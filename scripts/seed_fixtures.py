import argparse

from app.config.settings import Settings
from app.db.store import Store
from app.models.schemas import SourceInput
from app.rag.embeddings import embedding_provider
from app.rag.ingestion import Ingestor

FIXTURES = {
    "atlas": "O laboratório fictício Atlas propõe um catálogo aberto de experimentos de inteligência artificial. Cada experimento deve registrar documentação, testes de segurança e limites de uso. A educação em inteligência artificial deve incluir leitura crítica de fontes e auditoria de sistemas.",
    "nova": "O laboratório fictício Nova propõe ambientes de inteligência artificial reproduzíveis para educação. Os projetos devem publicar avaliações, rastreabilidade das fontes e alternativas locais. A segurança em inteligência artificial deve incluir revisão humana de resultados e testes de privacidade.",
}


def seed(store, embeddings):
    ingest = Ingestor(store, embeddings)
    return [
        ingest.ingest_text(
            SourceInput(
                candidate_id=cid,
                title=f"Fixture sintética {cid}",
                url=f"https://example.org/debategraph/fixtures/{cid}",
                publisher="DebateGraph synthetic tests",
                source_type="synthetic_fixture",
            ),
            text,
        )
        for cid, text in FIXTURES.items()
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-embeddings", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    print(seed(Store(settings), embedding_provider(settings, fixture=not args.live_embeddings)))
