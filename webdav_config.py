"""
WebDAV authentication and configuration for Obsidian vault remote access.

Supports bcrypt-hashed per-device credentials for secure authentication.
"""

import os
import json
import bcrypt
from typing import Dict, Optional
from pathlib import Path


class WebDAVAuthConfig:
    """
    Manages WebDAV authentication with bcrypt-hashed credentials.
    
    Credentials are stored in environment variable WEBDAV_AUTH_USERS as JSON:
    {
        "device_name": "bcrypt_hash_here",
        "mobile": "$2b$12$...",
        "laptop": "$2b$12$..."
    }
    """
    
    def __init__(self):
        self.users: Dict[str, str] = {}
        self._load_credentials()
    
    def _load_credentials(self):
        """Load and parse credentials from environment or file."""
        users_json = os.getenv("WEBDAV_AUTH_USERS", "{}")
        
        # Try loading from environment variable first
        try:
            self.users = json.loads(users_json)
            if self.users:  # Successfully loaded users from env
                return
        except json.JSONDecodeError:
            pass
        
        # Fall back to webdav_users.json file
        users_file = Path(__file__).parent / "webdav_users.json"
        if users_file.exists():
            try:
                with open(users_file, 'r') as f:
                    self.users = json.load(f)
                print(f"INFO: Loaded WebDAV users from {users_file}")
                return
            except (json.JSONDecodeError, IOError) as e:
                print(f"WARNING: Failed to load {users_file}: {e}")
        
        print("WARNING: No WebDAV authentication configured.")
        self.users = {}
    
    def verify_credentials(self, username: str, password: str) -> bool:
        """
        Verify username/password against stored bcrypt hashes.
        
        Args:
            username: Device/user identifier
            password: Plain-text password or token
        
        Returns:
            True if credentials are valid, False otherwise
        """
        if not self.users:
            # No auth configured - deny access
            return False
        
        if username not in self.users:
            return False
        
        stored_hash = self.users[username]
        
        # Handle both string and bytes
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode('utf-8')
        if isinstance(password, str):
            password = password.encode('utf-8')
        
        try:
            return bcrypt.checkpw(password, stored_hash)
        except Exception as e:
            print(f"ERROR: bcrypt verification failed: {e}")
            return False
    
    def add_user(self, username: str, password: str, rounds: int = 12) -> str:
        """
        Add a new user with bcrypt-hashed password.
        
        Args:
            username: Device/user identifier
            password: Plain-text password to hash
            rounds: bcrypt cost factor (default: 12)
        
        Returns:
            The bcrypt hash string for storage
        """
        salt = bcrypt.gensalt(rounds=rounds)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        hash_str = password_hash.decode('utf-8')
        self.users[username] = hash_str
        return hash_str
    
    def remove_user(self, username: str) -> bool:
        """
        Remove a user from the credentials store.
        
        Args:
            username: Device/user identifier
        
        Returns:
            True if user was removed, False if user didn't exist
        """
        if username in self.users:
            del self.users[username]
            return True
        return False
    
    def export_json(self) -> str:
        """
        Export current credentials as JSON for storage in .env file.
        
        Returns:
            JSON string suitable for WEBDAV_AUTH_USERS environment variable
        """
        return json.dumps(self.users, indent=2)
    
    def list_users(self) -> list:
        """
        Get list of configured usernames.
        
        Returns:
            List of username strings
        """
        return list(self.users.keys())


def generate_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.
    
    Args:
        length: Number of bytes for token (default: 32)
    
    Returns:
        Hex-encoded random token
    """
    import secrets
    return secrets.token_hex(length)


# Singleton instance
_auth_config: Optional[WebDAVAuthConfig] = None

def get_auth_config() -> WebDAVAuthConfig:
    """Get or create the singleton WebDAVAuthConfig instance."""
    global _auth_config
    if _auth_config is None:
        _auth_config = WebDAVAuthConfig()
    return _auth_config
