"""
OpenAI provider implementation.
Wraps OpenAI's API to conform to our provider interface.
"""

from typing import Any, Generator, Optional
from openai import OpenAI
from providers.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """
    OpenAI implementation of LLMProvider.
    Supports GPT-4, GPT-3.5, and other OpenAI models.
    """

    def __init__(self, api_key: str):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)

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
        Perform non-streaming chat completion using OpenAI.

        Returns:
            OpenAI ChatCompletion object
        """
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs
        }

        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        if tools is not None:
            params["tools"] = tools
            if tool_choice is not None:
                params["tool_choice"] = tool_choice

        return self.client.chat.completions.create(**params)

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
        Perform streaming chat completion using OpenAI.

        Yields:
            OpenAI ChatCompletionChunk objects
        """
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            **kwargs
        }

        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        if tools is not None:
            params["tools"] = tools
            if tool_choice is not None:
                params["tool_choice"] = tool_choice

        return self.client.chat.completions.create(**params)

    def get_usage(self, response: Any) -> tuple[int, int]:
        """
        Extract token usage from OpenAI response.

        Args:
            response: OpenAI ChatCompletion object

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        if hasattr(response, 'usage') and response.usage:
            return (
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )
        return (0, 0)

    def supports_tools(self) -> bool:
        """OpenAI supports tool/function calling."""
        return True
