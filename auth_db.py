"""
Authentication database layer.
Provides user, API key, and audit logging functionality.

Schema:
- users: User accounts with hashed passwords
- api_keys: API keys for programmatic access (voice, automation, etc.)
- auth_logs: Audit trail for login attempts and API key usage
"""

import sqlite3
import time
import structlog
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

logger = structlog.get_logger()


class AuthDatabase:
    """SQLite database manager for authentication data."""

    def __init__(self, db_path: str | Path = "chats.sqlite3"):
        """
        Initialize auth database connection.

        Args:
            db_path: Path to SQLite database file (shared with chat storage)
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
        """Initialize database schema if not exists."""
        conn = self.get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                key_hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                revoked BOOLEAN DEFAULT 0,
                revoked_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS auth_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                username TEXT,
                key_label TEXT,
                ip_address TEXT,
                success BOOLEAN,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
            CREATE INDEX IF NOT EXISTS idx_api_keys_revoked ON api_keys(revoked);
            CREATE INDEX IF NOT EXISTS idx_auth_logs_timestamp ON auth_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_auth_logs_username ON auth_logs(username);
        """)
        conn.commit()
        conn.close()
        logger.info("auth_db_initialized")

    # ========== User Management ==========

    def create_user(self, username: str, password_hash: str) -> int:
        """
        Create a new user account.

        Args:
            username: Username (must be unique)
            password_hash: Bcrypt hashed password

        Returns:
            User ID

        Raises:
            sqlite3.IntegrityError: If username already exists
        """
        conn = self.get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash)
            )
            conn.commit()
            user_id = cursor.lastrowid
            logger.info("user_created", username=username, user_id=user_id)
            return user_id
        except sqlite3.IntegrityError as e:
            logger.warning("user_creation_failed", username=username, error=str(e))
            raise
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve user by username.

        Args:
            username: Username to look up

        Returns:
            Dictionary with user data or None if not found
        """
        conn = self.get_conn()
        row = conn.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if row:
            return {
                "id": row[0],
                "username": row[1],
                "password_hash": row[2],
                "created_at": row[3]
            }
        return None

    def user_exists(self, username: str) -> bool:
        """Check if user exists."""
        return self.get_user_by_username(username) is not None

    # ========== API Key Management ==========

    def create_api_key(self, label: str, key_hash: str) -> int:
        """
        Create a new API key.

        Args:
            label: Human-readable label (e.g., "Voice Assistant", "Mobile Phone")
            key_hash: Hashed API key

        Returns:
            API key ID

        Raises:
            sqlite3.IntegrityError: If key_hash already exists
        """
        conn = self.get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO api_keys (label, key_hash) VALUES (?, ?)",
                (label, key_hash)
            )
            conn.commit()
            key_id = cursor.lastrowid
            logger.info("api_key_created", label=label, key_id=key_id)
            return key_id
        except sqlite3.IntegrityError as e:
            logger.warning("api_key_creation_failed", label=label, error=str(e))
            raise
        finally:
            conn.close()

    def get_api_key_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve API key by hash.

        Args:
            key_hash: Hashed API key

        Returns:
            Dictionary with key data or None if not found
        """
        conn = self.get_conn()
        row = conn.execute(
            """SELECT id, label, created_at, last_used_at, revoked
               FROM api_keys WHERE key_hash = ?""",
            (key_hash,)
        ).fetchone()
        conn.close()

        if row:
            return {
                "id": row[0],
                "label": row[1],
                "created_at": row[2],
                "last_used_at": row[3],
                "revoked": bool(row[4])
            }
        return None

    def list_api_keys(self) -> List[Dict[str, Any]]:
        """
        List all API keys (non-revoked).

        Returns:
            List of API key dictionaries
        """
        conn = self.get_conn()
        rows = conn.execute(
            """SELECT id, label, created_at, last_used_at, revoked
               FROM api_keys
               ORDER BY created_at DESC"""
        ).fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "label": row[1],
                "created_at": row[2],
                "last_used_at": row[3],
                "revoked": bool(row[4])
            }
            for row in rows
        ]

    def revoke_api_key(self, key_id: int) -> bool:
        """
        Revoke an API key by ID.

        Args:
            key_id: API key ID

        Returns:
            True if successful, False if not found
        """
        conn = self.get_conn()
        cursor = conn.execute(
            "UPDATE api_keys SET revoked = 1, revoked_at = CURRENT_TIMESTAMP WHERE id = ?",
            (key_id,)
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()

        if affected > 0:
            logger.info("api_key_revoked", key_id=key_id)
            return True
        return False

    def update_api_key_last_used(self, key_id: int) -> None:
        """Update last_used_at timestamp for an API key."""
        conn = self.get_conn()
        conn.execute(
            "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
            (key_id,)
        )
        conn.commit()
        conn.close()

    # ========== Authentication Logging ==========

    def log_auth_attempt(
        self,
        event_type: str,
        success: bool,
        ip_address: str,
        username: Optional[str] = None,
        key_label: Optional[str] = None
    ) -> None:
        """
        Log an authentication attempt.

        Args:
            event_type: Type of event (e.g., "login", "api_key_auth")
            success: Whether the attempt was successful
            ip_address: IP address of the requester
            username: Username (for login attempts)
            key_label: API key label (for API key authentication)
        """
        conn = self.get_conn()
        conn.execute(
            """INSERT INTO auth_logs
               (event_type, username, key_label, ip_address, success)
               VALUES (?, ?, ?, ?, ?)""",
            (event_type, username, key_label, ip_address, success)
        )
        conn.commit()
        conn.close()

    def get_recent_auth_logs(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        username: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent authentication logs.

        Args:
            limit: Maximum number of logs to return
            event_type: Filter by event type (optional)
            username: Filter by username (optional)

        Returns:
            List of log dictionaries
        """
        conn = self.get_conn()

        query = "SELECT event_type, username, key_label, ip_address, success, timestamp FROM auth_logs WHERE 1=1"
        params = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        if username:
            query += " AND username = ?"
            params.append(username)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        conn.close()

        return [
            {
                "event_type": row[0],
                "username": row[1],
                "key_label": row[2],
                "ip_address": row[3],
                "success": bool(row[4]),
                "timestamp": row[5]
            }
            for row in rows
        ]


# Global instance for use across the app
_auth_db: Optional[AuthDatabase] = None


def get_auth_db(db_path: str | Path = "chats.sqlite3") -> AuthDatabase:
    """
    Get or create the global auth database instance.

    Args:
        db_path: Path to SQLite database file

    Returns:
        AuthDatabase instance
    """
    global _auth_db
    if _auth_db is None:
        _auth_db = AuthDatabase(db_path)
    return _auth_db


def init_auth_db(db_path: str | Path = "chats.sqlite3") -> AuthDatabase:
    """
    Initialize the auth database (call at app startup).

    Args:
        db_path: Path to SQLite database file

    Returns:
        AuthDatabase instance
    """
    global _auth_db
    _auth_db = AuthDatabase(db_path)
    return _auth_db
