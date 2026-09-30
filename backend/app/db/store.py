from datetime import UTC, datetime

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, DebateSession, DocumentChunk, Source


class Store:
    def __init__(self, settings):
        self.runtime_dir = settings.runtime_dir
        settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        url = settings.database_url
        if url == "sqlite:///runtime/debategraph.db":
            url = f"sqlite:///{settings.runtime_dir / 'debategraph.db'}"
        args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=args, pool_pre_ping=True)
        self.postgres = self.engine.dialect.name == "postgresql"
        if self.postgres:
            with self.engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def source_dict(self, source):
        return {
            key: (
                getattr(source, key).isoformat()
                if getattr(source, key) and key in ["publication_date", "retrieved_at"]
                else getattr(source, key)
            )
            for key in [
                "id",
                "candidate_id",
                "title",
                "url",
                "publisher",
                "source_type",
                "publication_date",
                "retrieved_at",
                "content_hash",
                "election_year",
            ]
        }

    def sources(self, candidate_id=None):
        with self.session() as db:
            query = select(Source)
            if candidate_id:
                query = query.where(Source.candidate_id == candidate_id)
            return [self.source_dict(source) for source in db.scalars(query)]

    def program_evidence(self, candidate_id, embedding_model):
        with self.session() as db:
            rows = db.execute(
                select(DocumentChunk, Source)
                .join(Source, Source.id == DocumentChunk.source_id)
                .where(
                    Source.candidate_id == candidate_id,
                    DocumentChunk.candidate_id == candidate_id,
                    Source.source_type == "government_program",
                    DocumentChunk.chunk_metadata["embedding_model"].as_string() == embedding_model,
                )
                .order_by(Source.id, DocumentChunk.chunk_index)
            )
            return [
                {
                    **self.source_dict(source),
                    "source_id": source.id,
                    "chunk_id": chunk.id,
                    "content": chunk.content,
                }
                for chunk, source in rows
            ]

    def create_session(self, session_id, config):
        with self.session.begin() as db:
            db.add(
                DebateSession(
                    id=session_id,
                    topic=config.topic,
                    participants=[config.candidate_a, config.candidate_b],
                    configuration=config.model_dump(),
                    created_at=datetime.now(UTC),
                    status="created",
                    messages=[],
                    sources_consulted=[],
                    execution_metadata=[],
                )
            )

    def save_state(self, state, status="running"):
        with self.session.begin() as db:
            row = db.get(DebateSession, state["session_id"])
            if row is None:
                return  # Studio executes graphs without the REST session creator.
            row.status = status
            row.messages = state.get("messages", [])
            row.sources_consulted = list(
                dict.fromkeys(c["source_id"] for m in row.messages for c in m.get("citations", []))
            )
            row.execution_metadata = state.get("execution_metadata", [])
            row.token_usage = sum(n.get("tokens", 0) for n in row.execution_metadata)
            row.latency_ms = sum(
                n.get("duration_ms", 0) for n in row.execution_metadata if not n.get("namespace")
            )

    def get_session(self, session_id):
        with self.session() as db:
            row = db.get(DebateSession, session_id)
            if row is None:
                return None
            return {
                key: (getattr(row, key).isoformat() if key == "created_at" else getattr(row, key))
                for key in [
                    "id",
                    "topic",
                    "participants",
                    "configuration",
                    "created_at",
                    "status",
                    "messages",
                    "sources_consulted",
                    "execution_metadata",
                    "token_usage",
                    "latency_ms",
                ]
            }

    def sessions(self, include_fixture=True):
        with self.session() as db:
            return [
                {"id": s.id, "topic": s.topic, "status": s.status, "created_at": s.created_at.isoformat()}
                for s in db.scalars(
                    select(DebateSession)
                    .where(
                        DebateSession.configuration["mode"].as_string() != "fixture"
                        if not include_fixture
                        else True
                    )
                    .order_by(DebateSession.created_at.desc())
                    .limit(30)
                )
            ]
