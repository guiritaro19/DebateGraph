from app.config.settings import Settings
from app.db.store import Store
from app.graph.graph import build_graph
from app.rag.embeddings import embedding_provider
from app.rag.retrieval import CandidateRetriever
from app.services.providers import generation_provider
from app.services.search import SearchProvider

settings = Settings()
graph = build_graph(
    Store(settings),
    generation_provider(settings),
    CandidateRetriever(Store(settings), embedding_provider(settings)),
    SearchProvider(settings),
)
