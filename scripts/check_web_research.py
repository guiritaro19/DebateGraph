"""Live smoke test for discovery, public fetch, indexing and retrieval."""

import asyncio
import json
from pathlib import Path

from app.config.settings import Settings
from app.db.store import Store
from app.rag.embeddings import embedding_provider
from app.rag.retrieval import CandidateRetriever
from app.services.loops import postgres_loop
from app.services.search import SearchProvider


async def main():
    settings = Settings()
    store = Store(settings)
    try:
        retriever = CandidateRetriever(store, embedding_provider(settings))
        report = await SearchProvider(settings).research_candidate(
            "regulação de apostas online proteção consumidores educação financeira",
            "lula",
            "REBUTTAL",
            retriever,
        )
        ids = [r["source_id"] for r in report["discoveries"] if r.get("status") == "ingested"]
        report["retrieved_web_chunks"] = [
            e["chunk_id"]
            for e in retriever.retrieve(
                "regulação apostas online consumidores", "lula", source_ids=ids, limit=3
            )
        ]
        Path("docs/samples/web-research-smoke.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        assert report["status"] == "complete"
        assert any(item["status"] == "ingested" for item in report["discoveries"])
        assert report["retrieved_web_chunks"]
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=postgres_loop)
