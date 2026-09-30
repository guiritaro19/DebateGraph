import asyncio
import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from app.config.catalog import candidate, candidates, topics
from app.config.settings import Settings
from app.graph.graph import initial_state
from app.models.schemas import DISCLAIMER, DebateConfig, SourceInput
from app.rag.embeddings import embedding_provider
from app.rag.ingestion import Ingestor
from app.services.runtime import Runtime

logging.basicConfig(level=logging.INFO)


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime = Runtime(settings)
        await app.state.runtime.start()
        yield
        await app.state.runtime.close()

    app = FastAPI(title="DebateGraph", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health():
        runtime = app.state.runtime
        return {
            "status": "ok",
            "database": "postgresql+pgvector" if runtime.store.postgres else "sqlite-local",
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "openai_configured": bool(settings.openai_api_key.get_secret_value()),
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/candidates")
    def catalog():
        sources = app.state.runtime.store.sources()
        return [
            {**c, "source_count": sum(s["candidate_id"] == c["id"] for s in sources)}
            for c in candidates()
            if not c["fictional"]
        ]

    @app.get("/api/topics")
    def topic_list():
        return topics()

    @app.get("/api/sources")
    def source_list(candidate_id: str | None = None):
        return [
            s
            for s in app.state.runtime.store.sources(candidate_id)
            if not candidate(s["candidate_id"])["fictional"]
        ]

    @app.post("/api/sources/ingest")
    async def ingest(metadata: SourceInput):
        if metadata.source_type == "synthetic_fixture":
            raise HTTPException(400, "Fixtures are seeded through the CLI")
        try:
            return await asyncio.to_thread(
                Ingestor(app.state.runtime.store, embedding_provider(settings)).ingest_url, metadata
            )
        except (ValueError, OSError, httpx.HTTPError) as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/api/sessions")
    def session_list():
        return app.state.runtime.store.sessions(include_fixture=settings.llm_provider == "fixture")

    @app.post("/api/sessions")
    def create_session(config: DebateConfig):
        try:
            selected = [candidate(config.candidate_a), candidate(config.candidate_b)]
            if settings.llm_provider != "fixture" and (
                config.mode != "live" or any(c["fictional"] for c in selected)
            ):
                raise ValueError("Only the five presidential participants are available")
            if config.mode == "fixture" and not all(c["fictional"] for c in selected):
                raise ValueError("Fixture mode requires fictional agents")
            app.state.runtime.graph(config.mode)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        session_id = str(uuid4())
        app.state.runtime.store.create_session(session_id, config)
        return {"session_id": session_id, "thread_id": session_id}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        session = app.state.runtime.store.get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        return session

    @app.get("/api/sessions/{session_id}/state")
    async def get_state(session_id: str):
        session = get_session(session_id)
        state = await app.state.runtime.graph(session["configuration"]["mode"]).aget_state(
            {"configurable": {"thread_id": session_id}}
        )
        return {"state": state.values, "next": state.next, "paused": bool(state.interrupts)}

    @app.get("/api/graph")
    def graph_info():
        graph = app.state.runtime.graph("live")
        drawing = graph.get_graph()
        from app.agents.candidate import build_candidate_agent
        from app.services.providers import FixtureProvider

        sub = build_candidate_agent(FixtureProvider(), None).get_graph()
        return {
            "mermaid": drawing.draw_mermaid(),
            "nodes": list(drawing.nodes),
            "edges": [
                {"source": e.source, "target": e.target, "conditional": e.conditional} for e in drawing.edges
            ],
            "candidate_subgraph": {
                "mermaid": sub.draw_mermaid(),
                "nodes": list(sub.nodes),
                "edges": [
                    {"source": e.source, "target": e.target, "conditional": e.conditional} for e in sub.edges
                ],
            },
        }

    @app.get("/api/sessions/{session_id}/stream")
    async def stream(session_id: str, resume: bool = False):
        session = get_session(session_id)
        runtime = app.state.runtime
        if session_id in runtime.active:
            raise HTTPException(409, "Session is already running")
        graph = runtime.graph(session["configuration"]["mode"])
        cfg = {"configurable": {"thread_id": session_id}, "recursion_limit": 200}
        snapshot = await graph.aget_state(cfg)
        if session["status"] == "complete":
            raise HTTPException(409, "Session is complete; open its saved log")
        if snapshot.interrupts and not resume:
            raise HTTPException(409, "Session paused; use resume=true")
        runtime.active.add(session_id)

        async def events():
            try:
                value = (
                    Command(resume=True)
                    if snapshot.interrupts
                    else (
                        None
                        if snapshot.values
                        else initial_state(session_id, DebateConfig.model_validate(session["configuration"]))
                    )
                )
                yield sse({"type": "session", "session_id": session_id, "thread_id": session_id})
                # Subgraphs emit updates as well, enabling live inspection of validator/retry nodes.
                async for namespace, mode, data in graph.astream(
                    value, cfg, stream_mode=["custom", "updates"], subgraphs=True
                ):
                    if mode == "custom":
                        yield sse(data)
                    else:
                        for node, update in data.items():
                            if node == "__interrupt__":
                                continue
                            yield sse(
                                {
                                    "type": "graph_update",
                                    "node": node,
                                    "namespace": list(namespace),
                                    "update": update,
                                }
                            )
                final = await graph.aget_state(cfg)
                paused = bool(final.interrupts)
                await asyncio.to_thread(
                    runtime.store.save_state, final.values, "paused" if paused else "complete"
                )
                yield sse(
                    {
                        "type": "paused" if paused else "complete",
                        "session_id": session_id,
                        "state": final.values,
                    }
                )
            except asyncio.CancelledError:
                checkpoint = await graph.aget_state(cfg)
                await asyncio.to_thread(runtime.store.save_state, checkpoint.values, "interrupted")
                raise
            except Exception as error:
                logging.getLogger("debategraph.api").exception("Session execution failed: %s", session_id)
                checkpoint = await graph.aget_state(cfg)
                if checkpoint.values:
                    await asyncio.to_thread(runtime.store.save_state, checkpoint.values, "error")
                yield sse(
                    {
                        "type": "error",
                        "error": type(error).__name__,
                        "message": "A execução falhou. Consulte o log do backend e retome a sessão.",
                    }
                )
            finally:
                runtime.active.discard(session_id)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def sse(event):
    return "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"


app = create_app()
