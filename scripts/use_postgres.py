"""Update local non-secret database settings, preserving the API key without printing it."""

from app.config.settings import ROOT
from dotenv import set_key

if __name__ == "__main__":
    target = ROOT / ".env"
    set_key(target, "DATABASE_URL", "postgresql+psycopg://debategraph:debategraph@127.0.0.1:5433/debategraph")
    set_key(target, "CHECKPOINT_BACKEND", "postgres")
    set_key(
        target, "CHECKPOINT_DATABASE_URL", "postgresql://debategraph:debategraph@127.0.0.1:5433/debategraph"
    )
    print("Local .env configured for PostgreSQL + pgvector and PostgreSQL checkpoints.")
