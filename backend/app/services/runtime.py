from contextlib import AsyncExitStack

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.db.store import Store
from app.graph.graph import build_graph
from app.rag.embeddings import embedding_provider
from app.rag.retrieval import CandidateRetriever
from app.services.providers import generation_provider
from app.services.search import SearchProvider


class Runtime:
    def __init__(self, settings):
        self.settings = settings
        self.store = Store(settings)
        self.stack = AsyncExitStack()
        self.active = set()
        self.graphs = {}

    async def start(self):
        if self.settings.checkpoint_backend == "memory":
            self.checkpointer = InMemorySaver()
        elif self.settings.checkpoint_backend == "postgres":
            self.checkpointer = await self.stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(self.settings.checkpoint_database_url)
            )
            await self.checkpointer.setup()
        else:
            self.checkpointer = await self.stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(str(self.settings.runtime_dir / "checkpoints.db"))
            )

    def graph(self, mode):
        if mode not in self.graphs:
            fixture = mode == "fixture"
            self.graphs[mode] = build_graph(
                self.store,
                generation_provider(self.settings, fixture),
                CandidateRetriever(self.store, embedding_provider(self.settings, fixture)),
                SearchProvider(self.settings),
                self.checkpointer,
            )
        return self.graphs[mode]

    async def close(self):
        await self.stack.aclose()
        self.store.engine.dispose()
