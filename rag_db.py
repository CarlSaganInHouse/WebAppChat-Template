"""
RAG Database Module

Thin wrapper around RAGService for backward compatibility.
Routes all database operations to the centralized service layer.

DEPRECATED: Use RAGService directly via:
    from services.rag_service import get_rag_service
    rag = get_rag_service()

This module will be maintained for backward compatibility but new code
should use the service layer directly.
"""

import urllib.parse
from typing import List, Dict, Any, Tuple, Optional
from services.rag_service import get_rag_service

# Get singleton service instance
_service = get_rag_service()

# Export DB_PATH for backward compatibility
DB_PATH = _service.db_path


def get_db():
    """
    Get database connection.

    DEPRECATED: Use get_rag_service().get_conn() directly.

    Returns:
        SQLite connection
    """
    return _service.get_conn()


def init_db():
    """
    Initialize database schema.

    DEPRECATED: Use get_rag_service().init_db() directly.
    """
    _service.init_db()


def upsert_source(name: str) -> int:
    """
    Insert or get existing source.

    DEPRECATED: Use get_rag_service().upsert_source() directly.

    Args:
        name: Source name

    Returns:
        Source ID
    """
    return _service.upsert_source(name)


def add_chunks(source_id: int, chunks: List[Tuple[int, str, List[float]]]):
    """
    Add chunks with embeddings to database.

    DEPRECATED: Use get_rag_service().add_chunks() directly.

    Args:
        source_id: Source ID
        chunks: List of (order, text, embedding) tuples
    """
    _service.add_chunks(source_id, chunks)


def list_sources() -> List[Dict[str, Any]]:
    """
    List all sources with chunk counts.

    DEPRECATED: Use get_rag_service().list_sources() directly.

    Returns:
        List of source dicts
    """
    return _service.list_sources()


def delete_source(source_id: int):
    """
    Delete a source and all its chunks.

    DEPRECATED: Use get_rag_service().delete_source() directly.

    Args:
        source_id: Source ID to delete
    """
    _service.delete_source(source_id)


def _cosine(a: List[float], b: List[float]) -> float:
    """
    Calculate cosine similarity.

    DEPRECATED: Use get_rag_service()._cosine_similarity() directly.

    Args:
        a: First vector
        b: Second vector

    Returns:
        Similarity score
    """
    return _service._cosine_similarity(a, b)


def format_obsidian_link(vault_name: str, file_path: str) -> str:
    """
    Generate Obsidian deep link for a file.

    DEPRECATED: Use get_rag_service()._format_obsidian_link() directly.

    Args:
        vault_name: Name of the Obsidian vault
        file_path: Relative path to file within vault

    Returns:
        Obsidian URI scheme link
    """
    return _service._format_obsidian_link(vault_name, file_path)


def search(
    query_vec: List[float],
    top_k: int = 5,
    vault_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search for relevant chunks using cosine similarity.

    DEPRECATED: Use get_rag_service().search() directly.

    Args:
        query_vec: Query embedding vector
        top_k: Number of top results to return
        vault_name: Optional Obsidian vault name for deep links

    Returns:
        List of matching chunks with scores
    """
    return _service.search(query_vec, top_k, vault_name)


def list_presets_from_db() -> List[Dict[str, Any]]:
    """
    List all chat presets.

    DEPRECATED: Use get_rag_service().list_presets() directly.

    Returns:
        List of preset dicts
    """
    return _service.list_presets()


def get_preset_from_db(pid: int) -> Dict[str, Any]:
    """
    Get a preset by ID.

    DEPRECATED: Use get_rag_service().get_preset() directly.

    Args:
        pid: Preset ID

    Returns:
        Preset dict or None if not found
    """
    return _service.get_preset(pid)


def add_preset_to_db(label: str, system: str, temperature: float) -> int:
    """
    Add a new preset.

    DEPRECATED: Use get_rag_service().add_preset() directly.

    Args:
        label: Preset label
        system: System prompt
        temperature: Sampling temperature

    Returns:
        New preset ID
    """
    return _service.add_preset(label, system, temperature)


def update_preset_in_db(pid: int, label: str, system: str, temperature: float):
    """
    Update an existing preset.

    DEPRECATED: Use get_rag_service().update_preset() directly.

    Args:
        pid: Preset ID
        label: New label
        system: New system prompt
        temperature: New temperature
    """
    _service.update_preset(pid, label, system, temperature)


def delete_preset_from_db(pid: int):
    """
    Delete a preset.

    DEPRECATED: Use get_rag_service().delete_preset() directly.

    Args:
        pid: Preset ID
    """
    _service.delete_preset(pid)
