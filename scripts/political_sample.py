import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.config.settings import Settings
from app.graph.graph import initial_state
from app.models.schemas import DebateConfig
from app.services.loops import postgres_loop
from app.services.runtime import Runtime

from scripts.evaluate import evaluate


async def main():
    runtime = Runtime(Settings())
    await runtime.start()
    try:
        config = DebateConfig(
            candidate_a="lula",
            candidate_b="flavio",
            topic="Educação básica e formação de professores",
            style_mode="expressive",
        )
        session_id = str(uuid4())
        runtime.store.create_session(session_id, config)
        state = await runtime.graph("live").ainvoke(
            initial_state(session_id, config),
            {"configurable": {"thread_id": session_id}, "recursion_limit": 200},
        )
        runtime.store.save_state(state, "complete")
        log = runtime.store.get_session(session_id)
        log["research"] = state["research"]
        Path("docs/samples/political-debate.json").write_text(
            json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        report = evaluate(log, runtime.store)
        Path("docs/samples/political-evaluation.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps({"session_id": session_id, "evaluation": report}, indent=2, ensure_ascii=False))
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=postgres_loop)
