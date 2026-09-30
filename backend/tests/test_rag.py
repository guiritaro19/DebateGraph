from datetime import date
from io import BytesIO
from unittest.mock import patch

import pytest
from app.db.models import DocumentChunk
from app.models.schemas import SourceInput
from app.rag.embeddings import FixtureEmbeddings
from app.rag.ingestion import Ingestor, extract, validate_public_url
from app.rag.retrieval import CandidateRetriever
from sqlalchemy import select


def test_isolation_and_filters(store):
    metadata = SourceInput(
        candidate_id="atlas",
        title="Another dated fixture",
        url="https://example.org/test",
        source_type="synthetic_fixture",
        publisher="test",
        publication_date=date(2026, 9, 1),
    )
    Ingestor(store, FixtureEmbeddings()).ingest_text(
        metadata,
        "O laboratório fictício Atlas usa inteligência artificial na educação com revisão humana e documentação aberta.",
    )
    retriever = CandidateRetriever(store, FixtureEmbeddings())
    results = retriever.retrieve(
        "Inteligência artificial", "atlas", source_type="synthetic_fixture", publication_date="2026-08-01"
    )
    assert results and all(r["candidate_id"] == "atlas" for r in results)
    assert all(r["publication_date"] >= "2026-08-01" for r in results)
    assert retriever.retrieve("Inteligência artificial", "atlas", source_type="journalism") == []
    assert retriever.retrieve("Inteligência artificial", "atlas", publication_date="2027-01-01") == []
    assert all(
        r["candidate_id"] == "nova"
        for r in retriever.retrieve("educação", "nova", topic="Inteligência artificial")
    )


def test_dedup_never_calls_embeddings_for_unchanged_content(store):
    metadata = SourceInput(
        candidate_id="atlas",
        title="Dedup",
        url="https://example.org/dedup",
        source_type="synthetic_fixture",
        publisher="test",
    )
    text = "Documentação de inteligência artificial com testes reproduzíveis e rastreabilidade de resultados."
    embeddings = FixtureEmbeddings()
    pipeline = Ingestor(store, embeddings)
    first = pipeline.ingest_text(metadata, text)
    with patch.object(embeddings, "embed_documents", side_effect=AssertionError("Must not embed twice")):
        second = pipeline.ingest_text(metadata, text)
    assert second["unchanged"] and first["source_id"] == second["source_id"]


def test_synthetic_sources_cannot_enter_political_context(store):
    pipeline = Ingestor(store, FixtureEmbeddings())
    with pytest.raises(ValueError, match="isolated"):
        pipeline.ingest_text(
            SourceInput(
                candidate_id="lula",
                title="Wrong",
                url="https://example.org",
                publisher="test",
                source_type="synthetic_fixture",
            ),
            "Some synthetic text that cannot be a real position.",
        )


def test_tse_provenance_is_required(store):
    pipeline = Ingestor(store, FixtureEmbeddings())
    with pytest.raises(ValueError, match="TSE"):
        pipeline.ingest_url(
            SourceInput(
                candidate_id="lula",
                title="Wrong",
                url="https://example.org",
                publisher="test",
                source_type="government_program",
                election_year=2026,
            )
        )


def test_extract_html_docx_and_chunk_metadata(store):
    from docx import Document

    assert "hidden" not in extract(b"<main>Real evidence</main><script>hidden</script>", "text/html")
    doc = Document()
    doc.add_paragraph("Document evidence")
    stream = BytesIO()
    doc.save(stream)
    assert extract(stream.getvalue(), ".docx") == "Document evidence"
    with store.session() as db:
        assert all(
            c.chunk_metadata["embedding_model"] == "fixture-hash-v1"
            for c in db.scalars(select(DocumentChunk))
        )


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "http://127.0.0.1/a", "http://localhost/a", "https://user:secret@example.com/a"],
)
def test_private_url_rejection(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_source_filter_keeps_candidate_isolation(store):
    retriever = CandidateRetriever(store, FixtureEmbeddings())
    evidence = retriever.retrieve("inteligência artificial", "atlas")
    ids = [evidence[0]["source_id"]]
    assert retriever.retrieve("inteligência artificial", "atlas", source_ids=ids)
    assert retriever.retrieve("inteligência artificial", "nova", source_ids=ids) == []
    assert retriever.retrieve("inteligência artificial", "atlas", source_ids=[]) == []
