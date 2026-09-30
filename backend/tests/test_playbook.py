from app.models.schemas import CandidatePlaybookDraft, ValidationResult
from app.rag.embeddings import FixtureEmbeddings
from app.rag.retrieval import CandidateRetriever
from app.services.profiles import build_profile
from app.services.providers import FixtureProvider


async def test_playbook_uses_original_passages_and_keeps_supported_positions(store):
    evidence = CandidateRetriever(store, FixtureEmbeddings()).retrieve("inteligência artificial", "atlas")
    item = evidence[0]

    class Profile(FixtureProvider):
        async def structured(self, schema, instruction, payload):
            if schema is CandidatePlaybookDraft:
                return CandidatePlaybookDraft(
                    candidate_id="atlas",
                    positions=[
                        {
                            "area": "technology",
                            "position": "Supported position",
                            "chunk_ids": [item["chunk_id"]],
                        },
                        {
                            "area": "economy",
                            "position": "Unsupported position",
                            "chunk_ids": [item["chunk_id"]],
                        },
                    ],
                ), 1
            if schema is ValidationResult:
                assert all(c["quote"] == item["content"] for c in payload["response"]["citations"])
                return ValidationResult(
                    valid=False, unsupported_claims=["Unsupported position"], reasons=["No entailment"]
                ), 2
            raise AssertionError("Unexpected schema")

    result, tokens = await build_profile(Profile(), "atlas", evidence)
    assert [p.position for p in result.policy_positions] == ["Supported position"]
    assert result.policy_positions[0].citations[0].quote == item["content"]
    assert tokens == 3


async def test_truncated_profile_does_not_abort_topic_debate(store):
    from types import SimpleNamespace

    from openai import LengthFinishReasonError

    class Truncated(FixtureProvider):
        async def structured(self, *args):
            raise LengthFinishReasonError(completion=SimpleNamespace(usage=None))

    evidence = CandidateRetriever(store, FixtureEmbeddings()).retrieve("inteligência artificial", "atlas")
    result, tokens = await build_profile(Truncated(), "atlas", evidence)
    assert result.candidate_id == "atlas" and result.policy_positions == []
    assert tokens == 0
