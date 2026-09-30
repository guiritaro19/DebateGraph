from datetime import date
from typing import Protocol

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select

from app.db.models import DocumentChunk, Source
from app.models.schemas import TIERS


class Retriever(Protocol):
    def retrieve(self, query: str, candidate_id: str, **filters) -> list[dict]: ...


class Reranker(Protocol):
    def rerank(self, query: str, evidence: list[dict]) -> list[dict]: ...


class CandidateRetriever:
    def __init__(self, store, embeddings, reranker=None):
        self.store, self.embeddings, self.reranker = store, embeddings, reranker

    def retrieve(
        self,
        query,
        candidate_id,
        source_type=None,
        publication_date=None,
        topic=None,
        limit=6,
        source_ids=None,
    ):
        vector = self.embeddings.embed_query(query + (" " + topic if topic else ""))
        with self.store.session() as db:
            stmt = (
                select(DocumentChunk, Source)
                .join(Source, Source.id == DocumentChunk.source_id)
                .where(DocumentChunk.candidate_id == candidate_id, Source.candidate_id == candidate_id)
            )
            if source_ids is not None:
                stmt = stmt.where(Source.id.in_(source_ids))
            if source_type:
                stmt = stmt.where(Source.source_type == source_type)
            if publication_date:
                stmt = stmt.where(Source.publication_date >= date.fromisoformat(publication_date))
            if self.store.postgres:
                # Never compare embedding spaces/models or fixture vectors against real embeddings.
                stmt = stmt.where(
                    DocumentChunk.chunk_metadata["embedding_model"].as_string() == self.embeddings.model
                )
                stmt = stmt.add_columns(
                    cast(DocumentChunk.embedding, Vector()).cosine_distance(vector).label("distance")
                )
                stmt = stmt.order_by("distance").limit(limit * 3)
                rows = [(chunk, source, 1 - float(distance)) for chunk, source, distance in db.execute(stmt)]
            else:
                rows = []
                for chunk, source in db.execute(stmt):
                    if chunk.chunk_metadata.get("embedding_model") != self.embeddings.model:
                        continue
                    if len(vector) != len(chunk.embedding):
                        continue
                    import math

                    denom = math.sqrt(sum(x * x for x in vector) * sum(x * x for x in chunk.embedding)) or 1
                    rows.append((chunk, source, sum(x * y for x, y in zip(vector, chunk.embedding)) / denom))
            # First exclude weak relevance, then prioritize authoritative sources.
            evidence = [
                {
                    **self.store.source_dict(source),
                    "source_id": source.id,
                    "chunk_id": chunk.id,
                    "content": chunk.content,
                    "similarity": round(score, 5),
                    "tier": TIERS[source.source_type],
                }
                for chunk, source, score in rows
                if score >= 0.15
            ]
            evidence.sort(key=lambda item: (item["tier"], -item["similarity"]))
            return (self.reranker.rerank(query, evidence) if self.reranker else evidence)[:limit]


class TopicRetriever:
    def __init__(self, candidate_retriever):
        self.candidate_retriever = candidate_retriever

    def retrieve(self, topic, candidate_ids):
        return {cid: self.candidate_retriever.retrieve(topic, cid) for cid in candidate_ids}
