import argparse
import json
from pathlib import Path

from app.config.settings import Settings
from app.db.store import Store
from app.models.schemas import SourceInput
from app.rag.embeddings import embedding_provider
from app.rag.ingestion import Ingestor

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()
    settings = Settings()
    pipeline = Ingestor(Store(settings), embedding_provider(settings))
    for record in json.loads(Path(args.manifest).read_text(encoding="utf-8")):
        metadata = SourceInput.model_validate(record["metadata"])
        print(
            pipeline.ingest_document(Path(record["document"]), metadata)
            if "document" in record
            else pipeline.ingest_url(metadata)
        )
