"""
Chat Storage Service

Centralized service for all chat and message storage operations.
Supports multiple backends (JSON files, SQLite) with a unified interface.

This service encapsulates:
- Chat CRUD operations
- Message management
- Tag management
- Full-text search
- Storage backend abstraction
"""

import os
import json
import time
import uuid
import sqlite3
import structlog
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = structlog.get_logger()


class StorageService:
    """
    Unified storage service for chat and message operations.

    Handles both JSON file storage and SQLite storage based on configuration.
    Provides a clean, testable interface for all storage operations.
    """

    def __init__(self, use_sqlite: bool = False, db_path: str = "chats.sqlite3", json_dir: str = "chats"):
        """
        Initialize storage service.

        Args:
            use_sqlite: Whether to use SQLite backend (default: False for JSON)
            db_path: Path to SQLite database file
            json_dir: Directory for JSON file storage
        """
        self.use_sqlite = use_sqlite
        self.db_path = db_path
        self.json_dir = json_dir

        # Initialize storage backend
        if self.use_sqlite:
            self._init_sqlite()
        else:
            self._init_json()

    def _init_json(self) -> None:
        """Initialize JSON file storage."""
        os.makedirs(self.json_dir, exist_ok=True)

    def _init_sqlite(self) -> None:
        """Initialize SQLite database."""
        from chat_db import ChatDatabase
        self.db = ChatDatabase(self.db_path)

    def _json_path(self, chat_id: str) -> str:
        """Get JSON file path for a chat."""
        return os.path.join(self.json_dir, f"{chat_id}.json")

    # ========================================================================
    # CHAT OPERATIONS
    # ========================================================================

    def new_chat(self, title: str = "New chat", model: Optional[str] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Create a new chat.

        Args:
            title: Chat title
            model: Optional model name
            user_id: Optional user ID for multi-user support

        Returns:
            Chat dictionary with metadata and empty messages list
        """
        if self.use_sqlite:
            return self._new_chat_sqlite(title, model, user_id)
        else:
            return self._new_chat_json(title, model)

    def _new_chat_json(self, title: str, model: Optional[str]) -> Dict[str, Any]:
        """Create new chat in JSON storage."""
        from context_aware import initialize_context

        chat_id = uuid.uuid4().hex[:12]
        chat = {
            "id": chat_id,
            "title": title,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "model": model,
            "messages": [],
            "meta": {
                "budget_usd": None,
                "spent_usd": 0.0,
                "tags": [],
                "context_memory": initialize_context()
            }
        }
        self.save_chat(chat)
        logger.info("chat_created_json", chat_id=chat_id, title=title)
        return chat

    def _new_chat_sqlite(self, title: str, model: Optional[str], user_id: Optional[int] = None) -> Dict[str, Any]:
        """Create new chat in SQLite storage."""
        from context_aware import initialize_context

        chat_id = uuid.uuid4().hex[:12]

        # Create chat in database
        self.db.create_chat(chat_id=chat_id, title=title, user_id=user_id)

        # Initialize context_memory
        conn = self.db.get_conn()
        try:
            context_memory = initialize_context()
            conn.execute(
                "UPDATE chats SET context_memory = ?, model = ? WHERE id = ?",
                (json.dumps(context_memory), model, chat_id)
            )
            conn.commit()
        finally:
            conn.close()

        chat = self.db.get_chat(chat_id)
        logger.info("chat_created_sqlite", chat_id=chat_id, title=title, user_id=user_id)
        return chat

    def load_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a chat by ID.

        Args:
            chat_id: Chat identifier

        Returns:
            Chat dictionary or None if not found
        """
        if self.use_sqlite:
            return self._load_chat_sqlite(chat_id)
        else:
            return self._load_chat_json(chat_id)

    def _load_chat_json(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Load chat from JSON storage."""
        path = self._json_path(chat_id)
        if not os.path.exists(path):
            logger.warning("chat_not_found_json", chat_id=chat_id)
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                chat = json.load(f)
            logger.debug("chat_loaded_json", chat_id=chat_id)
            return chat
        except (json.JSONDecodeError, IOError) as e:
            logger.error("chat_load_error_json", chat_id=chat_id, error=str(e))
            return None

    def _load_chat_sqlite(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Load chat from SQLite storage."""
        chat = self.db.get_chat(chat_id)
        if chat:
            logger.debug("chat_loaded_sqlite", chat_id=chat_id)
        else:
            logger.warning("chat_not_found_sqlite", chat_id=chat_id)
        return chat

    def save_chat(self, chat: Dict[str, Any]) -> None:
        """
        Save/update a chat.

        Args:
            chat: Chat dictionary with all metadata
        """
        if self.use_sqlite:
            self._save_chat_sqlite(chat)
        else:
            self._save_chat_json(chat)

    def _save_chat_json(self, chat: Dict[str, Any]) -> None:
        """Save chat to JSON storage."""
        chat["updated_at"] = int(time.time())
        path = self._json_path(chat["id"])

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(chat, f, indent=2, ensure_ascii=False)
            logger.debug("chat_saved_json", chat_id=chat["id"])
        except IOError as e:
            logger.error("chat_save_error_json", chat_id=chat["id"], error=str(e))

    def _save_chat_sqlite(self, chat: Dict[str, Any]) -> None:
        """Save chat to SQLite storage."""
        chat_id = chat["id"]
        meta = chat.get("meta", {})

        # Update chat metadata
        self.db.update_chat(
            chat_id=chat_id,
            title=chat.get("title"),
            model=chat.get("model"),
            budget_usd=meta.get("budget_usd"),
            spent_usd=meta.get("spent_usd"),
            context_memory=meta.get("context_memory")
        )

        # Update tags
        tags = meta.get("tags", [])
        if tags:
            existing_chat = self.db.get_chat(chat_id)
            if existing_chat:
                existing_tags = existing_chat.get("meta", {}).get("tags", [])
                tags_to_remove = [t for t in existing_tags if t not in tags]
                tags_to_add = [t for t in tags if t not in existing_tags]

                if tags_to_remove:
                    self.db.remove_tags(chat_id, tags_to_remove)
                if tags_to_add:
                    self.db.add_tags(chat_id, tags_to_add)

        logger.debug("chat_saved_sqlite", chat_id=chat_id)

    def list_chats(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List all chats.

        Args:
            user_id: Optional user ID to filter chats (for multi-user support)

        Returns:
            List of chat summaries sorted by updated_at (newest first)
        """
        if self.use_sqlite:
            return self._list_chats_sqlite(user_id)
        else:
            return self._list_chats_json()

    def _list_chats_json(self) -> List[Dict[str, Any]]:
        """List all chats from JSON storage."""
        items = []

        if not os.path.exists(self.json_dir):
            return items

        for filename in os.listdir(self.json_dir):
            if not filename.endswith(".json"):
                continue

            path = os.path.join(self.json_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    chat = json.load(f)
                items.append({
                    "id": chat["id"],
                    "title": chat.get("title", "New chat"),
                    "created_at": chat.get("created_at", 0),
                    "updated_at": chat.get("updated_at", 0),
                    "tags": chat.get("meta", {}).get("tags", [])
                })
            except (json.JSONDecodeError, KeyError, IOError):
                # Skip corrupted files
                continue

        items.sort(key=lambda x: x["updated_at"], reverse=True)
        logger.debug("chats_listed_json", count=len(items))
        return items

    def _list_chats_sqlite(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """List all chats from SQLite storage."""
        chats = self.db.list_chats(user_id=user_id)
        logger.debug("chats_listed_sqlite", count=len(chats), user_id=user_id)
        return chats

    def rename_chat(self, chat_id: str, title: str) -> bool:
        """
        Rename a chat.

        Args:
            chat_id: Chat identifier
            title: New title

        Returns:
            True if successful, False if chat not found
        """
        if self.use_sqlite:
            return self._rename_chat_sqlite(chat_id, title)
        else:
            return self._rename_chat_json(chat_id, title)

    def _rename_chat_json(self, chat_id: str, title: str) -> bool:
        """Rename chat in JSON storage."""
        chat = self.load_chat(chat_id)
        if not chat:
            return False

        chat["title"] = title.strip() or chat["title"]
        self.save_chat(chat)
        logger.info("chat_renamed_json", chat_id=chat_id, new_title=title)
        return True

    def _rename_chat_sqlite(self, chat_id: str, title: str) -> bool:
        """Rename chat in SQLite storage."""
        title = title.strip()

        if not title:
            # Don't rename to empty string
            chat = self.db.get_chat(chat_id)
            if chat:
                title = chat["title"]
            else:
                return False

        success = self.db.update_chat(chat_id, title=title)

        if success:
            logger.info("chat_renamed_sqlite", chat_id=chat_id, new_title=title)
        else:
            logger.warning("chat_rename_failed_sqlite", chat_id=chat_id)

        return success

    def delete_chat(self, chat_id: str, user_id: Optional[int] = None) -> bool:
        """
        Delete a chat.

        Args:
            chat_id: Chat identifier
            user_id: Optional user ID for ownership verification

        Returns:
            True if successful, False if not found or invalid ID
        """
        # Security: prevent path traversal
        if '/' in chat_id or '\\' in chat_id or '..' in chat_id:
            logger.warning("chat_delete_blocked", chat_id=chat_id, reason="invalid_id")
            return False

        if self.use_sqlite:
            return self._delete_chat_sqlite(chat_id, user_id)
        else:
            return self._delete_chat_json(chat_id)

    def _delete_chat_json(self, chat_id: str) -> bool:
        """Delete chat from JSON storage."""
        path = self._json_path(chat_id)
        if not os.path.exists(path):
            return False

        try:
            os.remove(path)
            logger.info("chat_deleted_json", chat_id=chat_id)
            return True
        except OSError as e:
            logger.error("chat_delete_error_json", chat_id=chat_id, error=str(e))
            return False

    def _delete_chat_sqlite(self, chat_id: str, user_id: Optional[int] = None) -> bool:
        """Delete chat from SQLite storage."""
        success = self.db.delete_chat(chat_id, user_id=user_id)

        if success:
            logger.info("chat_deleted_sqlite", chat_id=chat_id, user_id=user_id)
        else:
            logger.warning("chat_delete_failed_sqlite", chat_id=chat_id, user_id=user_id)

        return success

    # ========================================================================
    # ARCHIVE OPERATIONS
    # ========================================================================

    def archive_chat(self, chat_id: str, user_id: Optional[int] = None) -> bool:
        """
        Archive a chat (soft delete).

        Args:
            chat_id: Chat identifier
            user_id: Optional user ID for ownership verification

        Returns:
            True if successful, False if not found or permission denied
        """
        # Security: prevent path traversal
        if '/' in chat_id or '\\' in chat_id or '..' in chat_id:
            logger.warning("chat_archive_blocked", chat_id=chat_id, reason="invalid_id")
            return False

        if self.use_sqlite:
            success = self.db.archive_chat(chat_id, user_id=user_id)
            if success:
                logger.info("chat_archived", chat_id=chat_id, user_id=user_id)
            else:
                logger.warning("chat_archive_failed", chat_id=chat_id, user_id=user_id)
            return success
        else:
            # For JSON, add archived_at to metadata
            chat = self.load_chat(chat_id)
            if not chat:
                return False
            chat.setdefault("meta", {})["archived_at"] = int(time.time())
            self.save_chat(chat)
            logger.info("chat_archived_json", chat_id=chat_id)
            return True

    def unarchive_chat(self, chat_id: str, user_id: Optional[int] = None) -> bool:
        """
        Unarchive a chat (restore from archive).

        Args:
            chat_id: Chat identifier
            user_id: Optional user ID for ownership verification

        Returns:
            True if successful, False if not found or permission denied
        """
        # Security: prevent path traversal
        if '/' in chat_id or '\\' in chat_id or '..' in chat_id:
            logger.warning("chat_unarchive_blocked", chat_id=chat_id, reason="invalid_id")
            return False

        if self.use_sqlite:
            success = self.db.unarchive_chat(chat_id, user_id=user_id)
            if success:
                logger.info("chat_unarchived", chat_id=chat_id, user_id=user_id)
            else:
                logger.warning("chat_unarchive_failed", chat_id=chat_id, user_id=user_id)
            return success
        else:
            # For JSON, remove archived_at from metadata
            chat = self.load_chat(chat_id)
            if not chat:
                return False
            if "meta" in chat and "archived_at" in chat["meta"]:
                del chat["meta"]["archived_at"]
                self.save_chat(chat)
            logger.info("chat_unarchived_json", chat_id=chat_id)
            return True

    def list_archived_chats(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List all archived chats.

        Args:
            user_id: Optional user ID to filter chats

        Returns:
            List of archived chat summaries
        """
        if self.use_sqlite:
            chats = self.db.list_archived_chats(user_id=user_id)
            logger.debug("archived_chats_listed", count=len(chats), user_id=user_id)
            return chats
        else:
            # For JSON, filter by archived_at in meta
            all_items = []
            if not os.path.exists(self.json_dir):
                return all_items

            for filename in os.listdir(self.json_dir):
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(self.json_dir, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        chat = json.load(f)
                    archived_at = chat.get("meta", {}).get("archived_at")
                    if archived_at:
                        all_items.append({
                            "id": chat["id"],
                            "title": chat.get("title", "New chat"),
                            "created_at": chat.get("created_at", 0),
                            "updated_at": chat.get("updated_at", 0),
                            "tags": chat.get("meta", {}).get("tags", []),
                            "archived_at": archived_at
                        })
                except (json.JSONDecodeError, KeyError, IOError):
                    continue

            all_items.sort(key=lambda x: x.get("archived_at", 0), reverse=True)
            logger.debug("archived_chats_listed_json", count=len(all_items))
            return all_items

    def bulk_archive_chats(self, chat_ids: List[str], user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Archive multiple chats at once.

        Args:
            chat_ids: List of chat IDs to archive
            user_id: Optional user ID for ownership verification

        Returns:
            Dict with archived count and failed IDs
        """
        archived = 0
        failed = []

        for chat_id in chat_ids:
            if self.archive_chat(chat_id, user_id=user_id):
                archived += 1
            else:
                failed.append(chat_id)

        logger.info("bulk_archive_complete", archived=archived, failed=len(failed))
        return {"archived": archived, "failed": failed}

    def bulk_unarchive_chats(self, chat_ids: List[str], user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Unarchive multiple chats at once.

        Args:
            chat_ids: List of chat IDs to unarchive
            user_id: Optional user ID for ownership verification

        Returns:
            Dict with unarchived count and failed IDs
        """
        unarchived = 0
        failed = []

        for chat_id in chat_ids:
            if self.unarchive_chat(chat_id, user_id=user_id):
                unarchived += 1
            else:
                failed.append(chat_id)

        logger.info("bulk_unarchive_complete", unarchived=unarchived, failed=len(failed))
        return {"unarchived": unarchived, "failed": failed}

    # ========================================================================
    # MESSAGE OPERATIONS
    # ========================================================================

    def append_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        model: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Append a message to a chat.

        Args:
            chat_id: Chat identifier
            role: Message role (user/assistant/system)
            content: Message content
            model: Optional model name

        Returns:
            Updated chat dictionary or None if chat not found
        """
        if self.use_sqlite:
            return self._append_message_sqlite(chat_id, role, content, model)
        else:
            return self._append_message_json(chat_id, role, content, model)

    def _append_message_json(
        self,
        chat_id: str,
        role: str,
        content: str,
        model: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Append message to JSON storage."""
        chat = self.load_chat(chat_id)
        if not chat:
            logger.warning("message_append_failed_json", chat_id=chat_id, reason="chat_not_found")
            return None

        # Create message
        msg = {
            "role": role,
            "content": content,
            "ts": int(time.time())
        }
        if model:
            msg["model"] = model
            chat["model"] = model  # Track most recent model

        chat["messages"].append(msg)
        self.save_chat(chat)

        logger.info("message_appended_json", chat_id=chat_id, role=role, model=model)
        return chat

    def _append_message_sqlite(
        self,
        chat_id: str,
        role: str,
        content: str,
        model: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Append message to SQLite storage."""
        success = self.db.add_message(chat_id, role, content, model)

        if not success:
            logger.warning("message_append_failed_sqlite", chat_id=chat_id)
            return None

        chat = self.db.get_chat(chat_id)
        logger.info("message_appended_sqlite", chat_id=chat_id, role=role, model=model)
        return chat

    # ========================================================================
    # TAG OPERATIONS (SQLite only)
    # ========================================================================

    def add_tags(self, chat_id: str, tags: List[str]) -> bool:
        """
        Add tags to a chat.

        Args:
            chat_id: Chat identifier
            tags: List of tags to add

        Returns:
            True if successful, False otherwise
        """
        if self.use_sqlite:
            success = self.db.add_tags(chat_id, tags)
            if success:
                logger.info("tags_added_sqlite", chat_id=chat_id, tags=tags)
            return success
        else:
            # For JSON, update via save_chat
            chat = self.load_chat(chat_id)
            if not chat:
                return False

            existing_tags = set(chat.get("meta", {}).get("tags", []))
            existing_tags.update(tags)
            chat.setdefault("meta", {})["tags"] = list(existing_tags)
            self.save_chat(chat)
            logger.info("tags_added_json", chat_id=chat_id, tags=tags)
            return True

    def remove_tags(self, chat_id: str, tags: List[str]) -> bool:
        """
        Remove tags from a chat.

        Args:
            chat_id: Chat identifier
            tags: List of tags to remove

        Returns:
            True if successful, False otherwise
        """
        if self.use_sqlite:
            success = self.db.remove_tags(chat_id, tags)
            if success:
                logger.info("tags_removed_sqlite", chat_id=chat_id, tags=tags)
            return success
        else:
            # For JSON, update via save_chat
            chat = self.load_chat(chat_id)
            if not chat:
                return False

            existing_tags = set(chat.get("meta", {}).get("tags", []))
            existing_tags.difference_update(tags)
            chat.setdefault("meta", {})["tags"] = list(existing_tags)
            self.save_chat(chat)
            logger.info("tags_removed_json", chat_id=chat_id, tags=tags)
            return True

    def get_chats_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """
        Get all chats with a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of chat summaries
        """
        if self.use_sqlite:
            chats = self.db.get_chats_by_tag(tag)
            logger.debug("chats_by_tag_sqlite", tag=tag, count=len(chats))
            return chats
        else:
            # For JSON, filter in memory
            all_chats = self.list_chats()
            matching = []

            for chat_summary in all_chats:
                if tag in chat_summary.get("tags", []):
                    matching.append(chat_summary)

            logger.debug("chats_by_tag_json", tag=tag, count=len(matching))
            return matching

    # ========================================================================
    # SEARCH OPERATIONS (SQLite only)
    # ========================================================================

    def search_messages(self, query: str, limit: int = 20, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Full-text search across all messages.

        Args:
            query: Search query
            limit: Maximum number of results
            user_id: Optional user ID to filter search results

        Returns:
            List of matching messages with metadata
        """
        if self.use_sqlite:
            results = self.db.search_messages(query, limit, user_id=user_id)
            logger.info("messages_searched_sqlite", query=query, results=len(results), user_id=user_id)
            return results
        else:
            # For JSON, simple substring search (not efficient)
            logger.warning("search_not_implemented_json", query=query)
            return []


# Singleton instance for backward compatibility
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """
    Get the singleton storage service instance.

    Returns:
        StorageService instance configured from settings
    """
    global _storage_service

    if _storage_service is None:
        try:
            from config import settings
            use_sqlite = settings.use_sqlite_chats
        except (ImportError, AttributeError):
            use_sqlite = False

        _storage_service = StorageService(use_sqlite=use_sqlite)

    return _storage_service
