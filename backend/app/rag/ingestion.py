import hashlib
import ipaddress
import socket
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader
from sqlalchemy import select

from app.config.catalog import candidate
from app.db.models import DocumentChunk, Source
from app.rag.chunking import chunks, clean

MAX_BYTES = 20 * 1024 * 1024


def validate_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ["http", "https"] or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) source URLs are allowed")
    if parsed.port not in [None, 80, 443]:
        raise ValueError("Only standard HTTP(S) ports are allowed")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Private/local network sources are not allowed")


def fetch(url):
    # Validate each redirect and never expose credentials in URLs.
    for _ in range(5):
        validate_public_url(url)
        with (
            httpx.Client(timeout=30, follow_redirects=False) as client,
            client.stream(
                "GET", url, headers={"User-Agent": "DebateGraph/0.1 educational ingestion"}
            ) as response,
        ):
            if response.is_redirect:
                url = str(response.url.join(response.headers["location"]))
                continue
            response.raise_for_status()
            body = bytearray()
            for part in response.iter_bytes():
                body.extend(part)
                if len(body) > MAX_BYTES:
                    raise ValueError("Source exceeds 20 MB")
            return bytes(body), response.headers.get("content-type", ""), url
    raise ValueError("Too many redirects")


def extract(body, kind):
    if "pdf" in kind.lower() or body.startswith(b"%PDF"):
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(body)).pages)
    if "wordprocessingml" in kind or kind.endswith(".docx"):
        return "\n".join(p.text for p in Document(BytesIO(body)).paragraphs)
    if "html" in kind:
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text("\n", strip=True)
    return body.decode("utf-8-sig")


class Ingestor:
    def __init__(self, store, embeddings):
        self.store, self.embeddings = store, embeddings

    def ingest_url(self, metadata):
        if metadata.source_type == "government_program":
            host = urlparse(metadata.url).hostname or ""
            if not (host == "tse.jus.br" or host.endswith(".tse.jus.br")):
                raise ValueError("Tier 1 government programs must be hosted by TSE")
            if not metadata.election_year:
                raise ValueError("Government programs require election_year")
        body, kind, resolved = fetch(metadata.url)
        return self.ingest_text(metadata.model_copy(update={"url": resolved}), extract(body, kind))

    def ingest_document(self, path: Path, metadata):
        # CLI-only local file ingestion. The HTTP endpoint cannot read local paths.
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Source exceeds 20 MB")
        if metadata.source_type == "government_program":
            host = urlparse(metadata.url).hostname or ""
            if not (host == "tse.jus.br" or host.endswith(".tse.jus.br")) or not metadata.election_year:
                raise ValueError("TSE provenance URL and election_year are required")
        suffix = path.suffix.lower()
        if suffix not in [".pdf", ".docx", ".txt", ".md", ".html"]:
            raise ValueError("Supported documents: PDF, DOCX, TXT, MD, HTML")
        return self.ingest_text(
            metadata, extract(path.read_bytes(), "text/html" if suffix == ".html" else suffix)
        )

    def ingest_text(self, metadata, text):
        info = candidate(metadata.candidate_id)
        if (metadata.source_type == "synthetic_fixture") != info["fictional"]:
            raise ValueError("Synthetic sources are isolated from real candidate sources")
        normalized = clean(text)
        if len(normalized) < 30:
            raise ValueError("No usable text; scanned PDFs require OCR before importing")
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        with self.store.session() as db:
            existing = db.scalar(
                select(Source).where(
                    Source.candidate_id == metadata.candidate_id, Source.content_hash == digest
                )
            )
            if existing:
                # Add observed metadata previously unavailable; never replace an existing date.
                if existing.publication_date is None and metadata.publication_date is not None:
                    existing.publication_date = metadata.publication_date
                if existing.title.startswith("http") and not metadata.title.startswith("http"):
                    existing.title = metadata.title
                db.commit()
                matching = db.scalar(
                    select(DocumentChunk).where(
                        DocumentChunk.source_id == existing.id,
                        DocumentChunk.chunk_metadata["embedding_model"].as_string() == self.embeddings.model,
                    )
                )
                if matching:
                    return {"source_id": existing.id, "unchanged": True, "chunks": 0}
                source_id = existing.id
            else:
                source_id = None
        parts = chunks(normalized)
        vectors = self.embeddings.embed_documents(parts)
        if len(vectors) != len(parts):
            raise ValueError("Embedding provider returned an incorrect number of vectors")
        create_source = source_id is None
        source_id = source_id or str(uuid4())
        with self.store.session.begin() as db:
            if create_source:
                db.add(
                    Source(
                        id=source_id,
                        **metadata.model_dump(),
                        retrieved_at=datetime.now(UTC),
                        content_hash=digest,
                        raw_text=normalized,
                    )
                )
                db.flush()
            for index, (content, vector) in enumerate(zip(parts, vectors, strict=True)):
                db.add(
                    DocumentChunk(
                        id=str(uuid4()),
                        source_id=source_id,
                        candidate_id=metadata.candidate_id,
                        content=content,
                        embedding=vector,
                        chunk_index=index,
                        chunk_metadata={
                            "embedding_model": self.embeddings.model,
                            "embedding_dimensions": len(vector),
                        },
                    )
                )
        return {"source_id": source_id, "unchanged": False, "chunks": len(parts)}
