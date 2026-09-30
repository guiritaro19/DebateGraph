from uuid import uuid4

from app.agents.candidate import build_candidate_agent
from app.agents.dialogue import dialogue_context, question_participants, repeated_response
from app.agents.question import generate_question
from app.agents.validator import validate
from app.graph.graph import initial_state
from app.models.schemas import CandidateResponse, DebateConfig, DebateQuestion
from app.services.providers import FixtureProvider


def base():
    return initial_state(
        str(uuid4()), DebateConfig(candidate_a="atlas", candidate_b="nova", topic="Educação", mode="fixture")
    )


async def test_question_addresses_opponent_and_rotates():
    state = base()
    state["research"] = {"evidence": [], "source_ids": []}

    class Capture(FixtureProvider):
        async def structured(self, schema, instruction, payload):
            assert schema is DebateQuestion
            assert payload["asker"]["id"] == "atlas"
            assert payload["opponent"]["id"] == "nova"
            assert "not a moderator" in instruction
            return await super().structured(schema, instruction, payload)

    result, _ = await generate_question(Capture(), state)
    assert result.content.startswith("Nova")
    state["turn_number"] = 1
    assert question_participants(state) == ("nova", "atlas")


async def test_counter_uses_latest_opponent_and_prefers_unused_evidence():
    state = base()
    own = {
        "candidate_id": "nova",
        "phase": "ANSWER",
        "content": "Primeira resposta",
        "citations": [{"chunk_id": "used"}],
    }
    last = {
        "candidate_id": "atlas",
        "phase": "REBUTTAL",
        "content": "Como pagar?",
        "claims": [{"text": "Custos da formação docente"}],
    }
    state.update(
        current_speaker="nova", current_phase="COUNTER_REBUTTAL", question="Educação?", messages=[own, last]
    )

    class Retrieval:
        def retrieve(self, query, cid, **filters):
            assert "Custos da formação docente" in query
            assert cid == "nova"
            return [
                {"candidate_id": cid, "chunk_id": chunk, "source_id": "source", "content": "Formação docente"}
                for chunk in ["best", "used", "fresh"]
            ]

    class Capture(FixtureProvider):
        async def structured(self, schema, instruction, payload):
            if schema is CandidateResponse:
                context = payload["dialogue_context"]
                assert context["latest_opponent_message"] == last
                assert context["previous_own_responses"] == [own]
                assert [e["chunk_id"] for e in payload["evidence"]] == ["best", "fresh", "used"]
            return await super().structured(schema, instruction, payload)

    result = await build_candidate_agent(Capture(), Retrieval()).ainvoke(state)
    assert result["validation"]["valid"]
    assert result["dialogue_context"]["latest_opponent_message"] == last


async def test_repeated_own_speech_rejected_before_semantic_judge():
    citation = {"chunk_id": "c", "source_id": "s", "quote": "Formação docente"}
    response = CandidateResponse(
        candidate_id="nova",
        phase="COUNTER_REBUTTAL",
        content="Formação docente",
        claims=[{"text": "Formação docente", "citations": [citation]}],
        citations=[citation],
        confidence="HIGH",
    )

    class NoCall:
        async def structured(self, *args):
            raise AssertionError("Duplicate must be rejected before model call")

    result, tokens = await validate(
        NoCall(),
        response,
        [{"chunk_id": "c", "source_id": "s", "candidate_id": "nova", "content": "Formação docente"}],
        {"previous_own_responses": [{"content": "Formação docente"}]},
    )
    assert not result.valid and tokens == 0
    assert any("repeats" in reason for reason in result.reasons)
    assert not repeated_response("Qual é o custo dessa medida?", [{"content": "Formação docente"}])


def test_context_excludes_own_question_from_previous_responses():
    state = base()
    state.update(
        current_speaker="atlas", messages=[{"candidate_id": "atlas", "phase": "QUESTION", "content": "Como?"}]
    )
    assert dialogue_context(state)["previous_own_responses"] == []


def test_requested_political_frames_are_distinct():
    from app.agents.dialogue import ideological_direction

    assert "Left-wing" in ideological_direction("lula")
    assert "Right-wing" in ideological_direction("flavio")
    assert ideological_direction("lula") != ideological_direction("flavio")
    assert "program playbook" in ideological_direction("caiado")


async def test_argument_plan_precedes_speech_and_enters_generation(store):
    from app.models.schemas import DebateArgumentPlan
    from app.rag.embeddings import FixtureEmbeddings
    from app.rag.retrieval import CandidateRetriever

    calls = []

    class Planned(FixtureProvider):
        async def structured(self, schema, instruction, payload):
            calls.append(schema)
            if schema is CandidateResponse:
                assert payload["argument_plan"]["disagreement"]
                assert payload["political_frame"]
            return await super().structured(schema, instruction, payload)

    state = base()
    state.update(
        topic="Inteligência artificial",
        current_speaker="nova",
        current_phase="COUNTER_REBUTTAL",
        question="Como executar?",
    )
    result = await build_candidate_agent(Planned(), CandidateRetriever(store, FixtureEmbeddings())).ainvoke(
        state
    )
    assert calls.index(DebateArgumentPlan) < calls.index(CandidateResponse)
    assert result["argument_plan"]["reasoning_steps"]
