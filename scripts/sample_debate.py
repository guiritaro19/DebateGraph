import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.config.settings import Settings
from app.graph.graph import initial_state
from app.models.schemas import DebateConfig
from app.rag.embeddings import embedding_provider
from app.services.loops import postgres_loop
from app.services.runtime import Runtime

from scripts.evaluate import evaluate
from scripts.seed_fixtures import seed


async def main(live=False):
    settings = Settings()
    runtime = Runtime(settings)
    await runtime.start()
    try:
        seed(runtime.store, embedding_provider(settings, fixture=not live))
        config = DebateConfig(
            candidate_a="atlas",
            candidate_b="nova",
            topic="Inteligência artificial na educação",
            mode="live" if live else "fixture",
        )
        session_id = str(uuid4())
        runtime.store.create_session(session_id, config)
        state = await runtime.graph(config.mode).ainvoke(
            initial_state(session_id, config),
            {"configurable": {"thread_id": session_id}, "recursion_limit": 200},
        )
        runtime.store.save_state(state, "complete")
        log = runtime.store.get_session(session_id)
        log["research"] = state["research"]
        destination = Path("docs/samples")
        destination.mkdir(parents=True, exist_ok=True)
        kind = "live" if live else "fixture"
        (destination / f"{kind}-debate.json").write_text(
            json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        report = evaluate(log, runtime.store)
        (destination / f"{kind}-evaluation.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps({"session_id": session_id, "evaluation": report}, indent=2, ensure_ascii=False))
    finally:
        await runtime.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    asyncio.run(main(parser.parse_args().live), loop_factory=postgres_loop)
