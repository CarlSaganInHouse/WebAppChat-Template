"""
Provider abstraction for LLM and embedding services.
Allows easy swapping between OpenAI, Ollama, Anthropic, etc.
"""

from providers.base import LLMProvider, EmbeddingProvider
from providers.openai_provider import OpenAIProvider
from providers.ollama_provider import OllamaProvider
from providers.embedding_provider import OpenAIEmbeddingProvider


def get_llm_provider(model: str, api_key: str = None, ollama_host: str = None) -> LLMProvider:
    """
    Factory function to get the appropriate LLM provider for a model.

    Args:
        model: Model name (e.g., 'gpt-4', 'llama3', 'qwen2.5:3b')
        api_key: API key for cloud providers (OpenAI, Anthropic, etc.)
        ollama_host: Ollama server URL for local models

    Returns:
        Appropriate LLMProvider instance

    Raises:
        ValueError: If model type cannot be determined or API key is missing
    """
    # Local models (Ollama) - identified by presence of colons or known local model names
    local_model_indicators = [':', 'llama', 'mistral', 'qwen', 'phi', 'codellama', 'vicuna']
    is_local = any(indicator in model.lower() for indicator in local_model_indicators)

    if is_local:
        return OllamaProvider(host=ollama_host or "http://localhost:11434")
    else:
        # Default to OpenAI for cloud models
        if not api_key:
            raise ValueError(f"API key required for cloud model: {model}")
        return OpenAIProvider(api_key=api_key)


__all__ = [
    "LLMProvider",
    "EmbeddingProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "OpenAIEmbeddingProvider",
    "get_llm_provider",
]
