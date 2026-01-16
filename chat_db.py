"""
SQLite database layer for chat storage.
Provides structured storage with better query capabilities than JSON files.

Schema:
- chats: Chat metadata (id, title, model, timestamps, budget)
- messages: Individual messages in chats
- chat_tags: Tags associated with chats
"""

import sqlite3
import time
import structlog
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = structlog.get_logger()


class ChatDatabase:
    """
    SQLite database manager for chat storage.
    Follows the same patterns as rag_db.py for consistency.
    """

    def __init__(self, db_path: str | Path = "chats.sqlite3"):
        """
        Initialize chat database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = str(db_path)
        self.init_db()

    def get_conn(self) -> sqlite3.Connection:
        """Get a database connection with WAL mode enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def init_db(self) -> None:
        """
        Initialize database schema if not exists.
        Creates tables for chats, messages, and tags.
        """
        conn = self.get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                budget_usd REAL,
                spent_usd REAL DEFAULT 0.0,
                context_memory TEXT,
                chat_mode TEXT DEFAULT 'agentic'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                model TEXT,
                FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chat_tags (
                chat_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY(chat_id, tag),
                FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
            CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at);
            CREATE INDEX IF NOT EXISTS idx_chat_tags_tag ON chat_tags(tag);

            -- FTS5 virtual table for full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                chat_id UNINDEXED,
                role UNINDEXED,
                content,
                content='messages',
                content_rowid='id'
            );

            -- Triggers to keep FTS in sync with messages table
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, chat_id, role, content)
                VALUES (new.id, new.chat_id, new.role, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                DELETE FROM messages_fts WHERE rowid = old.id;
            END;

            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                DELETE FROM messages_fts WHERE rowid = old.id;
                INSERT INTO messages_fts(rowid, chat_id, role, content)
                VALUES (new.id, new.chat_id, new.role, new.content);
            END;
        """)
        conn.commit()

        # Migration: Add chat_mode column if it doesn't exist (for existing databases)
        try:
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'chat_mode' not in columns:
                conn.execute("ALTER TABLE chats ADD COLUMN chat_mode TEXT DEFAULT 'agentic'")
                conn.commit()
                logger.info("chat_db_migration", added_column="chat_mode")
        except Exception as e:
            logger.warning("chat_db_migration_check_failed", error=str(e))

        # Migration: Add archived_at column if it doesn't exist
        try:
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'archived_at' not in columns:
                conn.execute("ALTER TABLE chats ADD COLUMN archived_at INTEGER DEFAULT NULL")
                conn.commit()
                logger.info("chat_db_migration", added_column="archived_at")
        except Exception as e:
            logger.warning("chat_db_migration_archived_at_failed", error=str(e))

        conn.close()
        logger.info("chat_db_initialized", db_path=self.db_path)

    def create_chat(
        self,
        chat_id: str,
        title: str,
        model: Optional[str] = None,
        budget_usd: Optional[float] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[int] = None
    ) -> None:
        """
        Create a new chat.

        Args:
            chat_id: Unique chat identifier
            title: Chat title
            model: Optional model name
            budget_usd: Optional budget limit in USD
            tags: Optional list of tags
            user_id: ID of user who owns this chat (recommended for multi-user setups)

        Raises:
            sqlite3.IntegrityError: If chat_id already exists
        """
        conn = self.get_conn()
        now = int(time.time())

        try:
            # Check if user_id column exists (for migration compatibility)
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            has_user_id = 'user_id' in columns

            if has_user_id:
                conn.execute(
                    """INSERT INTO chats (id, title, model, created_at, updated_at, budget_usd, spent_usd, user_id)
                       VALUES (?, ?, ?, ?, ?, ?, 0.0, ?)""",
                    (chat_id, title, model, now, now, budget_usd, user_id)
                )
            else:
                # Backward compatibility: create without user_id if column doesn't exist
                conn.execute(
                    """INSERT INTO chats (id, title, model, created_at, updated_at, budget_usd, spent_usd)
                       VALUES (?, ?, ?, ?, ?, ?, 0.0)""",
                    (chat_id, title, model, now, now, budget_usd)
                )

            # Add tags if provided
            if tags:
                conn.executemany(
                    "INSERT INTO chat_tags (chat_id, tag) VALUES (?, ?)",
                    [(chat_id, tag) for tag in tags]
                )

            conn.commit()
            logger.info("chat_created", chat_id=chat_id, title=title, tags=tags, user_id=user_id)
        finally:
            conn.close()

    def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a chat with all its messages and metadata.

        Args:
            chat_id: Chat identifier

        Returns:
            Dictionary with chat data (matching JSON format) or None if not found
        """
        conn = self.get_conn()

        try:
            # Get chat metadata (including context_memory)
            try:
                chat_row = conn.execute(
                    "SELECT id, title, model, created_at, updated_at, budget_usd, spent_usd, context_memory FROM chats WHERE id = ?",
                    (chat_id,)
                ).fetchone()
            except Exception:
                # Fallback for tables without context_memory column
                chat_row = conn.execute(
                    "SELECT id, title, model, created_at, updated_at, budget_usd, spent_usd FROM chats WHERE id = ?",
                    (chat_id,)
                ).fetchone()
                if chat_row:
                    chat_row = chat_row + (None,)  # Add None for context_memory

            if not chat_row:
                return None

            # Get messages
            message_rows = conn.execute(
                "SELECT role, content, timestamp, model FROM messages WHERE chat_id = ? ORDER BY timestamp ASC",
                (chat_id,)
            ).fetchall()

            # Get tags
            tag_rows = conn.execute(
                "SELECT tag FROM chat_tags WHERE chat_id = ?",
                (chat_id,)
            ).fetchall()

            # Parse context_memory if present
            import json
            context_memory = {}
            if len(chat_row) > 7 and chat_row[7]:
                try:
                    context_memory = json.loads(chat_row[7]) if isinstance(chat_row[7], str) else chat_row[7]
                except (json.JSONDecodeError, TypeError):
                    context_memory = {}

            # Build chat object (matches JSON format)
            chat = {
                "id": chat_row[0],
                "title": chat_row[1],
                "model": chat_row[2],
                "created_at": chat_row[3],
                "updated_at": chat_row[4],
                "messages": [
                    {
                        "role": msg[0],
                        "content": msg[1],
                        "ts": msg[2],
                        **({"model": msg[3]} if msg[3] else {})
                    }
                    for msg in message_rows
                ],
                "meta": {
                    "budget_usd": chat_row[5],
                    "spent_usd": chat_row[6],
                    "tags": [tag[0] for tag in tag_rows],
                    "context_memory": context_memory
                }
            }

            return chat
        finally:
            conn.close()

    def update_chat(
        self,
        chat_id: str,
        title: Optional[str] = None,
        model: Optional[str] = None,
        budget_usd: Optional[float] = None,
        spent_usd: Optional[float] = None,
        context_memory: Optional[dict] = None
    ) -> bool:
        """
        Update chat metadata.

        Args:
            chat_id: Chat identifier
            title: New title (if provided)
            model: New model (if provided)
            budget_usd: New budget (if provided)
            spent_usd: New spent amount (if provided)
            context_memory: Context memory dict (if provided)

        Returns:
            True if chat was found and updated, False otherwise
        """
        conn = self.get_conn()
        now = int(time.time())

        try:
            # Build dynamic UPDATE query
            updates = ["updated_at = ?"]
            params = [now]

            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if model is not None:
                updates.append("model = ?")
                params.append(model)
            if budget_usd is not None:
                updates.append("budget_usd = ?")
                params.append(budget_usd)
            if spent_usd is not None:
                updates.append("spent_usd = ?")
                params.append(spent_usd)
            if context_memory is not None:
                import json
                updates.append("context_memory = ?")
                params.append(json.dumps(context_memory))

            params.append(chat_id)

            cursor = conn.execute(
                f"UPDATE chats SET {', '.join(updates)} WHERE id = ?",
                params
            )

            success = cursor.rowcount > 0
            conn.commit()

            if success:
                logger.info("chat_updated", chat_id=chat_id, fields=len(updates))

            return success
        finally:
            conn.close()

    def get_chat_mode(self, chat_id: str) -> str:
        """
        Get the chat mode for a chat.

        Args:
            chat_id: Chat identifier

        Returns:
            Chat mode ('agentic' or 'chat'), defaults to 'agentic'
        """
        conn = self.get_conn()

        try:
            # Check if chat_mode column exists
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'chat_mode' not in columns:
                return 'agentic'

            row = conn.execute(
                "SELECT chat_mode FROM chats WHERE id = ?",
                (chat_id,)
            ).fetchone()

            if row and row[0]:
                return row[0]
            return 'agentic'
        finally:
            conn.close()

    def set_chat_mode(self, chat_id: str, mode: str) -> bool:
        """
        Set the chat mode for a chat.

        Args:
            chat_id: Chat identifier
            mode: Chat mode ('agentic' or 'chat')

        Returns:
            True if mode was set, False if chat doesn't exist or invalid mode
        """
        if mode not in ('agentic', 'chat'):
            return False

        conn = self.get_conn()

        try:
            # Check if chat_mode column exists
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'chat_mode' not in columns:
                return False

            cursor = conn.execute(
                "UPDATE chats SET chat_mode = ? WHERE id = ?",
                (mode, chat_id)
            )

            success = cursor.rowcount > 0
            conn.commit()

            if success:
                logger.info("chat_mode_set", chat_id=chat_id, mode=mode)

            return success
        finally:
            conn.close()

    def archive_chat(self, chat_id: str, user_id: Optional[int] = None) -> bool:
        """
        Archive a chat (soft delete) by setting archived_at timestamp.

        Args:
            chat_id: Chat identifier
            user_id: User ID for ownership verification (optional)

        Returns:
            True if chat was archived, False if not found or permission denied
        """
        conn = self.get_conn()

        try:
            # Check if user_id column exists
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            has_user_id = 'user_id' in columns

            # Verify ownership if user_id provided and column exists
            if has_user_id and user_id is not None:
                cursor = conn.execute(
                    "SELECT id FROM chats WHERE id = ? AND user_id = ?",
                    (chat_id, user_id)
                )
                if not cursor.fetchone():
                    logger.warning("chat_archive_denied", chat_id=chat_id, user_id=user_id)
                    return False

            now = int(time.time())
            cursor = conn.execute(
                "UPDATE chats SET archived_at = ? WHERE id = ? AND archived_at IS NULL",
                (now, chat_id)
            )
            success = cursor.rowcount > 0
            conn.commit()

            if success:
                logger.info("chat_archived", chat_id=chat_id, user_id=user_id)

            return success
        finally:
            conn.close()

    def unarchive_chat(self, chat_id: str, user_id: Optional[int] = None) -> bool:
        """
        Unarchive a chat by clearing archived_at timestamp.

        Args:
            chat_id: Chat identifier
            user_id: User ID for ownership verification (optional)

        Returns:
            True if chat was unarchived, False if not found or permission denied
        """
        conn = self.get_conn()

        try:
            # Check if user_id column exists
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            has_user_id = 'user_id' in columns

            # Verify ownership if user_id provided and column exists
            if has_user_id and user_id is not None:
                cursor = conn.execute(
                    "SELECT id FROM chats WHERE id = ? AND user_id = ?",
                    (chat_id, user_id)
                )
                if not cursor.fetchone():
                    logger.warning("chat_unarchive_denied", chat_id=chat_id, user_id=user_id)
                    return False

            cursor = conn.execute(
                "UPDATE chats SET archived_at = NULL WHERE id = ? AND archived_at IS NOT NULL",
                (chat_id,)
            )
            success = cursor.rowcount > 0
            conn.commit()

            if success:
                logger.info("chat_unarchived", chat_id=chat_id, user_id=user_id)

            return success
        finally:
            conn.close()

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        model: Optional[str] = None
    ) -> bool:
        """
        Add a message to a chat.

        Args:
            chat_id: Chat identifier
            role: Message role (user/assistant/system)
            content: Message content
            model: Optional model that generated this message

        Returns:
            True if message was added, False if chat doesn't exist
        """
        conn = self.get_conn()
        now = int(time.time())

        try:
            # Check if chat exists
            chat_exists = conn.execute(
                "SELECT 1 FROM chats WHERE id = ?", (chat_id,)
            ).fetchone()

            if not chat_exists:
                return False

            # Insert message
            conn.execute(
                "INSERT INTO messages (chat_id, role, content, timestamp, model) VALUES (?, ?, ?, ?, ?)",
                (chat_id, role, content, now, model)
            )

            # Update chat's updated_at and model (if provided)
            if model:
                conn.execute(
                    "UPDATE chats SET updated_at = ?, model = ? WHERE id = ?",
                    (now, model, chat_id)
                )
            else:
                conn.execute(
                    "UPDATE chats SET updated_at = ? WHERE id = ?",
                    (now, chat_id)
                )

            conn.commit()
            logger.info("message_added", chat_id=chat_id, role=role, model=model)
            return True
        finally:
            conn.close()

    def list_chats(self, user_id: Optional[int] = None, include_archived: bool = False) -> List[Dict[str, Any]]:
        """
        List all chats with summary information.

        Args:
            user_id: Filter chats by this user ID (optional, for multi-user support)
            include_archived: If True, include archived chats; if False, exclude them

        Returns:
            List of chat summaries sorted by updated_at (newest first)
        """
        conn = self.get_conn()

        try:
            # Check if user_id column exists
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            has_user_id = 'user_id' in columns

            # Build archive filter
            archive_filter = "" if include_archived else "AND c.archived_at IS NULL"

            if has_user_id and user_id is not None:
                # Filter by user
                rows = conn.execute(f"""
                    SELECT c.id, c.title, c.created_at, c.updated_at,
                           GROUP_CONCAT(ct.tag, ',') as tags, c.user_id, c.archived_at
                    FROM chats c
                    LEFT JOIN chat_tags ct ON ct.chat_id = c.id
                    WHERE c.user_id = ? {archive_filter}
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                """, (user_id,)).fetchall()

                chats = [
                    {
                        "id": row[0],
                        "title": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                        "tags": row[4].split(',') if row[4] else [],
                        "user_id": row[5],
                        "archived_at": row[6]
                    }
                    for row in rows
                ]
            else:
                # Return all chats (backward compatibility or no user filter)
                if has_user_id:
                    rows = conn.execute(f"""
                        SELECT c.id, c.title, c.created_at, c.updated_at,
                               GROUP_CONCAT(ct.tag, ',') as tags, c.user_id, c.archived_at
                        FROM chats c
                        LEFT JOIN chat_tags ct ON ct.chat_id = c.id
                        WHERE 1=1 {archive_filter}
                        GROUP BY c.id
                        ORDER BY c.updated_at DESC
                    """).fetchall()

                    chats = [
                        {
                            "id": row[0],
                            "title": row[1],
                            "created_at": row[2],
                            "updated_at": row[3],
                            "tags": row[4].split(',') if row[4] else [],
                            "user_id": row[5] if len(row) > 5 else None,
                            "archived_at": row[6] if len(row) > 6 else None
                        }
                        for row in rows
                    ]
                else:
                    rows = conn.execute(f"""
                        SELECT c.id, c.title, c.created_at, c.updated_at,
                               GROUP_CONCAT(ct.tag, ',') as tags, c.archived_at
                        FROM chats c
                        LEFT JOIN chat_tags ct ON ct.chat_id = c.id
                        WHERE 1=1 {archive_filter}
                        GROUP BY c.id
                        ORDER BY c.updated_at DESC
                    """).fetchall()

                    chats = [
                        {
                            "id": row[0],
                            "title": row[1],
                            "created_at": row[2],
                            "updated_at": row[3],
                            "tags": row[4].split(',') if row[4] else [],
                            "archived_at": row[5] if len(row) > 5 else None
                        }
                        for row in rows
                    ]

            return chats
        finally:
            conn.close()

    def list_archived_chats(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List only archived chats.

        Args:
            user_id: Filter chats by this user ID (optional)

        Returns:
            List of archived chat summaries sorted by archived_at (newest first)
        """
        conn = self.get_conn()

        try:
            # Check if user_id column exists
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            has_user_id = 'user_id' in columns

            if has_user_id and user_id is not None:
                rows = conn.execute("""
                    SELECT c.id, c.title, c.created_at, c.updated_at,
                           GROUP_CONCAT(ct.tag, ',') as tags, c.user_id, c.archived_at
                    FROM chats c
                    LEFT JOIN chat_tags ct ON ct.chat_id = c.id
                    WHERE c.user_id = ? AND c.archived_at IS NOT NULL
                    GROUP BY c.id
                    ORDER BY c.archived_at DESC
                """, (user_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT c.id, c.title, c.created_at, c.updated_at,
                           GROUP_CONCAT(ct.tag, ',') as tags, c.archived_at
                    FROM chats c
                    LEFT JOIN chat_tags ct ON ct.chat_id = c.id
                    WHERE c.archived_at IS NOT NULL
                    GROUP BY c.id
                    ORDER BY c.archived_at DESC
                """).fetchall()

            if has_user_id and user_id is not None:
                chats = [
                    {
                        "id": row[0],
                        "title": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                        "tags": row[4].split(',') if row[4] else [],
                        "user_id": row[5],
                        "archived_at": row[6]
                    }
                    for row in rows
                ]
            else:
                chats = [
                    {
                        "id": row[0],
                        "title": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                        "tags": row[4].split(',') if row[4] else [],
                        "archived_at": row[5]
                    }
                    for row in rows
                ]

            return chats
        finally:
            conn.close()

    def delete_chat(self, chat_id: str, user_id: Optional[int] = None) -> bool:
        """
        Delete a chat and all its messages.

        Args:
            chat_id: Chat identifier
            user_id: User ID for ownership verification (optional but recommended)

        Returns:
            True if chat was deleted, False if not found or permission denied
        """
        conn = self.get_conn()

        try:
            # Check if user_id column exists
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            has_user_id = 'user_id' in columns

            # Verify ownership if user_id provided and column exists
            if has_user_id and user_id is not None:
                cursor = conn.execute(
                    "SELECT id FROM chats WHERE id = ? AND user_id = ?",
                    (chat_id, user_id)
                )
                if not cursor.fetchone():
                    logger.warning("chat_delete_denied", chat_id=chat_id, user_id=user_id)
                    return False

            cursor = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            success = cursor.rowcount > 0
            conn.commit()

            if success:
                logger.info("chat_deleted", chat_id=chat_id, user_id=user_id)

            return success
        finally:
            conn.close()

    def add_tags(self, chat_id: str, tags: List[str]) -> bool:
        """
        Add tags to a chat.

        Args:
            chat_id: Chat identifier
            tags: List of tags to add

        Returns:
            True if tags were added, False if chat doesn't exist
        """
        if not tags:
            return True

        conn = self.get_conn()

        try:
            # Check if chat exists
            chat_exists = conn.execute(
                "SELECT 1 FROM chats WHERE id = ?", (chat_id,)
            ).fetchone()

            if not chat_exists:
                return False

            # Insert tags (ignore duplicates)
            conn.executemany(
                "INSERT OR IGNORE INTO chat_tags (chat_id, tag) VALUES (?, ?)",
                [(chat_id, tag) for tag in tags]
            )

            conn.commit()
            logger.info("tags_added", chat_id=chat_id, tags=tags)
            return True
        finally:
            conn.close()

    def remove_tags(self, chat_id: str, tags: List[str]) -> bool:
        """
        Remove tags from a chat.

        Args:
            chat_id: Chat identifier
            tags: List of tags to remove

        Returns:
            True if operation succeeded
        """
        if not tags:
            return True

        conn = self.get_conn()

        try:
            conn.executemany(
                "DELETE FROM chat_tags WHERE chat_id = ? AND tag = ?",
                [(chat_id, tag) for tag in tags]
            )

            conn.commit()
            logger.info("tags_removed", chat_id=chat_id, tags=tags)
            return True
        finally:
            conn.close()

    def get_chats_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """
        Get all chats with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of chat summaries
        """
        conn = self.get_conn()

        try:
            rows = conn.execute("""
                SELECT c.id, c.title, c.created_at, c.updated_at
                FROM chats c
                JOIN chat_tags ct ON ct.chat_id = c.id
                WHERE ct.tag = ?
                ORDER BY c.updated_at DESC
            """, (tag,)).fetchall()

            chats = [
                {
                    "id": row[0],
                    "title": row[1],
                    "created_at": row[2],
                    "updated_at": row[3]
                }
                for row in rows
            ]

            return chats
        finally:
            conn.close()

    def search_messages(self, query: str, limit: int = 20, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Full-text search across all chat messages and titles.

        Args:
            query: Search query string
            limit: Maximum number of chats to return
            user_id: Filter results by user ID (optional, for multi-user support)

        Returns:
            List of dicts with chat_id, title, and matches (snippets)
            Format: [{"chat_id": "...", "title": "...", "matches": [{"type": "title"|"user"|"assistant", "role": "...", "snippet": "..."}]}]
        """
        if not query or not query.strip():
            return []

        conn = self.get_conn()

        try:
            # Check if user_id column exists
            cursor = conn.execute("PRAGMA table_info(chats)")
            columns = [row[1] for row in cursor.fetchall()]
            has_user_id = 'user_id' in columns

            # Search in messages using FTS5
            # Group by chat_id and collect matching snippets
            results_dict = {}

            # Search message content
            if has_user_id and user_id is not None:
                message_rows = conn.execute("""
                    SELECT m.chat_id, c.title, m.role, snippet(messages_fts, 2, '<mark>', '</mark>', '...', 40) as snippet
                    FROM messages_fts
                    JOIN messages m ON messages_fts.rowid = m.id
                    JOIN chats c ON m.chat_id = c.id
                    WHERE messages_fts MATCH ? AND c.user_id = ?
                    ORDER BY rank
                    LIMIT 100
                """, (query, user_id)).fetchall()
            else:
                message_rows = conn.execute("""
                    SELECT m.chat_id, c.title, m.role, snippet(messages_fts, 2, '<mark>', '</mark>', '...', 40) as snippet
                    FROM messages_fts
                    JOIN messages m ON messages_fts.rowid = m.id
                    JOIN chats c ON m.chat_id = c.id
                    WHERE messages_fts MATCH ?
                    ORDER BY rank
                    LIMIT 100
                """, (query,)).fetchall()

            for chat_id, title, role, snippet in message_rows:
                if chat_id not in results_dict:
                    results_dict[chat_id] = {
                        "chat_id": chat_id,
                        "title": title,
                        "matches": []
                    }

                # Add message match
                results_dict[chat_id]["matches"].append({
                    "type": role,
                    "role": role,
                    "snippet": snippet
                })

            # Also search in chat titles
            if has_user_id and user_id is not None:
                title_rows = conn.execute("""
                    SELECT id, title
                    FROM chats
                    WHERE title LIKE ? AND user_id = ?
                    LIMIT 20
                """, (f"%{query}%", user_id)).fetchall()
            else:
                title_rows = conn.execute("""
                    SELECT id, title
                    FROM chats
                    WHERE title LIKE ?
                    LIMIT 20
                """, (f"%{query}%",)).fetchall()

            for chat_id, title in title_rows:
                if chat_id not in results_dict:
                    results_dict[chat_id] = {
                        "chat_id": chat_id,
                        "title": title,
                        "matches": []
                    }

                # Add title match (highlight the query term manually)
                # Simple case-insensitive highlighting
                import re
                pattern = re.compile(f"({re.escape(query)})", re.IGNORECASE)
                highlighted_title = pattern.sub(r"<mark>\1</mark>", title)

                results_dict[chat_id]["matches"].insert(0, {
                    "type": "title",
                    "snippet": highlighted_title
                })

            # Convert to list and limit results
            results = list(results_dict.values())[:limit]

            logger.info("messages_searched", query=query, result_count=len(results))
            return results

        finally:
            conn.close()


# Global database instance (lazy initialization)
_db_instance: Optional[ChatDatabase] = None


def get_chat_db(db_path: str | Path = "chats.sqlite3") -> ChatDatabase:
    """
    Get or create the global ChatDatabase instance.

    Args:
        db_path: Path to SQLite database file

    Returns:
        ChatDatabase instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = ChatDatabase(db_path)
    return _db_instance
