import argparse
import json
from pathlib import Path

from app.config.settings import Settings
from app.db.store import Store
from app.models.schemas import SourceInput
from app.rag.embeddings import embedding_provider
from app.rag.ingestion import Ingestor


def ingest(metadata_path, document=None):
    settings = Settings()
    metadata = SourceInput.model_validate_json(Path(metadata_path).read_text(encoding="utf-8"))
    pipeline = Ingestor(Store(settings), embedding_provider(settings))
    return pipeline.ingest_document(Path(document), metadata) if document else pipeline.ingest_url(metadata)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import curated URL or PDF/DOCX/TXT with explicit provenance"
    )
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--document")
    args = parser.parse_args()
    print(json.dumps(ingest(args.metadata, args.document), indent=2))
