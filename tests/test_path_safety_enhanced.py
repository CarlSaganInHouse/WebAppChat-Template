"""
Tests for enhanced path safety in obsidian.py operations.

Validates that all vault operations properly use safe_vault_path()
and reject traversal attacks.
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian import (
    create_note,
    research_and_save,
    create_note_from_template,
    apply_tags_to_note
)
from utils.vault_security import VaultPathError


@pytest.fixture
def mock_vault(tmp_path, monkeypatch):
    """Create a mock vault directory."""
    vault = tmp_path / "test_vault"
    vault.mkdir()

    # Create standard folders
    (vault / "Daily Notes").mkdir()
    (vault / "Jobs").mkdir()
    (vault / "Reference").mkdir()
    (vault / "Templates").mkdir()

    # Create a test template
    template = vault / "Templates" / "Test.md"
    template.write_text("# {{title}}\n\nContent here")

    # Patch environment
    monkeypatch.setenv('VAULT_PATH', str(vault))

    import importlib
    import config
    import obsidian
    importlib.reload(config)
    importlib.reload(obsidian)

    return vault


class TestCreateNotePathSafety:
    """Test create_note with enhanced path safety."""

    def test_rejects_traversal_in_destination(self, mock_vault):
        """Should reject path traversal in destination."""
        result = create_note(
            content="Test",
            destination="../../../etc/passwd.md",
            mode="create"
        )

        assert result['success'] is False
        assert "escapes vault" in result['error'] or "Invalid" in result['error']

    def test_rejects_absolute_path_destination(self, mock_vault):
        """Should reject absolute path destinations."""
        result = create_note(
            content="Test",
            destination="/etc/passwd.md",
            mode="create"
        )

        assert result['success'] is False
        assert "Invalid" in result['error'] or "absolute" in result['error'].lower()

    def test_rejects_invalid_filename(self, mock_vault):
        """Should reject filenames with path separators."""
        result = create_note(
            content="Test",
            destination="Reference",
            filename="../evil.md",
            mode="create"
        )

        assert result['success'] is False
        assert "Invalid filename" in result['error'] or "path separator" in result['error'].lower()

    def test_accepts_valid_paths(self, mock_vault):
        """Should accept valid, safe paths."""
        result = create_note(
            content="# Test Content",
            destination="Reference",
            filename="test.md",
            mode="create"
        )

        assert result['success'] is True
        note_path = mock_vault / "Reference" / "test.md"
        assert note_path.exists()


class TestResearchAndSavePathSafety:
    """Test research_and_save with enhanced path safety."""

    def test_rejects_traversal_in_save_location(self, mock_vault, monkeypatch):
        """Should reject path traversal in save_location."""
        # Mock the research functionality to skip API calls
        import obsidian
        def mock_research(*args, **kwargs):
            # Just test the path handling part
            pass

        result = research_and_save(
            topic="test",
            save_location="../../../etc/passwd",
            depth="quick"
        )

        # Will fail at path validation before getting to research
        assert result['success'] is False
        assert "Invalid" in result['error'] or "escapes vault" in result['error']

    def test_accepts_valid_folder(self, mock_vault, monkeypatch):
        """Should accept valid folder names."""
        # Mock external API call
        monkeypatch.setenv('OPENAI_API_KEY', '')

        result = research_and_save(
            topic="test topic",
            save_location="Reference",
            depth="quick"
        )

        # May fail on API but should pass path validation
        # Success or error should not be about path traversal
        if not result['success']:
            assert "Invalid save location" not in result['error']
            assert "escapes vault" not in result['error']


class TestTemplatePathSafety:
    """Test create_note_from_template with enhanced path safety."""

    def test_rejects_traversal_in_destination(self, mock_vault):
        """Should reject path traversal in template destination."""
        result = create_note_from_template(
            template_name="Test",
            destination="../../../etc/passwd.md",
            variables={}
        )

        assert result['success'] is False
        assert "Invalid" in result['error'] or "escapes vault" in result['error']

    def test_accepts_valid_destination(self, mock_vault):
        """Should accept valid destinations."""
        result = create_note_from_template(
            template_name="Test",
            destination="Reference",
            variables={"title": "My Test"}
        )

        assert result['success'] is True


class TestApplyTagsPathSafety:
    """Test apply_tags_to_note with enhanced path safety."""

    def test_rejects_traversal_in_file_path(self, mock_vault):
        """Should reject path traversal in file_path."""
        result = apply_tags_to_note(
            file_path="../../../etc/passwd",
            tags=["test"]
        )

        assert result['success'] is False
        assert "escapes vault" in result['error'] or "does not exist" in result['error']

    def test_accepts_valid_file_path(self, mock_vault):
        """Should accept valid file paths."""
        # Create a test note
        note_path = mock_vault / "Reference" / "test.md"
        note_path.write_text("---\ntags: []\n---\n\n# Test")

        result = apply_tags_to_note(
            file_path="Reference/test.md",
            tags=["new-tag"]
        )

        assert result['success'] is True
