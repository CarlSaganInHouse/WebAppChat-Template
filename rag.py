"""
RAG (Retrieval-Augmented Generation) Module

Thin wrapper around RAGService for backward compatibility.
Routes all RAG operations to the centralized service layer.

DEPRECATED: Use RAGService directly via:
    from services.rag_service import get_rag_service
    rag = get_rag_service()

This module will be maintained for backward compatibility but new code
should use the service layer directly.
"""

from typing import List
from services.rag_service import get_rag_service

# Get singleton service instance
_service = get_rag_service()


def tokenize_len(text: str, model_for_tokens: str = "gpt-4o-mini") -> int:
    """
    Count tokens in text.

    DEPRECATED: Use get_rag_service().tokenize_len() directly.

    Args:
        text: Text to count tokens for
        model_for_tokens: Model to use for tokenization

    Returns:
        Number of tokens
    """
    return _service.tokenize_len(text, model_for_tokens)


def chunk_text(
    text: str,
    model_for_tokens: str = "gpt-4o-mini",
    max_tokens: int | None = None
) -> List[str]:
    """
    Split text into chunks based on token limits.

    DEPRECATED: Use get_rag_service().chunk_text() directly.

    Args:
        text: Text to chunk
        model_for_tokens: Model to use for tokenization
        max_tokens: Maximum tokens per chunk

    Returns:
        List of text chunks
    """
    return _service.chunk_text(text, model_for_tokens, max_tokens)


def embed_texts(texts: List[str], api_key: str | None = None) -> List[List[float]]:
    """
    Generate embeddings for texts using OpenAI.

    DEPRECATED: Use get_rag_service().embed_texts() directly.

    Args:
        texts: List of text strings to embed
        api_key: Optional OpenAI API key

    Returns:
        List of embedding vectors
    """
    # Note: api_key parameter not directly supported in service
    # Service uses config settings, but this maintains compatibility
    if api_key:
        # Create temporary service instance with custom API key
        from services.rag_service import RAGService
        temp_service = RAGService(api_key=api_key)
        return temp_service.embed_texts(texts)
    else:
        return _service.embed_texts(texts)
