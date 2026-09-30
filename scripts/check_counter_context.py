"""Focused regression replay: regenerate only the counter, retaining the validated preceding exchange."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from app.agents.candidate import build_candidate_agent
from app.config.settings import Settings
from app.graph.graph import initial_state
from app.models.schemas import DebateConfig
from app.rag.embeddings import embedding_provider
from app.rag.retrieval import CandidateRetriever
from app.services.loops import postgres_loop
from app.services.profiles import build_profile
from app.services.providers import generation_provider
from app.services.runtime import Runtime
from app.services.search import SearchProvider


async def main():
    runtime = Runtime(Settings())
    await runtime.start()
    try:
        original = runtime.store.get_session(sys.argv[1])
        config = DebateConfig.model_validate(original["configuration"])
        sid = str(uuid4())
        state = initial_state(sid, config)
        state.update(
            messages=original["messages"][:3],
            question=original["messages"][0]["content"],
            current_phase="COUNTER_REBUTTAL",
            current_speaker="flavio",
        )
        embeddings = embedding_provider(runtime.settings)
        program = runtime.store.program_evidence("flavio", embeddings.model)
        profile, profile_tokens = await build_profile(
            generation_provider(runtime.settings), "flavio", program, runtime.store.runtime_dir / "playbooks"
        )
        state["profiles"] = {"flavio": profile.model_dump()}
        print(
            f"Full program playbook: {len(program)} chunks, {len(profile.policy_positions)} policy areas, {profile_tokens} tokens"
        )
        graph = build_candidate_agent(
            generation_provider(runtime.settings),
            CandidateRetriever(runtime.store, embedding_provider(runtime.settings)),
            SearchProvider(runtime.settings),
        )
        result = await graph.ainvoke(state)
        response = result["response"]
        print(
            json.dumps(
                {
                    "content": response["content"],
                    "validation": result["validation"],
                    "attempts": result["validation_history"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        report = {
            "test": "focused_counter_replay",
            "original_session_id": original["id"],
            "preceding_exchange": state["messages"],
            "argument_plan": result.get("argument_plan"),
            "playbook": profile.model_dump(),
            "response": response,
            "validation": result["validation"],
            "attempts": result["validation_history"],
            "retrieval_query": result["retrieval_query"],
        }
        Path("docs/samples/counter-context-regression.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=postgres_loop)
