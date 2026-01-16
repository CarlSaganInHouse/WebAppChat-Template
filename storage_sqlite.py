"""
SQLite-based chat storage implementation.
Provides the same API as storage.py but uses SQLite instead of JSON files.

This module mirrors the storage.py API exactly to allow seamless switching
via the use_sqlite_chats feature flag.
"""

import uuid
import structlog
from typing import Dict, Any, List, Optional
from chat_db import get_chat_db

logger = structlog.get_logger()


def new_chat(title: str = "New chat") -> Dict[str, Any]:
    """
    Create a new chat in SQLite.

    Args:
        title: Chat title

    Returns:
        Chat dictionary (matches JSON format)
    """
    from context_aware import initialize_context
    import json

    db = get_chat_db()
    chat_id = uuid.uuid4().hex[:12]

    # Create chat in database
    db.create_chat(chat_id=chat_id, title=title)

    # Initialize context_memory for this chat
    conn = db.get_conn()
    try:
        context_memory = initialize_context()
        conn.execute(
            "UPDATE chats SET context_memory = ? WHERE id = ?",
            (json.dumps(context_memory), chat_id)
        )
        conn.commit()
    finally:
        conn.close()

    # Return the created chat (matches storage.py format)
    chat = db.get_chat(chat_id)
    logger.info("chat_created_sqlite", chat_id=chat_id, title=title)
    return chat


def load_chat(cid: str) -> Dict[str, Any] | None:
    """
    Load a chat from SQLite.

    Args:
        cid: Chat ID

    Returns:
        Chat dictionary or None if not found
    """
    db = get_chat_db()
    chat = db.get_chat(cid)

    if chat:
        logger.debug("chat_loaded_sqlite", chat_id=cid)
    else:
        logger.warning("chat_not_found_sqlite", chat_id=cid)

    return chat


def save_chat(chat: Dict[str, Any]) -> None:
    """
    Save a chat to SQLite.

    This updates the chat metadata. For adding messages, use append_message().

    Args:
        chat: Chat dictionary (with id, title, model, meta, etc.)
    """
    db = get_chat_db()
    chat_id = chat["id"]

    # Update chat metadata
    meta = chat.get("meta", {})
    db.update_chat(
        chat_id=chat_id,
        title=chat.get("title"),
        model=chat.get("model"),
        budget_usd=meta.get("budget_usd"),
        spent_usd=meta.get("spent_usd"),
        context_memory=meta.get("context_memory")  # Save context_memory
    )

    # Update tags (simple approach: clear and re-add)
    tags = meta.get("tags", [])
    if tags:
        # Remove existing tags and add new ones
        # (This is simple but not optimal; could be improved later)
        all_existing = db.get_chat(chat_id)
        if all_existing:
            existing_tags = all_existing.get("meta", {}).get("tags", [])
            tags_to_remove = [t for t in existing_tags if t not in tags]
            tags_to_add = [t for t in tags if t not in existing_tags]

            if tags_to_remove:
                db.remove_tags(chat_id, tags_to_remove)
            if tags_to_add:
                db.add_tags(chat_id, tags_to_add)

    logger.debug("chat_saved_sqlite", chat_id=chat_id)


def list_chats() -> List[Dict[str, Any]]:
    """
    List all chats from SQLite.

    Returns:
        List of chat summaries (sorted by updated_at, newest first)
    """
    db = get_chat_db()
    chats = db.list_chats()
    logger.debug("chats_listed_sqlite", count=len(chats))
    return chats


def rename_chat(cid: str, title: str) -> bool:
    """
    Rename a chat in SQLite.

    Args:
        cid: Chat ID
        title: New title

    Returns:
        True if successful, False if chat not found
    """
    db = get_chat_db()
    title = title.strip()

    if not title:
        # Don't rename to empty string
        chat = db.get_chat(cid)
        if chat:
            title = chat["title"]
        else:
            return False

    success = db.update_chat(cid, title=title)

    if success:
        logger.info("chat_renamed_sqlite", chat_id=cid, new_title=title)
    else:
        logger.warning("chat_rename_failed_sqlite", chat_id=cid)

    return success


def append_message(cid: str, role: str, content: str, model: str | None = None) -> Dict[str, Any] | None:
    """
    Append a message to a chat in SQLite.

    Args:
        cid: Chat ID
        role: Message role (user/assistant/system)
        content: Message content
        model: Optional model name

    Returns:
        Updated chat dictionary or None if chat not found
    """
    db = get_chat_db()

    # Add the message
    success = db.add_message(cid, role, content, model)

    if not success:
        logger.warning("message_append_failed_sqlite", chat_id=cid)
        return None

    # Return the updated chat
    chat = db.get_chat(cid)
    logger.info("message_appended_sqlite", chat_id=cid, role=role, model=model)
    return chat


def delete_chat(cid: str) -> bool:
    """
    Delete a chat from SQLite.

    Args:
        cid: Chat ID

    Returns:
        True if successful, False if not found
    """
    # Basic security: prevent path traversal (even though SQLite doesn't have this issue)
    # Keep same validation as storage.py for consistency
    if '/' in cid or '\\' in cid or '..' in cid:
        logger.warning("chat_delete_blocked_sqlite", chat_id=cid, reason="invalid_id")
        return False

    db = get_chat_db()
    success = db.delete_chat(cid)

    if success:
        logger.info("chat_deleted_sqlite", chat_id=cid)
    else:
        logger.warning("chat_delete_failed_sqlite", chat_id=cid)

    return success
