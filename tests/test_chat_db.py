"""
Tests for chat_db.py - SQLite chat storage layer.
"""

import pytest
import tempfile
import os
from pathlib import Path
from chat_db import ChatDatabase


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    # Create temp file
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)

    # Initialize database
    db = ChatDatabase(path)

    yield db

    # Cleanup
    try:
        os.unlink(path)
    except:
        pass


class TestChatDatabaseInit:
    """Test database initialization."""

    def test_creates_database_file(self):
        """Test that database file is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.sqlite3"
            db = ChatDatabase(db_path)

            assert db_path.exists()

    def test_creates_tables(self, temp_db):
        """Test that all required tables are created."""
        conn = temp_db.get_conn()

        # Check chats table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chats'"
        )
        assert cursor.fetchone() is not None

        # Check messages table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
        )
        assert cursor.fetchone() is not None

        # Check chat_tags table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_tags'"
        )
        assert cursor.fetchone() is not None

        conn.close()

    def test_creates_indexes(self, temp_db):
        """Test that indexes are created."""
        conn = temp_db.get_conn()

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = [row[0] for row in cursor.fetchall()]

        # SQLite creates some indexes automatically
        assert "idx_messages_chat_id" in indexes
        assert "idx_chats_updated_at" in indexes

        conn.close()


class TestCreateChat:
    """Test chat creation."""

    def test_creates_chat_basic(self, temp_db):
        """Test creating a basic chat."""
        temp_db.create_chat(chat_id="test123", title="Test Chat")

        chat = temp_db.get_chat("test123")
        assert chat is not None
        assert chat["id"] == "test123"
        assert chat["title"] == "Test Chat"
        assert chat["model"] is None
        assert chat["messages"] == []
        assert chat["meta"]["budget_usd"] is None
        assert chat["meta"]["spent_usd"] == 0.0
        assert chat["meta"]["tags"] == []

    def test_creates_chat_with_model(self, temp_db):
        """Test creating a chat with a model."""
        temp_db.create_chat(chat_id="test456", title="Test", model="gpt-4")

        chat = temp_db.get_chat("test456")
        assert chat["model"] == "gpt-4"

    def test_creates_chat_with_budget(self, temp_db):
        """Test creating a chat with budget."""
        temp_db.create_chat(
            chat_id="test789",
            title="Test",
            budget_usd=5.0
        )

        chat = temp_db.get_chat("test789")
        assert chat["meta"]["budget_usd"] == 5.0

    def test_creates_chat_with_tags(self, temp_db):
        """Test creating a chat with tags."""
        temp_db.create_chat(
            chat_id="test_tags",
            title="Test",
            tags=["work", "important"]
        )

        chat = temp_db.get_chat("test_tags")
        assert set(chat["meta"]["tags"]) == {"work", "important"}

    def test_duplicate_chat_id_raises_error(self, temp_db):
        """Test that duplicate chat IDs raise an error."""
        temp_db.create_chat(chat_id="dup123", title="First")

        with pytest.raises(Exception):  # sqlite3.IntegrityError
            temp_db.create_chat(chat_id="dup123", title="Second")


class TestGetChat:
    """Test chat retrieval."""

    def test_get_nonexistent_chat(self, temp_db):
        """Test getting a chat that doesn't exist."""
        chat = temp_db.get_chat("nonexistent")
        assert chat is None

    def test_get_chat_with_messages(self, temp_db):
        """Test getting a chat with messages."""
        temp_db.create_chat(chat_id="chat_msg", title="Test")
        temp_db.add_message("chat_msg", "user", "Hello", model="gpt-4")
        temp_db.add_message("chat_msg", "assistant", "Hi there")

        chat = temp_db.get_chat("chat_msg")
        assert len(chat["messages"]) == 2
        assert chat["messages"][0]["role"] == "user"
        assert chat["messages"][0]["content"] == "Hello"
        assert chat["messages"][0]["model"] == "gpt-4"
        assert chat["messages"][1]["role"] == "assistant"
        assert chat["messages"][1]["content"] == "Hi there"


class TestUpdateChat:
    """Test chat updates."""

    def test_update_title(self, temp_db):
        """Test updating chat title."""
        temp_db.create_chat(chat_id="upd1", title="Old Title")
        success = temp_db.update_chat("upd1", title="New Title")

        assert success is True
        chat = temp_db.get_chat("upd1")
        assert chat["title"] == "New Title"

    def test_update_model(self, temp_db):
        """Test updating chat model."""
        temp_db.create_chat(chat_id="upd2", title="Test")
        temp_db.update_chat("upd2", model="gpt-4")

        chat = temp_db.get_chat("upd2")
        assert chat["model"] == "gpt-4"

    def test_update_budget(self, temp_db):
        """Test updating budget."""
        temp_db.create_chat(chat_id="upd3", title="Test")
        temp_db.update_chat("upd3", budget_usd=10.0, spent_usd=2.5)

        chat = temp_db.get_chat("upd3")
        assert chat["meta"]["budget_usd"] == 10.0
        assert chat["meta"]["spent_usd"] == 2.5

    def test_update_nonexistent_chat(self, temp_db):
        """Test updating a chat that doesn't exist."""
        success = temp_db.update_chat("nonexistent", title="New")
        assert success is False


class TestAddMessage:
    """Test message addition."""

    def test_add_message_basic(self, temp_db):
        """Test adding a basic message."""
        temp_db.create_chat(chat_id="msg1", title="Test")
        success = temp_db.add_message("msg1", "user", "Test message")

        assert success is True
        chat = temp_db.get_chat("msg1")
        assert len(chat["messages"]) == 1
        assert chat["messages"][0]["content"] == "Test message"

    def test_add_message_with_model(self, temp_db):
        """Test adding a message with model."""
        temp_db.create_chat(chat_id="msg2", title="Test")
        temp_db.add_message("msg2", "assistant", "Response", model="gpt-4")

        chat = temp_db.get_chat("msg2")
        assert chat["messages"][0]["model"] == "gpt-4"
        assert chat["model"] == "gpt-4"  # Chat-level model should update

    def test_add_message_to_nonexistent_chat(self, temp_db):
        """Test adding message to nonexistent chat."""
        success = temp_db.add_message("nonexistent", "user", "Hello")
        assert success is False

    def test_messages_ordered_by_timestamp(self, temp_db):
        """Test that messages are ordered by timestamp."""
        temp_db.create_chat(chat_id="msg_order", title="Test")
        temp_db.add_message("msg_order", "user", "First")
        temp_db.add_message("msg_order", "assistant", "Second")
        temp_db.add_message("msg_order", "user", "Third")

        chat = temp_db.get_chat("msg_order")
        assert chat["messages"][0]["content"] == "First"
        assert chat["messages"][1]["content"] == "Second"
        assert chat["messages"][2]["content"] == "Third"


class TestListChats:
    """Test listing chats."""

    def test_list_empty(self, temp_db):
        """Test listing when no chats exist."""
        chats = temp_db.list_chats()
        assert chats == []

    def test_list_multiple_chats(self, temp_db):
        """Test listing multiple chats."""
        temp_db.create_chat(chat_id="list1", title="First")
        temp_db.create_chat(chat_id="list2", title="Second")
        temp_db.create_chat(chat_id="list3", title="Third")

        chats = temp_db.list_chats()
        assert len(chats) == 3

        # Check that all IDs are present
        ids = {chat["id"] for chat in chats}
        assert ids == {"list1", "list2", "list3"}

    def test_list_sorted_by_updated_at(self, temp_db):
        """Test that chats are sorted by updated_at (newest first)."""
        import time

        temp_db.create_chat(chat_id="old", title="Old")
        time.sleep(0.01)
        temp_db.create_chat(chat_id="new", title="New")

        chats = temp_db.list_chats()
        assert chats[0]["id"] == "new"  # Newest first
        assert chats[1]["id"] == "old"

    def test_list_includes_tags(self, temp_db):
        """Test that list includes tags."""
        temp_db.create_chat(chat_id="tagged", title="Test", tags=["work"])

        chats = temp_db.list_chats()
        assert chats[0]["tags"] == ["work"]


class TestDeleteChat:
    """Test chat deletion."""

    def test_delete_existing_chat(self, temp_db):
        """Test deleting an existing chat."""
        temp_db.create_chat(chat_id="del1", title="Test")
        success = temp_db.delete_chat("del1")

        assert success is True
        assert temp_db.get_chat("del1") is None

    def test_delete_nonexistent_chat(self, temp_db):
        """Test deleting a nonexistent chat."""
        success = temp_db.delete_chat("nonexistent")
        assert success is False

    def test_delete_cascades_messages(self, temp_db):
        """Test that deleting a chat also deletes its messages."""
        temp_db.create_chat(chat_id="del_cascade", title="Test")
        temp_db.add_message("del_cascade", "user", "Message")

        temp_db.delete_chat("del_cascade")

        # Check that messages are gone
        conn = temp_db.get_conn()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ?",
            ("del_cascade",)
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0

    def test_delete_cascades_tags(self, temp_db):
        """Test that deleting a chat also deletes its tags."""
        temp_db.create_chat(chat_id="del_tags", title="Test", tags=["work"])
        temp_db.delete_chat("del_tags")

        # Check that tags are gone
        conn = temp_db.get_conn()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM chat_tags WHERE chat_id = ?",
            ("del_tags",)
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0


class TestTags:
    """Test tag operations."""

    def test_add_tags(self, temp_db):
        """Test adding tags to a chat."""
        temp_db.create_chat(chat_id="tags1", title="Test")
        success = temp_db.add_tags("tags1", ["work", "important"])

        assert success is True
        chat = temp_db.get_chat("tags1")
        assert set(chat["meta"]["tags"]) == {"work", "important"}

    def test_add_tags_to_nonexistent_chat(self, temp_db):
        """Test adding tags to nonexistent chat."""
        success = temp_db.add_tags("nonexistent", ["tag"])
        assert success is False

    def test_add_duplicate_tags_ignored(self, temp_db):
        """Test that duplicate tags are ignored."""
        temp_db.create_chat(chat_id="tags2", title="Test", tags=["work"])
        temp_db.add_tags("tags2", ["work", "personal"])

        chat = temp_db.get_chat("tags2")
        # Should have work (original) and personal (new), not duplicated
        assert set(chat["meta"]["tags"]) == {"work", "personal"}

    def test_remove_tags(self, temp_db):
        """Test removing tags from a chat."""
        temp_db.create_chat(
            chat_id="tags3",
            title="Test",
            tags=["work", "important", "urgent"]
        )
        temp_db.remove_tags("tags3", ["important"])

        chat = temp_db.get_chat("tags3")
        assert set(chat["meta"]["tags"]) == {"work", "urgent"}

    def test_get_chats_by_tag(self, temp_db):
        """Test getting chats by tag."""
        temp_db.create_chat(chat_id="t1", title="Work 1", tags=["work"])
        temp_db.create_chat(chat_id="t2", title="Work 2", tags=["work"])
        temp_db.create_chat(chat_id="t3", title="Personal", tags=["personal"])

        work_chats = temp_db.get_chats_by_tag("work")
        assert len(work_chats) == 2

        ids = {chat["id"] for chat in work_chats}
        assert ids == {"t1", "t2"}


class TestChatFormat:
    """Test that chat format matches JSON storage format."""

    def test_chat_format_matches_json(self, temp_db):
        """Test that SQLite chat format matches JSON format."""
        temp_db.create_chat(
            chat_id="format_test",
            title="Test Chat",
            model="gpt-4",
            budget_usd=10.0,
            tags=["test"]
        )
        temp_db.add_message("format_test", "user", "Hello")
        temp_db.add_message("format_test", "assistant", "Hi", model="gpt-4")

        chat = temp_db.get_chat("format_test")

        # Check top-level structure
        assert "id" in chat
        assert "title" in chat
        assert "model" in chat
        assert "created_at" in chat
        assert "updated_at" in chat
        assert "messages" in chat
        assert "meta" in chat

        # Check meta structure
        assert "budget_usd" in chat["meta"]
        assert "spent_usd" in chat["meta"]
        assert "tags" in chat["meta"]

        # Check message structure
        msg = chat["messages"][0]
        assert "role" in msg
        assert "content" in msg
        assert "ts" in msg


class TestSearchMessages:
    """Test full-text search functionality."""

    def test_search_empty_query(self, temp_db):
        """Test that empty query returns empty results."""
        results = temp_db.search_messages("")
        assert results == []

    def test_search_no_matches(self, temp_db):
        """Test search with no matches."""
        temp_db.create_chat("chat1", "Test Chat")
        temp_db.add_message("chat1", "user", "Hello world")

        results = temp_db.search_messages("nonexistent")
        assert results == []

    def test_search_message_content(self, temp_db):
        """Test searching in message content."""
        temp_db.create_chat("chat1", "Test Chat")
        temp_db.add_message("chat1", "user", "I love Python programming")
        temp_db.add_message("chat1", "assistant", "Python is great!")

        results = temp_db.search_messages("Python")

        assert len(results) == 1
        assert results[0]["chat_id"] == "chat1"
        assert results[0]["title"] == "Test Chat"
        assert len(results[0]["matches"]) >= 2  # Both messages match

    def test_search_case_insensitive(self, temp_db):
        """Test that search is case-insensitive."""
        temp_db.create_chat("chat1", "Test Chat")
        temp_db.add_message("chat1", "user", "Python is awesome")

        # Search with different cases
        results_lower = temp_db.search_messages("python")
        results_upper = temp_db.search_messages("PYTHON")
        results_mixed = temp_db.search_messages("PyThOn")

        assert len(results_lower) == 1
        assert len(results_upper) == 1
        assert len(results_mixed) == 1

    def test_search_title(self, temp_db):
        """Test searching in chat titles."""
        temp_db.create_chat("chat1", "Python Tutorial")
        temp_db.add_message("chat1", "user", "Let's learn")

        results = temp_db.search_messages("Tutorial")

        assert len(results) == 1
        assert results[0]["chat_id"] == "chat1"
        # Should have title match
        title_matches = [m for m in results[0]["matches"] if m["type"] == "title"]
        assert len(title_matches) > 0

    def test_search_multiple_chats(self, temp_db):
        """Test search across multiple chats."""
        temp_db.create_chat("chat1", "Python Guide")
        temp_db.add_message("chat1", "user", "Learn Python")

        temp_db.create_chat("chat2", "JavaScript Guide")
        temp_db.add_message("chat2", "user", "Learn JavaScript")

        temp_db.create_chat("chat3", "Ruby Guide")
        temp_db.add_message("chat3", "user", "Learn Ruby and Python")

        results = temp_db.search_messages("Python")

        assert len(results) >= 2  # chat1 and chat3
        chat_ids = [r["chat_id"] for r in results]
        assert "chat1" in chat_ids
        assert "chat3" in chat_ids

    def test_search_snippet_format(self, temp_db):
        """Test that search results include proper snippet format."""
        temp_db.create_chat("chat1", "Test")
        temp_db.add_message("chat1", "user", "This is a test message about Python")

        results = temp_db.search_messages("Python")

        assert len(results) == 1
        match = results[0]["matches"][0]
        assert "type" in match
        assert "snippet" in match
        assert match["type"] in ["user", "assistant", "title"]

    def test_search_limit(self, temp_db):
        """Test that limit parameter works."""
        # Create 10 chats with matching content
        for i in range(10):
            temp_db.create_chat(f"chat{i}", f"Chat {i}")
            temp_db.add_message(f"chat{i}", "user", "Python is great")

        results = temp_db.search_messages("Python", limit=5)
        assert len(results) <= 5

    def test_search_snippet_contains_query(self, temp_db):
        """Test that snippets contain the search query."""
        temp_db.create_chat("chat1", "Test")
        temp_db.add_message("chat1", "user", "I love programming in Python")

        results = temp_db.search_messages("Python")

        assert len(results) == 1
        snippet = results[0]["matches"][0]["snippet"]
        # Snippet should contain the query (case-insensitive)
        assert "python" in snippet.lower()

    def test_search_user_and_assistant_messages(self, temp_db):
        """Test searching finds both user and assistant messages."""
        temp_db.create_chat("chat1", "Test")
        temp_db.add_message("chat1", "user", "Tell me about Django")
        temp_db.add_message("chat1", "assistant", "Django is a web framework")

        results = temp_db.search_messages("Django")

        assert len(results) == 1
        assert len(results[0]["matches"]) >= 2

        # Check both user and assistant messages are found
        types = [m["type"] for m in results[0]["matches"]]
        assert "user" in types
        assert "assistant" in types

    def test_fts_table_created(self, temp_db):
        """Test that FTS5 virtual table is created."""
        conn = temp_db.get_conn()

        # Check for messages_fts table
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='messages_fts'
        """)
        result = cursor.fetchone()

        conn.close()
        assert result is not None

    def test_fts_triggers_created(self, temp_db):
        """Test that FTS5 triggers are created."""
        conn = temp_db.get_conn()

        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='trigger' AND name LIKE 'messages_a%'
        """)
        triggers = [row[0] for row in cursor.fetchall()]

        conn.close()

        # Should have insert, update, delete triggers
        assert "messages_ai" in triggers  # after insert
        assert "messages_au" in triggers  # after update
        assert "messages_ad" in triggers  # after delete
