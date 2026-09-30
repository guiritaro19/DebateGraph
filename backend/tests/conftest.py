import pytest
from app.config.settings import Settings
from app.db.store import Store
from app.rag.embeddings import FixtureEmbeddings

from scripts.seed_fixtures import seed


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        openai_api_key="",
        llm_provider="fixture",
        embedding_provider="fixture",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        runtime_dir=tmp_path,
        checkpoint_backend="sqlite",
    )


@pytest.fixture
def store(settings):
    instance = Store(settings)
    seed(instance, FixtureEmbeddings())
    yield instance
    instance.engine.dispose()
