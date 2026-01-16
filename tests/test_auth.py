"""
Authentication tests.
Tests for user login, API key validation, session management, and decorators.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import auth modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from auth_db import AuthDatabase
from utils.auth_utils import (
    hash_password,
    verify_password,
    generate_api_key,
    hash_api_key,
    verify_api_key,
    get_current_user,
    extract_api_key_from_request,
)


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password_creates_different_hashes(self):
        """Hash function should create different hashes for same password."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different (due to salt)
        assert hash1 != hash2

        # Both should verify against original password
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_verify_password_success(self):
        """Password verification should succeed for correct password."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed)

    def test_verify_password_failure(self):
        """Password verification should fail for incorrect password."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)

        assert not verify_password(wrong_password, hashed)

    def test_password_must_be_string(self):
        """Password hashing should work with string input."""
        assert isinstance(hash_password("test"), str)


class TestAPIKeyGeneration:
    """Test API key generation and hashing."""

    def test_generate_api_key_is_unique(self):
        """Each generated key should be unique."""
        key1 = generate_api_key()
        key2 = generate_api_key()

        assert key1 != key2
        assert len(key1) > 0
        assert len(key2) > 0

    def test_api_key_hash_is_consistent(self):
        """Same API key should always hash to same value."""
        api_key = "test_api_key_12345"
        hash1 = hash_api_key(api_key)
        hash2 = hash_api_key(api_key)

        assert hash1 == hash2

    def test_api_key_verification_success(self):
        """API key verification should succeed for matching key."""
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)

        assert verify_api_key(api_key, key_hash)

    def test_api_key_verification_failure(self):
        """API key verification should fail for non-matching key."""
        api_key1 = generate_api_key()
        api_key2 = generate_api_key()
        key_hash = hash_api_key(api_key1)

        assert not verify_api_key(api_key2, key_hash)

    def test_api_key_hash_different_from_original(self):
        """API key hash should not equal the original key (security)."""
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)

        assert api_key != key_hash


class TestAuthDatabase:
    """Test authentication database operations."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name

        db = AuthDatabase(db_path)
        yield db

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    # ========== User Tests ==========

    def test_create_user_success(self, temp_db):
        """Creating a user should succeed and return an ID."""
        username = "testuser"
        password_hash = hash_password("password123")

        user_id = temp_db.create_user(username, password_hash)

        assert isinstance(user_id, int)
        assert user_id > 0

    def test_create_user_duplicate_fails(self, temp_db):
        """Creating a duplicate user should raise IntegrityError."""
        username = "testuser"
        password_hash = hash_password("password123")

        temp_db.create_user(username, password_hash)

        with pytest.raises(Exception):  # sqlite3.IntegrityError
            temp_db.create_user(username, password_hash)

    def test_get_user_by_username_success(self, temp_db):
        """Getting an existing user should return user data."""
        username = "testuser"
        password_hash = hash_password("password123")
        user_id = temp_db.create_user(username, password_hash)

        user = temp_db.get_user_by_username(username)

        assert user is not None
        assert user['id'] == user_id
        assert user['username'] == username
        assert user['password_hash'] == password_hash

    def test_get_user_by_username_not_found(self, temp_db):
        """Getting a non-existent user should return None."""
        user = temp_db.get_user_by_username("nonexistent")

        assert user is None

    def test_user_exists_true(self, temp_db):
        """user_exists should return True for existing user."""
        username = "testuser"
        password_hash = hash_password("password123")
        temp_db.create_user(username, password_hash)

        assert temp_db.user_exists(username)

    def test_user_exists_false(self, temp_db):
        """user_exists should return False for non-existent user."""
        assert not temp_db.user_exists("nonexistent")

    # ========== API Key Tests ==========

    def test_create_api_key_success(self, temp_db):
        """Creating an API key should succeed and return an ID."""
        label = "Test Voice Assistant"
        key_hash = hash_api_key(generate_api_key())

        key_id = temp_db.create_api_key(label, key_hash)

        assert isinstance(key_id, int)
        assert key_id > 0

    def test_create_api_key_duplicate_hash_fails(self, temp_db):
        """Creating a key with duplicate hash should fail."""
        label1 = "Key 1"
        label2 = "Key 2"
        key_hash = hash_api_key(generate_api_key())

        temp_db.create_api_key(label1, key_hash)

        with pytest.raises(Exception):  # sqlite3.IntegrityError
            temp_db.create_api_key(label2, key_hash)

    def test_get_api_key_by_hash_success(self, temp_db):
        """Getting an API key by hash should return key data."""
        label = "Test Voice Assistant"
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        key_id = temp_db.create_api_key(label, key_hash)

        key = temp_db.get_api_key_by_hash(key_hash)

        assert key is not None
        assert key['id'] == key_id
        assert key['label'] == label
        assert key['revoked'] is False

    def test_get_api_key_by_hash_not_found(self, temp_db):
        """Getting non-existent key should return None."""
        key = temp_db.get_api_key_by_hash("nonexistent_hash")

        assert key is None

    def test_list_api_keys_empty(self, temp_db):
        """Listing keys when none exist should return empty list."""
        keys = temp_db.list_api_keys()

        assert keys == []

    def test_list_api_keys_multiple(self, temp_db):
        """Listing keys should return all non-revoked keys."""
        keys_to_create = [
            ("Voice Assistant", generate_api_key()),
            ("Mobile App", generate_api_key()),
            ("Laptop", generate_api_key()),
        ]

        for label, api_key in keys_to_create:
            temp_db.create_api_key(label, hash_api_key(api_key))

        keys = temp_db.list_api_keys()

        assert len(keys) == 3
        assert all(k['revoked'] is False for k in keys)

    def test_revoke_api_key_success(self, temp_db):
        """Revoking a key should mark it as revoked."""
        label = "Test Key"
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        key_id = temp_db.create_api_key(label, key_hash)

        result = temp_db.revoke_api_key(key_id)

        assert result is True

        # Key should still be in database but marked as revoked
        key = temp_db.get_api_key_by_hash(key_hash)
        assert key is not None
        assert key['revoked'] is True

    def test_revoke_api_key_not_found(self, temp_db):
        """Revoking non-existent key should return False."""
        result = temp_db.revoke_api_key(999)

        assert result is False

    def test_update_api_key_last_used(self, temp_db):
        """Updating last_used timestamp should succeed."""
        label = "Test Key"
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        key_id = temp_db.create_api_key(label, key_hash)

        # Should not raise
        temp_db.update_api_key_last_used(key_id)

        key = temp_db.get_api_key_by_hash(key_hash)
        assert key['last_used_at'] is not None

    # ========== Auth Logging Tests ==========

    def test_log_auth_attempt_login_success(self, temp_db):
        """Logging successful login should succeed."""
        temp_db.log_auth_attempt(
            event_type='login',
            success=True,
            ip_address='192.168.1.1',
            username='testuser'
        )

        logs = temp_db.get_recent_auth_logs(limit=10)
        assert len(logs) == 1
        assert logs[0]['event_type'] == 'login'
        assert logs[0]['success'] is True
        assert logs[0]['username'] == 'testuser'

    def test_log_auth_attempt_login_failure(self, temp_db):
        """Logging failed login should succeed."""
        temp_db.log_auth_attempt(
            event_type='login',
            success=False,
            ip_address='192.168.1.1',
            username='testuser'
        )

        logs = temp_db.get_recent_auth_logs(limit=10)
        assert len(logs) == 1
        assert logs[0]['success'] is False

    def test_log_auth_attempt_api_key(self, temp_db):
        """Logging API key authentication should succeed."""
        temp_db.log_auth_attempt(
            event_type='api_key_auth',
            success=True,
            ip_address='192.168.1.1',
            key_label='Voice Assistant'
        )

        logs = temp_db.get_recent_auth_logs(limit=10)
        assert len(logs) == 1
        assert logs[0]['event_type'] == 'api_key_auth'
        assert logs[0]['key_label'] == 'Voice Assistant'

    def test_get_recent_auth_logs_filter_by_event(self, temp_db):
        """Filtering logs by event type should work."""
        temp_db.log_auth_attempt('login', True, '192.168.1.1', 'user1')
        temp_db.log_auth_attempt('api_key_auth', True, '192.168.1.1', key_label='key1')
        temp_db.log_auth_attempt('login', False, '192.168.1.1', 'user2')

        login_logs = temp_db.get_recent_auth_logs(event_type='login')

        assert len(login_logs) == 2
        assert all(log['event_type'] == 'login' for log in login_logs)

    def test_get_recent_auth_logs_filter_by_username(self, temp_db):
        """Filtering logs by username should work."""
        temp_db.log_auth_attempt('login', True, '192.168.1.1', 'user1')
        temp_db.log_auth_attempt('login', False, '192.168.1.1', 'user2')
        temp_db.log_auth_attempt('login', True, '192.168.1.1', 'user1')

        user1_logs = temp_db.get_recent_auth_logs(username='user1')

        assert len(user1_logs) == 2
        assert all(log['username'] == 'user1' for log in user1_logs)


class TestFlaskAuthIntegration:
    """Test Flask integration with auth system."""

    @pytest.fixture
    def app(self):
        """Create a test Flask app."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from flask import Flask
        from config import get_settings

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'

        yield app

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return app.test_client()

    def test_extract_api_key_from_header(self, app):
        """Extracting API key from Authorization header should work."""
        api_key = "test_api_key_123"

        with app.test_request_context(headers={'Authorization': f'Bearer {api_key}'}):
            extracted = extract_api_key_from_request()
            assert extracted == api_key

    def test_extract_api_key_missing_header(self, app):
        """Extracting key without Authorization header should return None."""
        with app.test_request_context():
            extracted = extract_api_key_from_request()
            assert extracted is None

    def test_extract_api_key_invalid_format(self, app):
        """Extracting key with invalid format should return None."""
        with app.test_request_context(headers={'Authorization': 'Basic dXNlcjpwYXNz'}):
            extracted = extract_api_key_from_request()
            assert extracted is None

    def test_get_current_user_no_session(self, app):
        """Getting user with no session should return None."""
        with app.test_request_context():
            user = get_current_user()
            assert user is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
