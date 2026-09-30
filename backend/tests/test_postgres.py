import os

import pytest
from app.config.settings import Settings
from app.db.store import Store
from app.rag.embeddings import FixtureEmbeddings
from app.rag.retrieval import CandidateRetriever
from sqlalchemy import text

from scripts.seed_fixtures import seed


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL to test real pgvector")
def test_real_pgvector_retrieval():
    settings = Settings(_env_file=None, database_url=os.environ["TEST_DATABASE_URL"])
    store = Store(settings)
    try:
        seed(store, FixtureEmbeddings())
        with store.engine.connect() as connection:
            assert connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        docs = CandidateRetriever(store, FixtureEmbeddings()).retrieve("inteligência artificial", "atlas")
        assert docs and all(d["candidate_id"] == "atlas" for d in docs)
    finally:
        store.engine.dispose()
