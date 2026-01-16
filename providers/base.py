"""
Abstract base classes for LLM and embedding providers.
Following the Adapter Pattern to normalize different API interfaces.
"""

from abc import ABC, abstractmethod
from typing import Any, Generator, Optional


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers (OpenAI, Ollama, Anthropic, etc.).

    Providers adapt external APIs to a common interface, making it easy
    to swap models without changing core application logic.
    """

    @abstractmethod
    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Perform a non-streaming chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (e.g., 'gpt-4', 'llama3')
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            tools: Optional list of tool/function definitions
            tool_choice: How to choose tools ('auto', 'none', or specific tool)
            **kwargs: Additional provider-specific parameters

        Returns:
            Provider's native response object

        Raises:
            NotImplementedError: If provider doesn't support requested features
        """
        pass

    @abstractmethod
    def stream_chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> Generator[Any, None, None]:
        """
        Perform a streaming chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: Optional list of tool/function definitions
            tool_choice: How to choose tools
            **kwargs: Additional provider-specific parameters

        Returns:
            Generator yielding provider's native chunk objects

        Raises:
            NotImplementedError: If provider doesn't support streaming
        """
        pass

    @abstractmethod
    def get_usage(self, response: Any) -> tuple[int, int]:
        """
        Extract token usage from a response.

        Args:
            response: Provider's native response object

        Returns:
            Tuple of (input_tokens, output_tokens)
            Returns (0, 0) if usage information is unavailable
        """
        pass

    def supports_tools(self) -> bool:
        """
        Check if this provider supports tool/function calling.

        Returns:
            True if tools are supported, False otherwise
        """
        return False


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.
    """

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)

        Raises:
            ValueError: If texts is empty or contains invalid input
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the embedding model name.

        Returns:
            Model name (e.g., 'text-embedding-3-small')
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """
        Get the embedding dimension for this model.

        Returns:
            Embedding vector dimension (e.g., 1536, 384)
        """
        pass
