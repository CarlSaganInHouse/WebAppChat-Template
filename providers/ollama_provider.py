"""
Ollama provider implementation.
Wraps Ollama's API to conform to our provider interface.
"""

from typing import Any, Generator, Optional
import ollama
from providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    """
    Ollama implementation of LLMProvider.
    Supports locally-hosted models (llama3, mistral, etc.).
    """

    def __init__(self, host: str = "http://localhost:11434"):
        """
        Initialize Ollama provider.

        Args:
            host: Ollama server URL (default: http://localhost:11434)
        """
        self.host = host
        # Create explicit client with host
        self.client = ollama.Client(host=host)

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
        Perform non-streaming chat completion using Ollama.

        Note: Ollama doesn't support tools/functions yet.

        Returns:
            Ollama response dict
        """
        if tools is not None:
            raise NotImplementedError(
                "Ollama does not support tool/function calling yet"
            )

        options = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        return self.client.chat(
            model=model,
            messages=messages,
            options=options,
            **kwargs
        )

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
        Perform streaming chat completion using Ollama.

        Yields:
            Ollama chunk dicts
        """
        if tools is not None:
            raise NotImplementedError(
                "Ollama does not support tool/function calling yet"
            )

        options = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        return self.client.chat(
            model=model,
            messages=messages,
            options=options,
            stream=True,
            **kwargs
        )

    def get_usage(self, response: Any) -> tuple[int, int]:
        """
        Extract token usage from Ollama response.

        Args:
            response: Ollama response dict

        Returns:
            Tuple of (input_tokens, output_tokens)
            Returns (0, 0) if usage not available
        """
        # Ollama returns token counts in different keys
        if isinstance(response, dict):
            prompt_tokens = response.get('prompt_eval_count', 0)
            completion_tokens = response.get('eval_count', 0)
            return (prompt_tokens, completion_tokens)
        return (0, 0)

    def supports_tools(self) -> bool:
        """Ollama does not support tool/function calling yet."""
        return False
