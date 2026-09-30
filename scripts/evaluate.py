import argparse
import json
from pathlib import Path
from statistics import mean

from app.agents.validator import citation_errors
from app.config.settings import Settings
from app.db.store import Store
from app.models.schemas import CandidateResponse


def evaluate(log, store):
    from app.db.models import DocumentChunk
    from sqlalchemy import select

    with store.session() as db:
        evidence = [
            {
                "candidate_id": chunk.candidate_id,
                "chunk_id": chunk.id,
                "source_id": chunk.source_id,
                "content": chunk.content,
            }
            for chunk in db.scalars(select(DocumentChunk))
        ]
    messages = [m for m in log["messages"] if m["phase"] != "QUESTION"]
    claims = [c for m in messages for c in m.get("claims", [])]
    checked = [
        citation_errors(
            CandidateResponse.model_validate(
                {k: m[k] for k in ["content", "candidate_id", "phase", "claims", "citations", "confidence"]}
            ),
            evidence,
        )
        for m in messages
    ]
    coverage = sum(bool(c["citations"]) for c in claims) / len(claims) if claims else None
    unsupported = sum(len(m.get("validation", {}).get("unsupported_claims", [])) for m in messages)
    lookup = {e["source_id"]: e["candidate_id"] for e in evidence}
    isolated = all(lookup.get(c["source_id"]) == m["candidate_id"] for m in messages for c in m["citations"])
    retrievals = [
        e.get("retrieval_count", 0)
        for e in log.get("execution_metadata", [])
        if e["node"] == "research_topic"
    ]
    sims = [e["similarity"] for e in log.get("research", {}).get("evidence", [])]
    draft_rejections = [
        attempt
        for message in messages
        for attempt in message.get("validation", {}).get("attempts", [])
        if not attempt["valid"]
    ]
    return {
        "rejected_draft_attempts": len(draft_rejections),
        "unsupported_draft_claims": sum(len(a["unsupported_claims"]) for a in draft_rejections),
        "citation_coverage": coverage,
        "unsupported_claim_rate": unsupported / len(claims) if claims else None,
        "citation_errors": sum(len(e) for e in checked),
        "candidate_source_isolation": isolated,
        "mean_retrieval_similarity": mean(sims) if sims else None,
        "retrieval_relevance_note": "Cosine similarity is a proxy; manual relevance labels remain necessary.",
        "retrieved_chunks": sum(retrievals),
        "response_latency_ms": log.get(
            "latency_ms", sum(e.get("duration_ms", 0) for e in log.get("execution_metadata", []))
        ),
        "token_usage": log.get(
            "token_usage", sum(e.get("tokens", 0) for e in log.get("execution_metadata", []))
        ),
        "abstentions": sum(not m["claims"] for m in messages),
        "candidate_messages": len(messages),
        "scope": "Engineering diagnostics only; no candidate comparison.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session")
    group.add_argument("--file")
    args = parser.parse_args()
    store = Store(Settings())
    log = (
        store.get_session(args.session)
        if args.session
        else json.loads(Path(args.file).read_text(encoding="utf-8"))
    )
    if not log:
        raise SystemExit("Session not found")
    print(json.dumps(evaluate(log, store), indent=2, ensure_ascii=False))
