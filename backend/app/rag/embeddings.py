import hashlib
import math
import re
import unicodedata
from typing import Protocol

from langchain_openai import OpenAIEmbeddings


class EmbeddingProvider(Protocol):
    model: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FixtureEmbeddings:
    """Deterministic hash bag-of-words; test fixtures only, NOT semantic embeddings."""

    model = "fixture-hash-v1"

    def __init__(self, dimensions=1536):
        self.dimensions = dimensions

    def embed_query(self, text):
        vector = [0.0] * self.dimensions
        normalized = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
        for word in re.findall(r"\w+", normalized):
            if len(word) > 2:
                index = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dimensions
                vector[index] += 1
        norm = math.sqrt(sum(x * x for x in vector)) or 1
        return [x / norm for x in vector]

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]


class OpenAIEmbeddingProvider:
    def __init__(self, settings):
        settings.require_openai()
        self.model = settings.embedding_model
        self.client = OpenAIEmbeddings(
            model=self.model,
            dimensions=settings.embedding_dimensions,
            api_key=settings.openai_api_key.get_secret_value(),
            request_timeout=settings.model_timeout_seconds,
            max_retries=1,
        )

    def embed_documents(self, texts):
        return self.client.embed_documents(texts)

    def embed_query(self, text):
        return self.client.embed_query(text)


def embedding_provider(settings, fixture=False):
    if fixture or settings.embedding_provider == "fixture":
        return FixtureEmbeddings(settings.embedding_dimensions)
    return OpenAIEmbeddingProvider(settings)
