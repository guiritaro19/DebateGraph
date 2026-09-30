import json

import pytest
from app.api.main import create_app
from app.config.settings import Settings
from app.models.schemas import CandidateResponse, DebateConfig
from app.rag.embeddings import FixtureEmbeddings
from fastapi.testclient import TestClient
from pydantic import ValidationError

from scripts.seed_fixtures import seed


def test_complete_miniature_debate_sse_and_log(settings):
    with TestClient(create_app(settings)) as client:
        seed(client.app.state.runtime.store, FixtureEmbeddings())
        payload = {
            "candidate_a": "atlas",
            "candidate_b": "nova",
            "topic": "Inteligência artificial",
            "mode": "fixture",
            "depth": 3,
        }
        result = client.post("/api/sessions", json=payload)
        assert result.status_code == 200
        session_id = result.json()["session_id"]
        response = client.get(f"/api/sessions/{session_id}/stream")
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert not [e for e in events if e["type"] == "error"]
        assert events[-1]["type"] == "complete"
        assert any(e["type"] == "token" for e in events)
        assert any(e["type"] == "graph_update" and e["node"] == "source_validator" for e in events)
        log = client.get(f"/api/sessions/{session_id}").json()
        assert log["status"] == "complete" and len(log["messages"]) == 4
        assert log["sources_consulted"] and log["execution_metadata"]
        assert client.get(f"/api/sessions/{session_id}/stream").status_code == 409
        state = client.get(f"/api/sessions/{session_id}/state").json()
        assert state["state"]["current_phase"] == "COMPLETE"
        assert "candidate_agent" in client.get("/api/graph").json()["nodes"]
        assert client.post("/api/sessions", json={**payload, "candidate_a": "lula"}).status_code == 400


def test_environment_configuration_and_structured_outputs():
    settings = Settings(_env_file=None, openai_api_key="")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        settings.require_openai()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, checkpoint_backend="invalid")
    with pytest.raises(ValidationError):
        CandidateResponse(
            content="x", candidate_id="atlas", phase="INVALID", claims=[], citations=[], confidence="HIGH"
        )
    with pytest.raises(ValidationError):
        DebateConfig(candidate_a="atlas", candidate_b="atlas", topic="Test")
    assert "secret" not in repr(Settings(_env_file=None, openai_api_key="secret"))


def test_unknown_session_and_invalid_config(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/sessions/missing").status_code == 404
        assert (
            client.post(
                "/api/sessions", json={"candidate_a": "atlas", "candidate_b": "nova", "topic": "x"}
            ).status_code
            == 422
        )


def test_public_product_lists_only_five_candidates_and_rejects_fictional_mode(settings):
    public = settings.model_copy(update={"llm_provider": "openai"})
    with TestClient(create_app(public)) as client:
        catalog = client.get("/api/candidates").json()
        assert {c["id"] for c in catalog} == {"lula", "flavio", "cury", "caiado", "renan"}
        assert all(not c["fictional"] for c in catalog)
        result = client.post(
            "/api/sessions",
            json={"candidate_a": "atlas", "candidate_b": "nova", "topic": "Educação", "mode": "fixture"},
        )
        assert result.status_code == 400
