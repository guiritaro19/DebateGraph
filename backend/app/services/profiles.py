import hashlib
import json
import logging

from openai import APIError, LengthFinishReasonError

from app.config.catalog import candidate
from app.models.schemas import (
    CandidatePlaybookDraft,
    CandidateProfile,
    CandidateResponse,
    Citation,
    PolicyPosition,
    RhetoricalProfile,
)


async def build_profile(provider, candidate_id, evidence, cache_dir=None):
    info = candidate(candidate_id)
    neutral = CandidateProfile(
        candidate_id=candidate_id,
        name=info["name"],
        party=info["party"],
        policy_positions=[],
        rhetorical_profile=RhetoricalProfile(
            recurring_topics=[],
            typical_argument_structure="insufficient evidence",
            typical_sentence_length="insufficient evidence",
            vocabulary_characteristics=[],
            debate_patterns=[],
        ),
        source_ids=[],
    )
    if not evidence:
        return neutral, 0
    cache = None
    if cache_dir is not None and not provider.model.startswith("fixture"):
        digest = hashlib.sha256(
            json.dumps(
                {
                    "version": "whole-program-compact-v4",
                    "model": provider.model,
                    "chunks": [(e["chunk_id"], e["content"]) for e in evidence],
                },
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache = cache_dir / f"{candidate_id}-{digest}.json"
        if cache.exists():
            saved = CandidateProfile.model_validate_json(cache.read_text(encoding="utf-8"))
            if saved.policy_positions:
                return saved, 0
    # Sample the full program evenly so a cache miss does not resend hundreds of chunks.
    if len(evidence) > 28:
        indexes = {round(i * (len(evidence) - 1) / 27) for i in range(28)}
        profile_evidence = [evidence[i] for i in sorted(indexes)]
    else:
        profile_evidence = evidence
    try:
        draft, tokens = await provider.structured(
            CandidatePlaybookDraft,
            "Read the representative passages sampled across the ENTIRE supplied program and abstract a broad political playbook. This is internal "
            "analysis, not candidate speech. Return up to eight positions, each at most 25 words, across "
            "worldview (state versus markets and individual/social responsibility), economy, healthcare, "
            "education, public security, taxation, technology, social protection, environment and foreign "
            "policy. Prefer distinct strategic priorities and mechanisms, not generic topic labels. "
            "Each position must select 1-2 actual chunk_ids that substantiate it. Never invent passage IDs. "
            "Do not write quotes: code will attach the original passages and verify entailment. "
            "Omit unsupported positions. Preserve historical context and avoid inferring from party alone.",
            {
                "candidate_id": candidate_id,
                "name": info["name"],
                "party": info["party"],
                "evidence": [
                    {
                        "chunk_id": e["chunk_id"],
                        "content": e["content"],
                        "election_year": e.get("election_year"),
                    }
                    for e in profile_evidence
                ],
            },
        )
    except (LengthFinishReasonError, APIError, ValueError) as error:
        # A broad playbook is optional: topical RAG and web evidence remain usable.
        logging.getLogger(__name__).warning(
            "Playbook unavailable for %s: %s; continuing with topic evidence",
            candidate_id,
            type(error).__name__,
        )
        return neutral, 0
    if draft.candidate_id != candidate_id:
        raise ValueError("Profile identity mismatch")
    lookup = {e["chunk_id"]: e for e in evidence if e["candidate_id"] == candidate_id}
    positions = []
    for item in draft.positions:
        citations = [
            Citation(source_id=lookup[cid]["source_id"], chunk_id=cid, quote=lookup[cid]["content"])
            for cid in dict.fromkeys(item.chunk_ids)
            if cid in lookup
        ]
        if citations:
            positions.append(PolicyPosition(area=item.area, position=item.position, citations=citations))
    profile = neutral.model_copy(
        update={
            "policy_positions": positions,
            "source_ids": list(dict.fromkeys(c.source_id for p in positions for c in p.citations)),
        }
    )
    if positions:
        from app.agents.validator import validate

        response = CandidateResponse(
            content=" ".join(p.position for p in positions),
            candidate_id=candidate_id,
            phase="ANSWER",
            claims=[
                {"text": p.position, "citations": [c.model_dump() for c in p.citations]} for p in positions
            ],
            citations=[c for p in positions for c in p.citations],
            confidence="MEDIUM",
        )
        supporting_ids = {c.chunk_id for c in response.citations}
        validation, used = await validate(
            provider, response, [e for e in evidence if e["chunk_id"] in supporting_ids]
        )
        tokens += used
        if not validation.valid:
            unsupported = set(validation.unsupported_claims)
            profile.policy_positions = (
                [p for p in positions if p.position not in unsupported] if unsupported else []
            )
            if cache is not None:
                cache.with_suffix(".validation.json").write_text(
                    validation.model_dump_json(indent=2), encoding="utf-8"
                )
    if cache is not None:
        cache.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return profile, tokens
