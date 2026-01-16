"""
Chat Storage Abstraction Layer

Thin wrapper around StorageService for backward compatibility.
Routes all storage operations to the centralized service layer.

DEPRECATED: Use StorageService directly via:
    from services.storage_service import get_storage_service
    storage = get_storage_service()

This module will be maintained for backward compatibility but new code
should use the service layer directly.
"""

from typing import Dict, Any, List
from services.storage_service import get_storage_service

# Get singleton service instance
_service = get_storage_service()


def new_chat(title: str = "New chat", model: str | None = None, user_id: int | None = None) -> Dict[str, Any]:
    """
    Create a new chat.

    DEPRECATED: Use get_storage_service().new_chat() directly.

    Args:
        title: Chat title
        model: Optional model name
        user_id: Optional user ID for multi-user support

    Returns:
        Chat dictionary
    """
    return _service.new_chat(title, model, user_id)


def load_chat(cid: str) -> Dict[str, Any] | None:
    """
    Load a chat by ID.

    DEPRECATED: Use get_storage_service().load_chat() directly.

    Args:
        cid: Chat ID

    Returns:
        Chat dictionary or None if not found
    """
    return _service.load_chat(cid)


def save_chat(chat: Dict[str, Any]) -> None:
    """
    Save/update a chat.

    DEPRECATED: Use get_storage_service().save_chat() directly.

    Args:
        chat: Chat dictionary
    """
    _service.save_chat(chat)


def list_chats(user_id: int | None = None) -> List[Dict[str, Any]]:
    """
    List all chats.

    DEPRECATED: Use get_storage_service().list_chats() directly.

    Args:
        user_id: Optional user ID to filter chats (for multi-user support)

    Returns:
        List of chat summaries
    """
    return _service.list_chats(user_id)


def rename_chat(cid: str, title: str) -> bool:
    """
    Rename a chat.

    DEPRECATED: Use get_storage_service().rename_chat() directly.

    Args:
        cid: Chat ID
        title: New title

    Returns:
        True if successful
    """
    return _service.rename_chat(cid, title)


def append_message(cid: str, role: str, content: str, model: str | None = None) -> Dict[str, Any] | None:
    """
    Append a message to a chat.

    DEPRECATED: Use get_storage_service().append_message() directly.

    Args:
        cid: Chat ID
        role: Message role (user/assistant/system)
        content: Message content
        model: Optional model name

    Returns:
        Updated chat dictionary or None if not found
    """
    return _service.append_message(cid, role, content, model)


def delete_chat(cid: str, user_id: int | None = None) -> bool:
    """
    Delete a chat.

    DEPRECATED: Use get_storage_service().delete_chat() directly.

    Args:
        cid: Chat ID
        user_id: Optional user ID for ownership verification

    Returns:
        True if successful
    """
    return _service.delete_chat(cid, user_id)
