"""
Basic Obsidian vault operation tests.

Tests for daily notes, note creation, and path security.
"""

import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import sys
import os

# Add parent directory to path to import obsidian module
sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian import (
    append_to_daily,
    read_daily_note,
    create_note,
    update_note_section,
    replace_note_content,
    delete_note,
    get_daily_note_path,
)
from utils.vault_security import VaultPathError


@pytest.fixture
def mock_vault(tmp_path, monkeypatch):
    """
    Create a mock vault directory and configure obsidian module to use it.
    """
    vault = tmp_path / "test_vault"
    vault.mkdir()

    # Create standard folders
    (vault / "Daily Notes").mkdir()
    (vault / "Jobs").mkdir()
    (vault / "Reference").mkdir()
    (vault / "Templates").mkdir()

    # Patch the VAULT_PATH in environment and reload modules
    monkeypatch.setenv('VAULT_PATH', str(vault))

    # Reload config and obsidian modules to pick up new env var
    import importlib
    import config
    import obsidian
    importlib.reload(config)
    importlib.reload(obsidian)

    return vault


class TestAppendToDaily:
    """Test append_to_daily function."""

    def test_creates_daily_note_if_missing(self, mock_vault):
        """Should create today's daily note if it doesn't exist."""
        result = append_to_daily("Test content", "Quick Captures")

        assert result['success'] is True
        data = result.get('data', {})
        target_date = data.get('date')
        assert target_date in result['message']

        # Verify file was created
        note_path = mock_vault / data['path']
        assert note_path.exists()

    def test_appends_to_existing_note(self, mock_vault):
        """Should append to existing daily note."""
        # Create an initial note
        note_path_obj, target_date = get_daily_note_path()
        note_path = Path(note_path_obj)
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("# Existing content\n\n## Quick Captures\n", encoding='utf-8')

        # Append new content
        result = append_to_daily("New task", "Quick Captures", date=target_date)

        assert result['success'] is True

        # Verify content was added
        content = note_path.read_text(encoding='utf-8')
        assert "New task" in content

    def test_section_not_duplicated(self, mock_vault):
        """Should not duplicate section headers."""
        note_path_obj, target_date = get_daily_note_path()
        append_to_daily("Task 1", "Tasks", date=target_date)
        append_to_daily("Task 2", "Tasks", date=target_date)

        note_path = Path(note_path_obj)
        content = note_path.read_text(encoding='utf-8')

        # Section should appear only once
        assert content.count("## Tasks") == 1
        assert "Task 1" in content
        assert "Task 2" in content

    def test_append_with_custom_date(self, mock_vault):
        """Should create and append to a specified date."""
        custom_date = "2024-10-30"
        result = append_to_daily("Historical entry", "Work Notes", date=custom_date)

        assert result['success'] is True
        data = result.get('data', {})
        assert data.get('date') == custom_date
        note_path = mock_vault / data['path']
        assert note_path.exists()
        content = note_path.read_text(encoding='utf-8')
        assert "Historical entry" in content
        assert "## Work Notes" in content


class TestReadDailyNote:
    """Test read_daily_note function."""

    def test_reads_existing_note(self, mock_vault):
        """Should read an existing daily note."""
        # Create a test note
        date_str = "2024-10-30"
        note_path = mock_vault / "Daily Notes" / f"{date_str}.md"
        test_content = "# Test Content\n\nSome notes here."
        note_path.write_text(test_content)

        result = read_daily_note(date_str)

        assert result['success'] is True
        assert result['date'] == date_str
        assert test_content in result['content']

    def test_missing_note_returns_error(self, mock_vault):
        """Should return error for non-existent note."""
        result = read_daily_note("2024-01-01")

        assert result['success'] is False
        assert "does not exist" in result['error']

    def test_path_traversal_blocked(self, mock_vault):
        """Should block path traversal attempts."""
        result = read_daily_note("../../../etc/passwd")

        assert result['success'] is False
        assert "escapes vault" in result['error'] or "does not exist" in result['error']


class TestCreateNote:
    """Test create_note function."""

    def test_creates_note_in_folder(self, mock_vault):
        """Should create a note in specified folder."""
        result = create_note(
            content="# Test Note\n\nContent here.",
            destination="Reference",
            filename="test-note.md",
            mode="create"
        )

        assert result['success'] is True
        assert result['action'] == "created"

        # Verify file exists
        note_path = mock_vault / "Reference" / "test-note.md"
        assert note_path.exists()
        assert "Test Note" in note_path.read_text()

    def test_create_mode_fails_if_exists(self, mock_vault):
        """Create mode should fail if file already exists."""
        # Create initial file
        create_note("Initial", "Reference", "existing.md", "create")

        # Try to create again
        result = create_note("New content", "Reference", "existing.md", "create")

        assert result['success'] is False
        assert "already exists" in result['error']

    def test_append_mode_adds_content(self, mock_vault):
        """Append mode should add to existing file."""
        # Create initial file
        create_note("Initial content", "Reference", "test.md", "create")

        # Append new content
        result = create_note("New content", "Reference", "test.md", "append")

        assert result['success'] is True
        assert result['action'] == "appended"

        # Verify both contents present
        content = (mock_vault / "Reference" / "test.md").read_text()
        assert "Initial content" in content
        assert "New content" in content

    def test_overwrite_mode_replaces_content(self, mock_vault):
        """Overwrite mode should replace existing file."""
        # Create initial file
        create_note("Initial content", "Reference", "test.md", "create")

        # Overwrite
        result = create_note("New content only", "Reference", "test.md", "overwrite")

        assert result['success'] is True
        assert result['action'] == "overwritten"

        # Verify only new content present
        content = (mock_vault / "Reference" / "test.md").read_text()
        assert "Initial content" not in content
        assert "New content only" in content


class TestUpdateNoteSection:
    """Test update_note_section function."""

    def test_updates_existing_section(self, mock_vault):
        """Should update an existing section in a note."""
        # Create note with sections
        note_path = mock_vault / "Daily Notes" / "2024-10-30.md"
        note_path.write_text("""# Daily Note

## Work Notes
Old work content

## Personal Notes
Personal stuff
""")

        result = update_note_section(
            "Daily Notes/2024-10-30.md",
            "Work Notes",
            "New work content here"
        )

        assert result['success'] is True

        content = note_path.read_text()
        assert "New work content here" in content
        assert "Old work content" not in content
        assert "Personal stuff" in content  # Other sections unchanged

    def test_section_not_found_returns_error(self, mock_vault):
        """Should return error if section doesn't exist."""
        note_path = mock_vault / "Daily Notes" / "2024-10-30.md"
        note_path.write_text("# Daily Note\n\n## Tasks\n")

        result = update_note_section(
            "Daily Notes/2024-10-30.md",
            "Nonexistent Section",
            "Content"
        )

        assert result['success'] is False
        assert "not found" in result['error']

    def test_path_traversal_blocked(self, mock_vault):
        """Should block path traversal in file_path."""
        result = update_note_section(
            "../../../etc/passwd",
            "Section",
            "Malicious content"
        )

        assert result['success'] is False
        assert "escapes vault" in result['error']


class TestDeleteNote:
    """Test delete_note function."""

    def test_delete_note(self, mock_vault):
        """Should delete an existing note."""
        file_path = mock_vault / "Reference" / "temp.md"
        file_path.write_text("Temporary note", encoding='utf-8')

        result = delete_note("Reference/temp.md", dry_run=False)

        assert result['success'] is True
        assert "Deleted note" in result['message']
        assert not file_path.exists()

    def test_delete_note_dry_run(self, mock_vault):
        """Dry run should not delete file."""
        file_path = mock_vault / "Reference" / "preview.md"
        file_path.write_text("Preview note", encoding='utf-8')

        result = delete_note("Reference/preview.md", dry_run=True)

        assert result['success'] is True
        assert result.get('dry_run') is True
        assert "Would delete note" in result['message']
        assert file_path.exists()


class TestReplaceNoteContent:
    """Test replace_note_content function."""

    def test_replaces_text(self, mock_vault):
        """Should find and replace text in note."""
        note_path = mock_vault / "Reference" / "test.md"
        note_path.write_text("Status: draft\n\nMore content here.")

        result = replace_note_content(
            "Reference/test.md",
            "Status: draft",
            "Status: published"
        )

        assert result['success'] is True
        assert result['count'] == 1

        content = note_path.read_text()
        assert "Status: published" in content
        assert "Status: draft" not in content

    def test_text_not_found_returns_error(self, mock_vault):
        """Should return error if text to replace not found."""
        note_path = mock_vault / "Reference" / "test.md"
        note_path.write_text("Some content")

        result = replace_note_content(
            "Reference/test.md",
            "Nonexistent text",
            "Replacement"
        )

        assert result['success'] is False
        assert "not found" in result['error']

    def test_replaces_all_occurrences(self, mock_vault):
        """Should replace all occurrences of text."""
        note_path = mock_vault / "Reference" / "test.md"
        note_path.write_text("TODO item 1\nTODO item 2\nTODO item 3")

        result = replace_note_content(
            "Reference/test.md",
            "TODO",
            "DONE"
        )

        assert result['success'] is True
        assert result['count'] == 3

        content = note_path.read_text()
        assert content.count("DONE") == 3
        assert "TODO" not in content

    def test_path_traversal_blocked(self, mock_vault):
        """Should block path traversal attacks."""
        result = replace_note_content(
            "../../etc/passwd",
            "old",
            "new"
        )

        assert result['success'] is False
        assert "escapes vault" in result['error']
