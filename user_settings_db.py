"""
User settings database operations.
Manages per-user configuration like vault paths and RAG collections.
"""

import sqlite3
import json
import structlog
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = structlog.get_logger()


class UserSettingsDB:
    """Database operations for user settings."""

    def __init__(self, db_path: str | Path = "chats.sqlite3"):
        """
        Initialize UserSettingsDB.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = str(db_path)

    def get_conn(self) -> sqlite3.Connection:
        """Get database connection with WAL mode enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """
        Get settings for a user.

        Args:
            user_id: User ID

        Returns:
            Dictionary with user settings, or defaults if not found
        """
        conn = self.get_conn()

        try:
            cursor = conn.execute(
                """
                SELECT
                    user_id,
                    obsidian_vault_path,
                    obsidian_shared_paths,
                    rag_collection,
                    preferences,
                    created_at,
                    updated_at
                FROM user_settings
                WHERE user_id = ?
                """,
                (user_id,)
            )

            row = cursor.fetchone()

            if row:
                return {
                    'user_id': row[0],
                    'obsidian_vault_path': row[1],
                    'obsidian_shared_paths': json.loads(row[2]) if row[2] else [],
                    'rag_collection': row[3] or 'default',
                    'preferences': json.loads(row[4]) if row[4] else {},
                    'created_at': row[5],
                    'updated_at': row[6]
                }
            else:
                # Return defaults
                return {
                    'user_id': user_id,
                    'obsidian_vault_path': None,
                    'obsidian_shared_paths': [],
                    'rag_collection': 'default',
                    'preferences': {},
                    'created_at': None,
                    'updated_at': None
                }
        finally:
            conn.close()

    def update_vault_path(self, user_id: int, vault_path: str) -> bool:
        """
        Update user's Obsidian vault path.

        Args:
            user_id: User ID
            vault_path: Path to Obsidian vault

        Returns:
            True if updated successfully
        """
        conn = self.get_conn()

        try:
            # Upsert
            conn.execute(
                """
                INSERT INTO user_settings (user_id, obsidian_vault_path)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    obsidian_vault_path = excluded.obsidian_vault_path,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, vault_path)
            )

            conn.commit()
            logger.info("vault_path_updated", user_id=user_id, vault_path=vault_path)
            return True
        finally:
            conn.close()

    def update_shared_paths(self, user_id: int, shared_paths: List[str]) -> bool:
        """
        Update user's shared Obsidian folder paths.

        Args:
            user_id: User ID
            shared_paths: List of shared folder paths

        Returns:
            True if updated successfully
        """
        conn = self.get_conn()

        try:
            shared_paths_json = json.dumps(shared_paths)

            conn.execute(
                """
                INSERT INTO user_settings (user_id, obsidian_shared_paths)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    obsidian_shared_paths = excluded.obsidian_shared_paths,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, shared_paths_json)
            )

            conn.commit()
            logger.info("shared_paths_updated", user_id=user_id, path_count=len(shared_paths))
            return True
        finally:
            conn.close()

    def update_rag_collection(self, user_id: int, collection: str) -> bool:
        """
        Update user's RAG collection.

        Args:
            user_id: User ID
            collection: Collection name ('personal', 'shared', 'both', or 'default')

        Returns:
            True if updated successfully
        """
        conn = self.get_conn()

        try:
            conn.execute(
                """
                INSERT INTO user_settings (user_id, rag_collection)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    rag_collection = excluded.rag_collection,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, collection)
            )

            conn.commit()
            logger.info("rag_collection_updated", user_id=user_id, collection=collection)
            return True
        finally:
            conn.close()

    def get_effective_vault_paths(self, user_id: int, fallback_path: Optional[str] = None) -> List[str]:
        """
        Get all vault paths user has access to (personal + shared).

        Args:
            user_id: User ID
            fallback_path: Default vault path if user hasn't configured one

        Returns:
            List of vault paths to search
        """
        settings = self.get_user_settings(user_id)

        paths = []

        # Add user's personal vault if configured
        if settings['obsidian_vault_path']:
            paths.append(settings['obsidian_vault_path'])
        elif fallback_path:
            # Use system default if no personal vault
            paths.append(fallback_path)

        # Add shared paths
        paths.extend(settings['obsidian_shared_paths'])

        # Remove duplicates while preserving order
        seen = set()
        unique_paths = []
        for path in paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        return unique_paths

    def update_preferences(self, user_id: int, preferences: Dict[str, Any]) -> bool:
        """
        Update user's preferences JSON.

        Args:
            user_id: User ID
            preferences: Preferences dictionary

        Returns:
            True if updated successfully
        """
        conn = self.get_conn()

        try:
            preferences_json = json.dumps(preferences)

            conn.execute(
                """
                INSERT INTO user_settings (user_id, preferences)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferences = excluded.preferences,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, preferences_json)
            )

            conn.commit()
            logger.info("preferences_updated", user_id=user_id)
            return True
        finally:
            conn.close()


# Singleton instance
_user_settings_db: Optional[UserSettingsDB] = None


def get_user_settings_db(db_path: str | Path = "chats.sqlite3") -> UserSettingsDB:
    """
    Get or create UserSettingsDB instance.

    Args:
        db_path: Path to SQLite database

    Returns:
        UserSettingsDB instance
    """
    global _user_settings_db
    if _user_settings_db is None:
        _user_settings_db = UserSettingsDB(db_path)
    return _user_settings_db
