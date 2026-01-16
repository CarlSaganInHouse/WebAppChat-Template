"""
Tests for storage_sqlite.py - SQLite storage adapter.
Tests that storage_sqlite provides the same API as storage.py.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
from chat_db import ChatDatabase
import storage_sqlite


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def mock_db(temp_db_path):
    """Mock get_chat_db to use temp database."""
    with patch('storage_sqlite.get_chat_db') as mock:
        db = ChatDatabase(temp_db_path)
        mock.return_value = db
        yield db


class TestNewChat:
    """Test new_chat function."""

    def test_creates_new_chat(self, mock_db):
        """Test creating a new chat."""
        chat = storage_sqlite.new_chat("Test Chat")

        assert chat is not None
        assert chat["title"] == "Test Chat"
        assert chat["id"] is not None
        assert len(chat["id"]) == 12  # UUID hex[:12]
        assert chat["messages"] == []
        assert chat["meta"]["budget_usd"] is None
        assert chat["meta"]["spent_usd"] == 0.0
        assert chat["meta"]["tags"] == []

    def test_creates_chat_with_default_title(self, mock_db):
        """Test creating chat with default title."""
        chat = storage_sqlite.new_chat()
        assert chat["title"] == "New chat"

    def test_chat_has_timestamps(self, mock_db):
        """Test that new chat has timestamps."""
        chat = storage_sqlite.new_chat("Test")

        assert "created_at" in chat
        assert "updated_at" in chat
        assert chat["created_at"] > 0
        assert chat["updated_at"] > 0


class TestLoadChat:
    """Test load_chat function."""

    def test_loads_existing_chat(self, mock_db):
        """Test loading an existing chat."""
        # Create a chat first
        created = storage_sqlite.new_chat("Test")
        chat_id = created["id"]

        # Load it
        loaded = storage_sqlite.load_chat(chat_id)

        assert loaded is not None
        assert loaded["id"] == chat_id
        assert loaded["title"] == "Test"

    def test_load_nonexistent_chat(self, mock_db):
        """Test loading a nonexistent chat returns None."""
        chat = storage_sqlite.load_chat("nonexistent123")
        assert chat is None

    def test_load_chat_with_messages(self, mock_db):
        """Test loading a chat that has messages."""
        chat = storage_sqlite.new_chat("Test")
        storage_sqlite.append_message(chat["id"], "user", "Hello")

        loaded = storage_sqlite.load_chat(chat["id"])
        assert len(loaded["messages"]) == 1
        assert loaded["messages"][0]["content"] == "Hello"


class TestSaveChat:
    """Test save_chat function."""

    def test_saves_chat_updates(self, mock_db):
        """Test saving updates to a chat."""
        chat = storage_sqlite.new_chat("Original Title")
        chat["title"] = "Updated Title"
        chat["model"] = "gpt-4"
        chat["meta"]["budget_usd"] = 10.0

        storage_sqlite.save_chat(chat)

        # Load and verify
        loaded = storage_sqlite.load_chat(chat["id"])
        assert loaded["title"] == "Updated Title"
        assert loaded["model"] == "gpt-4"
        assert loaded["meta"]["budget_usd"] == 10.0

    def test_save_updates_tags(self, mock_db):
        """Test saving chat with tag changes."""
        chat = storage_sqlite.new_chat("Test")
        chat["meta"]["tags"] = ["work", "important"]

        storage_sqlite.save_chat(chat)

        loaded = storage_sqlite.load_chat(chat["id"])
        assert set(loaded["meta"]["tags"]) == {"work", "important"}

    def test_save_removes_tags(self, mock_db):
        """Test that save_chat can remove tags."""
        chat = storage_sqlite.new_chat("Test")
        chat["meta"]["tags"] = ["work", "personal"]
        storage_sqlite.save_chat(chat)

        # Remove one tag
        chat["meta"]["tags"] = ["work"]
        storage_sqlite.save_chat(chat)

        loaded = storage_sqlite.load_chat(chat["id"])
        assert loaded["meta"]["tags"] == ["work"]


class TestListChats:
    """Test list_chats function."""

    def test_list_empty(self, mock_db):
        """Test listing when no chats exist."""
        chats = storage_sqlite.list_chats()
        assert chats == []

    def test_list_multiple_chats(self, mock_db):
        """Test listing multiple chats."""
        storage_sqlite.new_chat("First")
        storage_sqlite.new_chat("Second")
        storage_sqlite.new_chat("Third")

        chats = storage_sqlite.list_chats()
        assert len(chats) == 3

    def test_list_returns_summary(self, mock_db):
        """Test that list returns summary (not full chat)."""
        chat = storage_sqlite.new_chat("Test")
        storage_sqlite.append_message(chat["id"], "user", "Hello")

        chats = storage_sqlite.list_chats()
        assert len(chats) == 1

        summary = chats[0]
        assert "id" in summary
        assert "title" in summary
        assert "created_at" in summary
        assert "updated_at" in summary
        assert "tags" in summary
        # Should NOT include full messages in summary
        assert "messages" not in summary

    def test_list_sorted_by_updated_at(self, mock_db):
        """Test that chats are sorted by updated_at (newest first)."""
        import time

        old_chat = storage_sqlite.new_chat("Old")
        time.sleep(1.1)  # Need at least 1 second for timestamp difference
        new_chat = storage_sqlite.new_chat("New")

        chats = storage_sqlite.list_chats()
        assert chats[0]["id"] == new_chat["id"]  # Newest first
        assert chats[1]["id"] == old_chat["id"]


class TestRenameChat:
    """Test rename_chat function."""

    def test_renames_chat(self, mock_db):
        """Test renaming a chat."""
        chat = storage_sqlite.new_chat("Original")
        success = storage_sqlite.rename_chat(chat["id"], "Renamed")

        assert success is True

        loaded = storage_sqlite.load_chat(chat["id"])
        assert loaded["title"] == "Renamed"

    def test_rename_nonexistent_chat(self, mock_db):
        """Test renaming a nonexistent chat."""
        success = storage_sqlite.rename_chat("nonexistent", "New Title")
        assert success is False

    def test_rename_empty_string_preserves_title(self, mock_db):
        """Test that empty string doesn't change title."""
        chat = storage_sqlite.new_chat("Original")
        success = storage_sqlite.rename_chat(chat["id"], "")

        loaded = storage_sqlite.load_chat(chat["id"])
        assert loaded["title"] == "Original"

    def test_rename_whitespace_only_preserves_title(self, mock_db):
        """Test that whitespace-only doesn't change title."""
        chat = storage_sqlite.new_chat("Original")
        storage_sqlite.rename_chat(chat["id"], "   ")

        loaded = storage_sqlite.load_chat(chat["id"])
        assert loaded["title"] == "Original"


class TestAppendMessage:
    """Test append_message function."""

    def test_appends_message(self, mock_db):
        """Test appending a message."""
        chat = storage_sqlite.new_chat("Test")
        updated = storage_sqlite.append_message(chat["id"], "user", "Hello")

        assert updated is not None
        assert len(updated["messages"]) == 1
        assert updated["messages"][0]["role"] == "user"
        assert updated["messages"][0]["content"] == "Hello"

    def test_append_message_with_model(self, mock_db):
        """Test appending a message with model."""
        chat = storage_sqlite.new_chat("Test")
        updated = storage_sqlite.append_message(
            chat["id"], "assistant", "Response", model="gpt-4"
        )

        assert updated["messages"][0]["model"] == "gpt-4"
        assert updated["model"] == "gpt-4"  # Chat-level model updates

    def test_append_message_to_nonexistent_chat(self, mock_db):
        """Test appending to nonexistent chat returns None."""
        result = storage_sqlite.append_message("nonexistent", "user", "Hello")
        assert result is None

    def test_append_multiple_messages(self, mock_db):
        """Test appending multiple messages."""
        chat = storage_sqlite.new_chat("Test")
        storage_sqlite.append_message(chat["id"], "user", "First")
        storage_sqlite.append_message(chat["id"], "assistant", "Second")
        updated = storage_sqlite.append_message(chat["id"], "user", "Third")

        assert len(updated["messages"]) == 3
        assert updated["messages"][0]["content"] == "First"
        assert updated["messages"][1]["content"] == "Second"
        assert updated["messages"][2]["content"] == "Third"

    def test_message_has_timestamp(self, mock_db):
        """Test that appended message has timestamp."""
        chat = storage_sqlite.new_chat("Test")
        updated = storage_sqlite.append_message(chat["id"], "user", "Hello")

        msg = updated["messages"][0]
        assert "ts" in msg
        assert msg["ts"] > 0


class TestDeleteChat:
    """Test delete_chat function."""

    def test_deletes_existing_chat(self, mock_db):
        """Test deleting an existing chat."""
        chat = storage_sqlite.new_chat("Test")
        success = storage_sqlite.delete_chat(chat["id"])

        assert success is True
        assert storage_sqlite.load_chat(chat["id"]) is None

    def test_delete_nonexistent_chat(self, mock_db):
        """Test deleting a nonexistent chat."""
        success = storage_sqlite.delete_chat("nonexistent")
        assert success is False

    def test_delete_blocks_path_traversal(self, mock_db):
        """Test that delete blocks path traversal attempts."""
        # These should be blocked for consistency with storage.py
        assert storage_sqlite.delete_chat("../etc/passwd") is False
        assert storage_sqlite.delete_chat("..\\windows\\system32") is False
        assert storage_sqlite.delete_chat("normal/../bad") is False

    def test_delete_removes_from_list(self, mock_db):
        """Test that deleted chat is removed from list."""
        chat1 = storage_sqlite.new_chat("Keep")
        chat2 = storage_sqlite.new_chat("Delete")

        storage_sqlite.delete_chat(chat2["id"])

        chats = storage_sqlite.list_chats()
        assert len(chats) == 1
        assert chats[0]["id"] == chat1["id"]


class TestAPICompatibility:
    """Test that storage_sqlite API matches storage.py."""

    def test_new_chat_signature(self, mock_db):
        """Test new_chat has same signature as storage.py."""
        # Should accept title parameter
        chat = storage_sqlite.new_chat(title="Test")
        assert chat["title"] == "Test"

        # Should have default
        chat = storage_sqlite.new_chat()
        assert chat["title"] == "New chat"

    def test_load_chat_signature(self, mock_db):
        """Test load_chat has same signature."""
        chat = storage_sqlite.new_chat()
        # Should accept chat ID string
        loaded = storage_sqlite.load_chat(chat["id"])
        assert loaded is not None

    def test_save_chat_signature(self, mock_db):
        """Test save_chat has same signature."""
        chat = storage_sqlite.new_chat("Test")
        # Should accept chat dict
        storage_sqlite.save_chat(chat)  # Should not raise

    def test_append_message_signature(self, mock_db):
        """Test append_message has same signature."""
        chat = storage_sqlite.new_chat()
        # Should accept cid, role, content, model
        result = storage_sqlite.append_message(
            chat["id"], "user", "Hello", model="gpt-4"
        )
        assert result is not None

    def test_delete_chat_signature(self, mock_db):
        """Test delete_chat has same signature."""
        chat = storage_sqlite.new_chat()
        # Should accept chat ID string and return bool
        result = storage_sqlite.delete_chat(chat["id"])
        assert isinstance(result, bool)

    def test_rename_chat_signature(self, mock_db):
        """Test rename_chat has same signature."""
        chat = storage_sqlite.new_chat()
        # Should accept cid and title, return bool
        result = storage_sqlite.rename_chat(chat["id"], "New Title")
        assert isinstance(result, bool)

    def test_list_chats_signature(self, mock_db):
        """Test list_chats has same signature."""
        # Should return list
        result = storage_sqlite.list_chats()
        assert isinstance(result, list)


class TestChatFormatCompatibility:
    """Test that SQLite storage returns same format as JSON storage."""

    def test_new_chat_format(self, mock_db):
        """Test new_chat returns same format as storage.py."""
        chat = storage_sqlite.new_chat("Test")

        # Required top-level keys
        assert "id" in chat
        assert "title" in chat
        assert "created_at" in chat
        assert "updated_at" in chat
        assert "model" in chat
        assert "messages" in chat
        assert "meta" in chat

        # Meta structure
        assert "budget_usd" in chat["meta"]
        assert "spent_usd" in chat["meta"]
        assert "tags" in chat["meta"]

        # Types
        assert isinstance(chat["id"], str)
        assert isinstance(chat["title"], str)
        assert isinstance(chat["created_at"], int)
        assert isinstance(chat["updated_at"], int)
        assert isinstance(chat["messages"], list)
        assert isinstance(chat["meta"], dict)
        assert isinstance(chat["meta"]["tags"], list)

    def test_message_format(self, mock_db):
        """Test message format matches storage.py."""
        chat = storage_sqlite.new_chat("Test")
        storage_sqlite.append_message(chat["id"], "user", "Hello", model="gpt-4")

        loaded = storage_sqlite.load_chat(chat["id"])
        msg = loaded["messages"][0]

        # Required message keys
        assert "role" in msg
        assert "content" in msg
        assert "ts" in msg
        assert "model" in msg

        # Types
        assert isinstance(msg["role"], str)
        assert isinstance(msg["content"], str)
        assert isinstance(msg["ts"], int)
        assert isinstance(msg["model"], str)

    def test_list_format(self, mock_db):
        """Test list_chats format matches storage.py."""
        storage_sqlite.new_chat("Test")
        chats = storage_sqlite.list_chats()

        assert len(chats) == 1
        chat_summary = chats[0]

        # Required keys in summary
        assert "id" in chat_summary
        assert "title" in chat_summary
        assert "created_at" in chat_summary
        assert "updated_at" in chat_summary
        assert "tags" in chat_summary
