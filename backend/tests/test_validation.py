from uuid import uuid4

from app.agents.candidate import build_candidate_agent
from app.agents.validator import citation_errors
from app.graph.graph import initial_state
from app.models.schemas import UNCERTAINTY, CandidateResponse, DebateConfig, ValidationResult
from app.rag.embeddings import FixtureEmbeddings
from app.rag.retrieval import CandidateRetriever
from app.services.providers import FixtureProvider


def test_cross_candidate_and_missing_excerpt_rejected(store):
    evidence = CandidateRetriever(store, FixtureEmbeddings()).retrieve("inteligência artificial", "atlas")
    item = evidence[0]
    citation = {"source_id": item["source_id"], "chunk_id": item["chunk_id"], "quote": "invented excerpt"}
    response = CandidateResponse(
        candidate_id="nova",
        phase="ANSWER",
        content="Invented claim",
        confidence="HIGH",
        claims=[{"text": "invented", "citations": [citation]}],
        citations=[citation],
    )
    assert citation_errors(response, evidence)
    response.candidate_id = "atlas"
    assert any("excerpt" in e for e in citation_errors(response, evidence))


def test_content_without_claim_mapping_rejected():
    response = CandidateResponse(
        candidate_id="atlas",
        phase="ANSWER",
        content="Unmapped factual claim",
        confidence="LOW",
        claims=[],
        citations=[],
    )
    assert citation_errors(response, [])


async def test_max_one_regeneration_and_argument_fallback(store):
    class AlwaysReject(FixtureProvider):
        calls = 0

        async def structured(self, schema, instruction, payload):
            if schema is ValidationResult:
                return ValidationResult(valid=False, unsupported_claims=["test"], reasons=["unsupported"]), 0
            if schema is CandidateResponse and payload.get("evidence"):
                self.calls += 1
            return await super().structured(schema, instruction, payload)

    provider = AlwaysReject()
    graph = build_candidate_agent(provider, CandidateRetriever(store, FixtureEmbeddings()))
    state = initial_state(
        str(uuid4()),
        DebateConfig(
            candidate_a="atlas", candidate_b="nova", topic="Inteligência artificial", mode="fixture"
        ),
    )
    state.update(current_speaker="atlas", current_phase="ANSWER", question="Como tratar IA?")
    result = await graph.ainvoke(state)
    assert provider.calls == 2 and result["retries"] == 1
    assert UNCERTAINTY not in result["response"]["content"]
    assert result["response"]["claims"] == []


async def test_missing_evidence_continues_argument_without_model_call(store):
    class NoCall(FixtureProvider):
        async def structured(self, *args):
            raise AssertionError("No evidence must not call provider")

    graph = build_candidate_agent(NoCall(), CandidateRetriever(store, FixtureEmbeddings()))
    state = initial_state(
        str(uuid4()), DebateConfig(candidate_a="lula", candidate_b="flavio", topic="Educação")
    )
    state.update(current_speaker="lula", current_phase="ANSWER", question="Educação?")
    result = await graph.ainvoke(state)
    assert UNCERTAINTY not in result["response"]["content"]


def test_spacing_recovery_preserves_original_excerpt_and_rejects_changed_words():
    from app.agents.validator import restore_excerpt_spacing

    evidence = [
        {
            "candidate_id": "atlas",
            "source_id": "s",
            "chunk_id": "c",
            "content": "Educação financeira,\n  com proteção ao consumidor.",
        }
    ]
    cite = {"source_id": "s", "chunk_id": "c", "quote": "Educação financeira, com proteção ao consumidor."}
    response = CandidateResponse(
        candidate_id="atlas",
        phase="ANSWER",
        content="Educação financeira",
        claims=[{"text": "Educação financeira", "citations": [cite]}],
        citations=[cite],
        confidence="HIGH",
    )
    repaired = restore_excerpt_spacing(response, evidence)
    assert repaired.citations[0].quote == evidence[0]["content"]
    assert not citation_errors(repaired, evidence)
    repaired.citations[0].quote = "Educação financeira, com proteção ilimitada ao consumidor."
    rebound = restore_excerpt_spacing(repaired, evidence)
    assert rebound.citations[0].quote == evidence[0]["content"]
    assert not citation_errors(rebound, evidence)


async def test_provider_refusal_never_reaches_the_transcript(store):
    class Refusal(FixtureProvider):
        async def structured(self, schema, instruction, payload):
            if schema is CandidateResponse:
                return CandidateResponse(
                    candidate_id=payload["candidate_id"],
                    phase=payload["phase"],
                    content=UNCERTAINTY,
                    claims=[],
                    citations=[],
                    confidence="LOW",
                ), 3
            if schema is ValidationResult:
                raise AssertionError("Known safe fallback must not invoke semantic model")
            return await super().structured(schema, instruction, payload)

    state = initial_state(
        str(uuid4()),
        DebateConfig(
            candidate_a="atlas", candidate_b="nova", topic="Inteligência artificial", mode="fixture"
        ),
    )
    state.update(current_speaker="atlas", current_phase="REBUTTAL", question="Como?")
    result = await build_candidate_agent(Refusal(), CandidateRetriever(store, FixtureEmbeddings())).ainvoke(
        state
    )
    assert UNCERTAINTY not in result["response"]["content"]
    assert result["response"]["claims"] == []
    assert result["validation"]["valid"]


def test_quote_can_rebind_only_to_same_candidate_and_source():
    from app.agents.validator import restore_excerpt_spacing

    quote = "Educação financeira e autonomia."
    citation = {"source_id": "s", "chunk_id": "wrong", "quote": quote}
    response = CandidateResponse(
        candidate_id="atlas",
        phase="ANSWER",
        content=quote,
        claims=[{"text": quote, "citations": [citation]}],
        citations=[citation],
        confidence="HIGH",
    )
    evidence = [{"candidate_id": "atlas", "source_id": "s", "chunk_id": "real", "content": quote}]
    repaired = restore_excerpt_spacing(response, evidence)
    assert repaired.citations[0].chunk_id == "real"
    assert not citation_errors(repaired, evidence)
    repaired.candidate_id = "nova"
    assert citation_errors(restore_excerpt_spacing(repaired, evidence), evidence)


def test_public_speech_rejects_internal_ids_and_normalizes_claim_citations():
    from app.agents.validator import normalize_response_citations, public_content_errors

    cite = {
        "source_id": "443b3095-5e40-42e9-9094-879a81953c9b",
        "chunk_id": "19237306-2f97-406e-beb6-a1e37cfe2c08",
        "quote": "Trecho exato",
    }
    response = CandidateResponse(
        candidate_id="atlas",
        phase="ANSWER",
        content="Fala pública [443b3095-5e40-42e9-9094-879a81953c9b, 19237306-2f97-406e-beb6-a1e37cfe2c08]",
        claims=[{"text": "Afirmação", "citations": [cite]}],
        citations=[],
        confidence="HIGH",
    )
    assert public_content_errors(response.content)
    normalized = normalize_response_citations(response)
    assert normalized.citations == normalized.claims[0].citations


def test_argument_fallback_is_bound_to_topic_and_opponent_point():
    from app.agents.validator import argument_response

    dialogue = {
        "opponent_name": "Flávio",
        "latest_opponent_message": {"content": "Defendo cinco presídios de segurança máxima."},
    }
    response = argument_response("lula", "REBUTTAL", "facções no Brasil", dialogue)
    assert "facções no Brasil" in response.content
    assert "facções no Brasil" in response.content
    assert len(response.content.split()) > 100
    assert "vamos sair do slogan" not in response.content


def test_argument_fallback_never_copies_nested_opponent_speech():
    from app.agents.validator import argument_response

    nested = "Renan, você acabou de sustentar que Lula, você acabou de sustentar que cotas resolvem tudo."
    dialogue = {"opponent_name": "Renan", "latest_opponent_message": {"content": nested}}
    response = argument_response("lula", "REBUTTAL", "cotas raciais", dialogue)
    assert "acabou de sustentar" not in response.content
    assert "cotas raciais" in response.content
