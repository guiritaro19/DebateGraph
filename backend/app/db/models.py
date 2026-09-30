from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("candidate_id", "content_hash"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String, index=True)
    publication_date: Mapped[object] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String, index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    election_year: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(JSON().with_variant(Vector(), "postgresql"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_metadata: Mapped[dict] = mapped_column("metadata", JSON)


class DebateSession(Base):
    __tablename__ = "debate_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic: Mapped[str] = mapped_column(String)
    participants: Mapped[list] = mapped_column(JSON)
    configuration: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String)
    messages: Mapped[list] = mapped_column(JSON)
    sources_consulted: Mapped[list] = mapped_column(JSON)
    execution_metadata: Mapped[list] = mapped_column(JSON)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(default=0.0)
