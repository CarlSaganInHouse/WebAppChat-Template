"""
Embedding provider implementations.
Abstracts embedding generation for easy provider swapping.
"""

from openai import OpenAI
from providers.base import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI implementation of EmbeddingProvider.
    Supports text-embedding-3-small, text-embedding-3-large, etc.
    """

    # Model dimensions (for reference)
    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        """
        Initialize OpenAI embedding provider.

        Args:
            api_key: OpenAI API key
            model: Embedding model name
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for texts using OpenAI.

        Args:
            texts: List of strings to embed

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If texts is empty
        """
        if not texts:
            raise ValueError("Cannot embed empty text list")

        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )

        return [data.embedding for data in response.data]

    def get_model_name(self) -> str:
        """Get the embedding model name."""
        return self.model

    def get_dimension(self) -> int:
        """
        Get the embedding dimension for this model.

        Returns:
            Embedding vector dimension
        """
        return self.MODEL_DIMENSIONS.get(self.model, 1536)
