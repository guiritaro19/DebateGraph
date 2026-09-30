from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    openai_api_key: SecretStr = SecretStr("")
    llm_provider: Literal["openai", "fixture"] = "openai"
    llm_model: str = "gpt-4.1-mini"
    embedding_provider: Literal["openai", "fixture"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=8, le=3072)
    database_url: str = "sqlite:///runtime/debategraph.db"
    checkpoint_backend: Literal["sqlite", "memory", "postgres"] = "sqlite"
    checkpoint_database_url: str = "postgresql://debategraph:debategraph@localhost:5433/debategraph"
    search_provider: Literal["none", "tavily", "openai"] = "none"
    search_model: str = "gpt-4.1-mini"
    search_domains: str = "gov.br,senado.leg.br,camara.leg.br,tse.jus.br,pt.org.br,pl.org.br,agenciabrasil.ebc.com.br,g1.globo.com,bbc.com,reuters.com,apnews.com,uol.com.br,folha.uol.com.br,estadao.com.br,cnnbrasil.com.br,poder360.com.br,metropoles.com,gazetadopovo.com.br,noticias.r7.com,band.uol.com.br,mbl.org.br,partidomissao.com.br,missao.org.br"
    search_max_sources_per_phase: int = Field(default=3, ge=3, le=6)
    search_api_key: SecretStr = SecretStr("")
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_output_tokens: int = Field(default=2500, ge=128, le=4000)
    model_timeout_seconds: int = Field(default=60, ge=5, le=120)
    runtime_dir: Path = ROOT / "runtime"

    def require_openai(self):
        if not self.openai_api_key.get_secret_value():
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")
