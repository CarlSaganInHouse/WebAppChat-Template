"""
StorageService comprehensive unit tests.

Tests for chat/message storage operations with both JSON and SQLite backends.
"""

import pytest
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.storage_service import StorageService, get_storage_service


@pytest.fixture
def temp_json_dir(tmp_path):
    """Create a temporary directory for JSON storage."""
    json_dir = tmp_path / "chats"
    json_dir.mkdir()
    return str(json_dir)


@pytest.fixture
def temp_sqlite_db(tmp_path):
    """Create a temporary SQLite database path."""
    db_path = tmp_path / "test_chats.sqlite3"
    return str(db_path)


@pytest.fixture
def json_storage(temp_json_dir):
    """Create StorageService with JSON backend."""
    return StorageService(use_sqlite=False, json_dir=temp_json_dir)


@pytest.fixture
def sqlite_storage(temp_sqlite_db):
    """Create StorageService with SQLite backend."""
    return StorageService(use_sqlite=True, db_path=temp_sqlite_db)


class TestInitialization:
    """Test StorageService initialization."""

    def test_json_backend_creates_directory(self, temp_json_dir):
        """Should create chats directory for JSON backend."""
        service = StorageService(use_sqlite=False, json_dir=temp_json_dir)

        assert Path(temp_json_dir).exists()
        assert service.use_sqlite is False

    def test_sqlite_backend_initializes_db(self, temp_sqlite_db):
        """Should initialize SQLite database and schema."""
        service = StorageService(use_sqlite=True, db_path=temp_sqlite_db)

        assert Path(temp_sqlite_db).exists()
        assert service.use_sqlite is True

        # Verify schema
        import chat_db
        db = chat_db.ChatDB(temp_sqlite_db)
        conn = db.get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert 'chats' in tables
        assert 'messages' in tables


class TestNewChat:
    """Test chat creation."""

    def test_json_creates_new_chat(self, json_storage):
        """JSON backend should create new chat."""
        chat = json_storage.new_chat(title="Test Chat", model="gpt-4o")

        assert chat['id'] is not None
        assert chat['title'] == "Test Chat"
        assert chat['model'] == "gpt-4o"
        assert chat['messages'] == []
        assert 'created_at' in chat
        assert 'updated_at' in chat

    def test_sqlite_creates_new_chat(self, sqlite_storage):
        """SQLite backend should create new chat."""
        chat = sqlite_storage.new_chat(title="Test Chat", model="gpt-4o")

        assert chat['id'] is not None
        assert chat['title'] == "Test Chat"
        assert chat['model'] == "gpt-4o"
        assert chat['messages'] == []
        assert 'created_at' in chat
        assert 'updated_at' in chat

    def test_default_title(self, json_storage):
        """Should use default title if none provided."""
        chat = json_storage.new_chat()

        assert chat['title'] == "New chat"

    def test_unique_ids(self, json_storage):
        """Each chat should have unique ID."""
        chat1 = json_storage.new_chat()
        chat2 = json_storage.new_chat()

        assert chat1['id'] != chat2['id']


class TestLoadChat:
    """Test chat loading."""

    def test_json_loads_existing_chat(self, json_storage):
        """JSON backend should load existing chat."""
        # Create chat
        created = json_storage.new_chat(title="Test")
        chat_id = created['id']

        # Load it
        loaded = json_storage.load_chat(chat_id)

        assert loaded is not None
        assert loaded['id'] == chat_id
        assert loaded['title'] == "Test"

    def test_sqlite_loads_existing_chat(self, sqlite_storage):
        """SQLite backend should load existing chat."""
        # Create chat
        created = sqlite_storage.new_chat(title="Test")
        chat_id = created['id']

        # Load it
        loaded = sqlite_storage.load_chat(chat_id)

        assert loaded is not None
        assert loaded['id'] == chat_id
        assert loaded['title'] == "Test"

    def test_json_returns_none_for_nonexistent(self, json_storage):
        """JSON backend should return None for nonexistent chat."""
        loaded = json_storage.load_chat("nonexistent-id")
        assert loaded is None

    def test_sqlite_returns_none_for_nonexistent(self, sqlite_storage):
        """SQLite backend should return None for nonexistent chat."""
        loaded = sqlite_storage.load_chat(99999)
        assert loaded is None


class TestSaveChat:
    """Test chat saving."""

    def test_json_saves_chat_updates(self, json_storage):
        """JSON backend should save chat metadata updates."""
        # Create chat
        chat = json_storage.new_chat(title="Original")
        chat_id = chat['id']

        # Update and save
        chat['title'] = "Updated"
        chat['meta']['tags'] = ["tag1", "tag2"]
        json_storage.save_chat(chat)

        # save_chat returns None, just check it doesn't raise
        assert True

        # Verify persisted
        loaded = json_storage.load_chat(chat_id)
        assert loaded['title'] == "Updated"
        assert 'tag1' in loaded.get('tags', [])

    def test_sqlite_saves_chat_updates(self, sqlite_storage):
        """SQLite backend should save chat metadata updates."""
        # Create chat
        chat = sqlite_storage.new_chat(title="Original")
        chat_id = chat['id']

        # Update and save
        chat['title'] = "Updated"
        chat['meta']['tags'] = ["tag1", "tag2"]
        sqlite_storage.save_chat(chat)

        # save_chat returns None, just check it doesn't raise
        assert True

        # Verify persisted
        loaded = sqlite_storage.load_chat(chat_id)
        assert loaded['title'] == "Updated"


class TestAppendMessage:
    """Test message appending."""

    def test_json_appends_message(self, json_storage):
        """JSON backend should append messages."""
        chat = json_storage.new_chat()
        chat_id = chat['id']

        result = json_storage.append_message(
            chat_id=chat_id,
            role="user",
            content="Hello",
            model="gpt-4o"
        )

        # append_message returns the chat dict, not a boolean
        assert result is not None
        assert 'id' in result

        # Verify message added
        loaded = json_storage.load_chat(chat_id)
        assert len(loaded['messages']) == 1
        assert loaded['messages'][0]['role'] == "user"
        assert loaded['messages'][0]['content'] == "Hello"

    def test_sqlite_appends_message(self, sqlite_storage):
        """SQLite backend should append messages."""
        chat = sqlite_storage.new_chat()
        chat_id = chat['id']

        result = sqlite_storage.append_message(
            chat_id=chat_id,
            role="user",
            content="Hello",
            model="gpt-4o"
        )

        # append_message returns the chat dict, not a boolean
        assert result is not None
        assert 'id' in result

        # Verify message added
        loaded = sqlite_storage.load_chat(chat_id)
        assert len(loaded['messages']) == 1
        assert loaded['messages'][0]['role'] == "user"
        assert loaded['messages'][0]['content'] == "Hello"

    def test_multiple_messages_preserve_order(self, json_storage):
        """Messages should maintain order."""
        chat = json_storage.new_chat()
        chat_id = chat['id']

        json_storage.append_message(chat_id, "user", "Message 1")
        json_storage.append_message(chat_id, "assistant", "Message 2")
        json_storage.append_message(chat_id, "user", "Message 3")

        loaded = json_storage.load_chat(chat_id)
        assert len(loaded['messages']) == 3
        assert loaded['messages'][0]['content'] == "Message 1"
        assert loaded['messages'][1]['content'] == "Message 2"
        assert loaded['messages'][2]['content'] == "Message 3"


class TestListChats:
    """Test chat listing."""

    def test_json_lists_all_chats(self, json_storage):
        """JSON backend should list all chats."""
        # Create multiple chats
        json_storage.new_chat(title="Chat 1")
        json_storage.new_chat(title="Chat 2")
        json_storage.new_chat(title="Chat 3")

        chats = json_storage.list_chats()

        assert len(chats) == 3
        titles = {c['title'] for c in chats}
        assert 'Chat 1' in titles
        assert 'Chat 2' in titles
        assert 'Chat 3' in titles

    def test_sqlite_lists_all_chats(self, sqlite_storage):
        """SQLite backend should list all chats."""
        # Create multiple chats
        sqlite_storage.new_chat(title="Chat 1")
        sqlite_storage.new_chat(title="Chat 2")
        sqlite_storage.new_chat(title="Chat 3")

        chats = sqlite_storage.list_chats()

        assert len(chats) == 3
        titles = {c['title'] for c in chats}
        assert 'Chat 1' in titles
        assert 'Chat 2' in titles
        assert 'Chat 3' in titles

    def test_empty_list_when_no_chats(self, json_storage):
        """Should return empty list when no chats exist."""
        chats = json_storage.list_chats()
        assert chats == []

    def test_sorted_by_updated_at(self, json_storage):
        """Chats should be sorted by updated_at descending."""
        # Create chats with different timestamps
        chat1 = json_storage.new_chat(title="First")
        chat2 = json_storage.new_chat(title="Second")
        chat3 = json_storage.new_chat(title="Third")

        # Update middle one
        json_storage.append_message(chat2['id'], "user", "Update")

        chats = json_storage.list_chats()

        # Most recently updated should be first
        assert chats[0]['id'] == chat2['id']


class TestRenameChat:
    """Test chat renaming."""

    def test_json_renames_chat(self, json_storage):
        """JSON backend should rename chat."""
        chat = json_storage.new_chat(title="Original")
        chat_id = chat['id']

        result = json_storage.rename_chat(chat_id, "New Title")
        assert result is True

        loaded = json_storage.load_chat(chat_id)
        assert loaded['title'] == "New Title"

    def test_sqlite_renames_chat(self, sqlite_storage):
        """SQLite backend should rename chat."""
        chat = sqlite_storage.new_chat(title="Original")
        chat_id = chat['id']

        result = sqlite_storage.rename_chat(chat_id, "New Title")
        assert result is True

        loaded = sqlite_storage.load_chat(chat_id)
        assert loaded['title'] == "New Title"

    def test_rename_nonexistent_returns_false(self, json_storage):
        """Should return False for nonexistent chat."""
        result = json_storage.rename_chat("nonexistent", "New Title")
        assert result is False


class TestDeleteChat:
    """Test chat deletion."""

    def test_json_deletes_chat(self, json_storage):
        """JSON backend should delete chat."""
        chat = json_storage.new_chat(title="To Delete")
        chat_id = chat['id']

        result = json_storage.delete_chat(chat_id)
        assert result is True

        # Verify deleted
        loaded = json_storage.load_chat(chat_id)
        assert loaded is None

    def test_sqlite_deletes_chat(self, sqlite_storage):
        """SQLite backend should delete chat."""
        chat = sqlite_storage.new_chat(title="To Delete")
        chat_id = chat['id']

        result = sqlite_storage.delete_chat(chat_id)
        assert result is True

        # Verify deleted
        loaded = sqlite_storage.load_chat(chat_id)
        assert loaded is None

    def test_delete_removes_from_list(self, json_storage):
        """Deleted chat should not appear in list."""
        chat1 = json_storage.new_chat(title="Keep")
        chat2 = json_storage.new_chat(title="Delete")

        json_storage.delete_chat(chat2['id'])

        chats = json_storage.list_chats()
        assert len(chats) == 1
        assert chats[0]['id'] == chat1['id']

    def test_delete_nonexistent_returns_false(self, json_storage):
        """Should return False for nonexistent chat."""
        result = json_storage.delete_chat("nonexistent")
        assert result is False


class TestTagManagement:
    """Test tag operations."""

    def test_json_adds_tags(self, json_storage):
        """JSON backend should add tags to chat."""
        chat = json_storage.new_chat()
        chat_id = chat['id']

        result = json_storage.add_tags(chat_id, ["tag1", "tag2"])
        assert result is True

        loaded = json_storage.load_chat(chat_id)
        # Tags are stored in meta.tags
        tags = loaded.get('meta', {}).get('tags', [])
        assert 'tag1' in tags
        assert 'tag2' in tags

    def test_sqlite_adds_tags(self, sqlite_storage):
        """SQLite backend should add tags to chat."""
        chat = sqlite_storage.new_chat()
        chat_id = chat['id']

        result = sqlite_storage.add_tags(chat_id, ["tag1", "tag2"])
        assert result is True

        loaded = sqlite_storage.load_chat(chat_id)
        # Tags are stored in meta.tags
        tags = loaded.get('meta', {}).get('tags', [])
        assert 'tag1' in tags
        assert 'tag2' in tags

    def test_json_removes_tags(self, json_storage):
        """JSON backend should remove tags from chat."""
        chat = json_storage.new_chat()
        chat_id = chat['id']

        json_storage.add_tags(chat_id, ["tag1", "tag2", "tag3"])
        result = json_storage.remove_tags(chat_id, ["tag2"])
        assert result is True

        loaded = json_storage.load_chat(chat_id)
        # Tags are stored in meta.tags
        tags = loaded.get('meta', {}).get('tags', [])
        assert 'tag1' in tags
        assert 'tag2' not in tags
        assert 'tag3' in tags

    def test_get_chats_by_tag(self, json_storage):
        """Should filter chats by tag."""
        chat1 = json_storage.new_chat(title="Chat 1")
        chat2 = json_storage.new_chat(title="Chat 2")
        chat3 = json_storage.new_chat(title="Chat 3")

        json_storage.add_tags(chat1['id'], ["work"])
        json_storage.add_tags(chat2['id'], ["personal"])
        json_storage.add_tags(chat3['id'], ["work", "important"])

        work_chats = json_storage.get_chats_by_tag("work")
        assert len(work_chats) == 2
        ids = {c['id'] for c in work_chats}
        assert chat1['id'] in ids
        assert chat3['id'] in ids


class TestSearchMessages:
    """Test message search (SQLite only)."""

    def test_sqlite_searches_messages(self, sqlite_storage):
        """SQLite backend should search message content."""
        chat = sqlite_storage.new_chat()
        chat_id = chat['id']

        sqlite_storage.append_message(chat_id, "user", "Hello world")
        sqlite_storage.append_message(chat_id, "assistant", "Hi there")
        sqlite_storage.append_message(chat_id, "user", "How are you?")

        results = sqlite_storage.search_messages("hello")

        assert len(results) > 0
        assert any("Hello world" in r.get('content', '') for r in results)

    def test_json_search_not_supported(self, json_storage):
        """JSON backend should return empty list for search."""
        chat = json_storage.new_chat()
        json_storage.append_message(chat['id'], "user", "Hello world")

        results = json_storage.search_messages("hello")
        assert results == []


class TestPathTraversalProtection:
    """Test path traversal protection in JSON backend."""

    def test_json_prevents_path_traversal_in_load(self, json_storage):
        """Should prevent path traversal attacks in load_chat."""
        # Try to load chat with path traversal
        result = json_storage.load_chat("../../etc/passwd")
        assert result is None

    def test_json_prevents_path_traversal_in_delete(self, json_storage):
        """Should prevent path traversal attacks in delete_chat."""
        # Try to delete with path traversal
        result = json_storage.delete_chat("../../important.json")
        assert result is False


class TestSingletonAccess:
    """Test singleton pattern."""

    def test_get_storage_service_returns_singleton(self):
        """Should return same instance on multiple calls."""
        service1 = get_storage_service()
        service2 = get_storage_service()

        assert service1 is service2


class TestBackendConsistency:
    """Test that both backends behave consistently."""

    def test_both_backends_create_chat_with_same_structure(self, json_storage, sqlite_storage):
        """Both backends should create chats with same structure."""
        json_chat = json_storage.new_chat(title="Test", model="gpt-4o")
        sqlite_chat = sqlite_storage.new_chat(title="Test", model="gpt-4o")

        # Both should have same keys
        assert set(json_chat.keys()) == set(sqlite_chat.keys())
        assert json_chat['title'] == sqlite_chat['title']
        assert json_chat['model'] == sqlite_chat['model']

    def test_both_backends_handle_messages_consistently(self, json_storage, sqlite_storage):
        """Both backends should handle message appending consistently."""
        json_chat = json_storage.new_chat()
        sqlite_chat = sqlite_storage.new_chat()

        json_storage.append_message(json_chat['id'], "user", "Test", model="gpt-4o")
        sqlite_storage.append_message(sqlite_chat['id'], "user", "Test", model="gpt-4o")

        json_loaded = json_storage.load_chat(json_chat['id'])
        sqlite_loaded = sqlite_storage.load_chat(sqlite_chat['id'])

        # Message structure should be same
        assert len(json_loaded['messages']) == len(sqlite_loaded['messages'])
        assert json_loaded['messages'][0]['role'] == sqlite_loaded['messages'][0]['role']
        assert json_loaded['messages'][0]['content'] == sqlite_loaded['messages'][0]['content']
