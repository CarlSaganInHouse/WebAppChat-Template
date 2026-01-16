"""
Anthropic (Claude) provider implementation.
Wraps Anthropic's API to conform to our provider interface.
"""

from typing import Any, Generator, Optional
from anthropic import Anthropic
from providers.base import LLMProvider


class AnthropicProvider(LLMProvider):
    """
    Anthropic implementation of LLMProvider.
    Supports Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Sonnet, Claude 3 Haiku, and other Claude models.
    """

    def __init__(self, api_key: str):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (starts with 'sk-ant-')
        """
        self.client = Anthropic(api_key=api_key)

    def _convert_messages_to_anthropic_format(self, messages: list[dict[str, str]]) -> tuple[str, list[dict]]:
        """
        Convert OpenAI-style messages to Anthropic format.

        Anthropic requires:
        - System message separate from conversation messages
        - Messages must alternate user/assistant (no consecutive same roles)
        - First message must be 'user' role

        Args:
            messages: OpenAI-style messages with role/content

        Returns:
            Tuple of (system_prompt, anthropic_messages)
        """
        system_prompt = ""
        anthropic_messages = []

        # Extract system messages and combine them
        system_messages = []
        conversation_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_messages.append(msg.get("content", ""))
            else:
                conversation_messages.append(msg)

        # Combine all system messages
        if system_messages:
            system_prompt = "\n\n".join(system_messages)

        # Convert conversation messages and ensure they alternate
        prev_role = None
        accumulated_content = []

        for msg in conversation_messages:
            role = msg.get("role")
            content = msg.get("content", "")

            # Skip empty messages
            if not content:
                continue

            # Convert 'assistant' role to Anthropic format
            if role == "assistant":
                role = "assistant"
            elif role == "user":
                role = "user"
            else:
                # Unknown role, treat as user
                role = "user"

            # If same role as previous, accumulate content
            if role == prev_role and anthropic_messages:
                # Append to last message
                anthropic_messages[-1]["content"] += f"\n\n{content}"
            else:
                # New message
                anthropic_messages.append({
                    "role": role,
                    "content": content
                })
                prev_role = role

        # Ensure first message is from user
        if anthropic_messages and anthropic_messages[0]["role"] != "user":
            # Prepend a simple user message
            anthropic_messages.insert(0, {
                "role": "user",
                "content": "Hello"
            })

        return system_prompt, anthropic_messages

    def _convert_tools_to_anthropic_format(self, tools: Optional[list[dict]]) -> Optional[list[dict]]:
        """
        Convert OpenAI-style tools to Anthropic format.

        OpenAI uses 'functions' or 'tools' with type='function'.
        Anthropic uses 'tools' with simpler schema.

        Args:
            tools: OpenAI-style tool definitions

        Returns:
            Anthropic-style tool definitions or None
        """
        if not tools:
            return None

        anthropic_tools = []

        for tool in tools:
            # Handle OpenAI 'tools' format (with type='function')
            if "type" in tool and tool["type"] == "function":
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {})
                })
            # Handle legacy OpenAI 'functions' format
            elif "name" in tool:
                anthropic_tools.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {})
                })

        return anthropic_tools if anthropic_tools else None

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
        Perform non-streaming chat completion using Anthropic.

        Returns:
            Anthropic Message object
        """
        # Convert messages to Anthropic format
        system_prompt, anthropic_messages = self._convert_messages_to_anthropic_format(messages)

        # Build parameters
        params = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,  # Anthropic requires max_tokens
            **kwargs
        }

        # Add system prompt if present
        if system_prompt:
            params["system"] = system_prompt

        # Convert and add tools if present
        if tools:
            anthropic_tools = self._convert_tools_to_anthropic_format(tools)
            if anthropic_tools:
                params["tools"] = anthropic_tools

                # Handle tool_choice
                if tool_choice == "auto":
                    params["tool_choice"] = {"type": "auto"}
                elif tool_choice == "none":
                    params["tool_choice"] = {"type": "none"}
                elif tool_choice and isinstance(tool_choice, str):
                    # Specific tool requested
                    params["tool_choice"] = {"type": "tool", "name": tool_choice}

        return self.client.messages.create(**params)

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
        Perform streaming chat completion using Anthropic.

        Yields:
            Anthropic MessageStreamEvent objects
        """
        # Convert messages to Anthropic format
        system_prompt, anthropic_messages = self._convert_messages_to_anthropic_format(messages)

        # Build parameters
        params = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "stream": True,
            **kwargs
        }

        # Add system prompt if present
        if system_prompt:
            params["system"] = system_prompt

        # Convert and add tools if present
        if tools:
            anthropic_tools = self._convert_tools_to_anthropic_format(tools)
            if anthropic_tools:
                params["tools"] = anthropic_tools

                # Handle tool_choice
                if tool_choice == "auto":
                    params["tool_choice"] = {"type": "auto"}
                elif tool_choice == "none":
                    params["tool_choice"] = {"type": "none"}
                elif tool_choice and isinstance(tool_choice, str):
                    params["tool_choice"] = {"type": "tool", "name": tool_choice}

        # Stream the response
        with self.client.messages.stream(**params) as stream:
            for event in stream:
                yield event

    def get_usage(self, response: Any) -> tuple[int, int]:
        """
        Extract token usage from Anthropic response.

        Args:
            response: Anthropic Message object

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        if hasattr(response, 'usage') and response.usage:
            return (
                response.usage.input_tokens,
                response.usage.output_tokens
            )
        return (0, 0)

    def supports_tools(self) -> bool:
        """Anthropic Claude supports tool/function calling."""
        return True
