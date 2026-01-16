"""
ObsidianService comprehensive unit tests.

Tests for vault operations, daily notes, note CRUD, templates, and search.
Focuses on core functionality and security (path validation).
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.obsidian_service import ObsidianService, get_obsidian_service
from utils.vault_security import VaultPathError


@pytest.fixture
def temp_vault(tmp_path):
    """Create a temporary vault for testing."""
    vault = tmp_path / "test_vault"
    vault.mkdir()

    # Create standard folders
    (vault / "Daily Notes").mkdir()
    (vault / "Jobs").mkdir()
    (vault / "Reference").mkdir()
    (vault / "Templates").mkdir()

    return vault


@pytest.fixture
def obsidian_service(temp_vault, monkeypatch):
    """Create ObsidianService with temporary vault."""
    monkeypatch.setenv('VAULT_PATH', str(temp_vault))

    # Reload config to pick up new env var
    import importlib
    import config
    importlib.reload(config)

    return ObsidianService()


class TestInitialization:
    """Test ObsidianService initialization."""

    def test_creates_instance(self, obsidian_service):
        """Should create instance with vault path."""
        assert obsidian_service.vault_path is not None
        assert obsidian_service.vault_path.exists()


class TestVaultOperations:
    """Test vault-level operations."""

    def test_get_vault_path(self, obsidian_service, temp_vault):
        """Should return vault path."""
        vault_path = obsidian_service.get_vault_path()
        assert vault_path == temp_vault

    def test_get_vault_folders(self, obsidian_service):
        """Should list vault folders."""
        folders = obsidian_service.get_vault_folders()

        assert 'Daily Notes' in folders
        assert 'Jobs' in folders
        assert 'Reference' in folders
        assert 'Templates' in folders


class TestDailyNotes:
    """Test daily note operations."""

    def test_get_daily_note_path(self, obsidian_service, temp_vault):
        """Should generate correct daily note path."""
        note_path, date_str = obsidian_service.get_daily_note_path()

        assert 'Daily Notes' in str(note_path)
        assert date_str in str(note_path)
        assert note_path.suffix == '.md'

    def test_ensure_daily_note_creates_note(self, obsidian_service):
        """Should create daily note if missing."""
        result = obsidian_service.ensure_daily_note()

        assert result['success'] is True
        note_path = Path(result['data']['path'])
        assert note_path.exists()

    def test_ensure_daily_note_idempotent(self, obsidian_service):
        """Should not fail if daily note already exists."""
        # Create once
        result1 = obsidian_service.ensure_daily_note()
        # Create again
        result2 = obsidian_service.ensure_daily_note()

        assert result2['success'] is True

    def test_append_to_daily(self, obsidian_service):
        """Should append content to daily note."""
        result = obsidian_service.append_to_daily(
            content="Test task",
            section="Quick Captures"
        )

        assert result['success'] is True

        # Verify content added
        note_path = Path(result['data']['path'])
        content = note_path.read_text(encoding='utf-8')
        assert "Test task" in content
        assert "## Quick Captures" in content

    def test_append_to_daily_does_not_duplicate_sections(self, obsidian_service):
        """Should not duplicate section headers."""
        obsidian_service.append_to_daily("Task 1", "Tasks")
        result = obsidian_service.append_to_daily("Task 2", "Tasks")

        note_path = Path(result['data']['path'])
        content = note_path.read_text(encoding='utf-8')

        assert content.count("## Tasks") == 1
        assert "Task 1" in content
        assert "Task 2" in content


class TestNoteCreation:
    """Test note creation operations."""

    def test_create_note(self, obsidian_service):
        """Should create new note."""
        result = obsidian_service.create_note(
            title="Test Note",
            content="Test content",
            folder="Reference"
        )

        assert result['success'] is True
        note_path = Path(result['path'])
        assert note_path.exists()
        assert note_path.name == "Test Note.md"

        content = note_path.read_text(encoding='utf-8')
        assert "Test content" in content

    def test_create_note_with_tags(self, obsidian_service):
        """Should create note with frontmatter tags."""
        result = obsidian_service.create_note(
            title="Tagged Note",
            content="Content",
            folder="Reference",
            tags=["tag1", "tag2"]
        )

        assert result['success'] is True
        note_path = Path(result['path'])
        content = note_path.read_text(encoding='utf-8')

        assert "tags:" in content
        assert "tag1" in content
        assert "tag2" in content

    def test_create_note_sanitizes_filename(self, obsidian_service):
        """Should sanitize unsafe characters in filename."""
        result = obsidian_service.create_note(
            title="Test/Note:With|Invalid*Chars",
            content="Content"
        )

        assert result['success'] is True
        # Filename should not contain invalid chars
        note_path = Path(result['path'])
        assert '/' not in note_path.name
        assert ':' not in note_path.name
        assert '|' not in note_path.name
        assert '*' not in note_path.name


class TestNoteReading:
    """Test note reading operations."""

    def test_read_note(self, obsidian_service, temp_vault):
        """Should read existing note."""
        # Create a test note
        test_note = temp_vault / "Reference" / "test.md"
        test_note.write_text("Test content", encoding='utf-8')

        result = obsidian_service.read_note("Reference/test.md")

        assert result['success'] is True
        assert result['content'] == "Test content"

    def test_read_note_nonexistent(self, obsidian_service):
        """Should return error for nonexistent note."""
        result = obsidian_service.read_note("Reference/nonexistent.md")

        assert result['success'] is False
        assert 'not found' in result['message'].lower()


class TestNoteUpdating:
    """Test note updating operations."""

    def test_update_note_section(self, obsidian_service, temp_vault):
        """Should update specific section in note."""
        # Create note with sections
        test_note = temp_vault / "Reference" / "test.md"
        test_note.write_text(
            "# Header\n\n## Section 1\nOriginal\n\n## Section 2\nContent",
            encoding='utf-8'
        )

        result = obsidian_service.update_note_section(
            note_path="Reference/test.md",
            section_title="Section 1",
            new_content="Updated content"
        )

        assert result['success'] is True

        # Verify section updated
        content = test_note.read_text(encoding='utf-8')
        assert "Updated content" in content
        assert "Section 2" in content  # Other sections preserved


class TestNoteDeletion:
    """Test note deletion operations."""

    def test_delete_note(self, obsidian_service, temp_vault):
        """Should delete existing note."""
        # Create a test note
        test_note = temp_vault / "Reference" / "to_delete.md"
        test_note.write_text("Content", encoding='utf-8')

        result = obsidian_service.delete_note("Reference/to_delete.md")

        assert result['success'] is True
        assert not test_note.exists()

    def test_delete_note_nonexistent(self, obsidian_service):
        """Should handle deleting nonexistent note."""
        result = obsidian_service.delete_note("Reference/nonexistent.md")

        assert result['success'] is False


class TestVaultSearch:
    """Test vault search operations."""

    def test_search_vault(self, obsidian_service, temp_vault):
        """Should search vault for keyword."""
        # Create test notes
        note1 = temp_vault / "test1.md"
        note1.write_text("This contains the search term")

        note2 = temp_vault / "test2.md"
        note2.write_text("This does not contain it")

        result = obsidian_service.search_vault("search term")

        assert result['success'] is True
        assert len(result['results']) > 0
        assert any('test1.md' in r['path'] for r in result['results'])

    def test_search_vault_case_insensitive(self, obsidian_service, temp_vault):
        """Should perform case-insensitive search."""
        note = temp_vault / "test.md"
        note.write_text("UPPERCASE CONTENT")

        result = obsidian_service.search_vault("uppercase content")

        assert result['success'] is True
        assert len(result['results']) > 0


class TestTemplates:
    """Test template operations."""

    def test_list_templates(self, obsidian_service, temp_vault):
        """Should list all templates."""
        # Create template files
        (temp_vault / "Templates" / "template1.md").write_text("Template 1")
        (temp_vault / "Templates" / "template2.md").write_text("Template 2")

        result = obsidian_service.list_templates()

        assert result['success'] is True
        assert len(result['templates']) == 2

    def test_create_note_from_template(self, obsidian_service, temp_vault):
        """Should create note from template with variable substitution."""
        # Create template
        template = temp_vault / "Templates" / "Meeting.md"
        template.write_text("# {{title}}\nDate: {{date}}\nContent here")

        result = obsidian_service.create_note_from_template(
            template_name="Meeting",
            title="Team Meeting",
            folder="Reference"
        )

        assert result['success'] is True
        note_path = Path(result['path'])
        content = note_path.read_text(encoding='utf-8')

        assert "# Team Meeting" in content
        assert "{{title}}" not in content  # Variable substituted


class TestTagManagement:
    """Test tag management operations."""

    def test_get_all_tags(self, obsidian_service, temp_vault):
        """Should extract all tags from vault."""
        # Create notes with tags
        note1 = temp_vault / "note1.md"
        note1.write_text("---\ntags: [tag1, tag2]\n---\nContent")

        note2 = temp_vault / "note2.md"
        note2.write_text("---\ntags: [tag2, tag3]\n---\nContent")

        result = obsidian_service.get_all_tags()

        assert result['success'] is True
        tags = result['tags']
        assert 'tag1' in tags
        assert 'tag2' in tags
        assert 'tag3' in tags

    def test_apply_tags_to_note(self, obsidian_service, temp_vault):
        """Should apply tags to note frontmatter."""
        note = temp_vault / "Reference" / "test.md"
        note.write_text("# Test Note\nContent")

        result = obsidian_service.apply_tags_to_note(
            note_path="Reference/test.md",
            tags=["new-tag1", "new-tag2"]
        )

        assert result['success'] is True

        # Verify tags added
        content = note.read_text(encoding='utf-8')
        assert "tags:" in content
        assert "new-tag1" in content


class TestPathSecurity:
    """Test path traversal protection."""

    def test_prevents_path_traversal_in_create(self, obsidian_service):
        """Should prevent path traversal in note creation."""
        result = obsidian_service.create_note(
            title="../../etc/passwd",
            content="malicious"
        )

        # Should either fail or sanitize path
        if result['success']:
            # If it succeeded, verify it's still within vault
            note_path = Path(result['path'])
            vault_path = obsidian_service.vault_path
            assert vault_path in note_path.parents

    def test_prevents_path_traversal_in_read(self, obsidian_service):
        """Should prevent path traversal in note reading."""
        result = obsidian_service.read_note("../../../etc/passwd")

        assert result['success'] is False
        assert 'outside vault' in result['message'].lower() or 'not found' in result['message'].lower()

    def test_prevents_path_traversal_in_delete(self, obsidian_service):
        """Should prevent path traversal in note deletion."""
        result = obsidian_service.delete_note("../../../important.md")

        assert result['success'] is False


class TestDryRunMode:
    """Test dry-run functionality."""

    def test_create_note_dry_run(self, obsidian_service):
        """Should preview note creation without writing."""
        result = obsidian_service.create_note(
            title="Dry Run Note",
            content="Content",
            dry_run=True
        )

        assert result['success'] is True
        assert 'would create' in result['message'].lower()

        # Verify note NOT created
        note_path = Path(result['path'])
        assert not note_path.exists()

    def test_delete_note_dry_run(self, obsidian_service, temp_vault):
        """Should preview note deletion without actually deleting."""
        # Create a test note
        test_note = temp_vault / "Reference" / "test.md"
        test_note.write_text("Content")

        result = obsidian_service.delete_note(
            note_path="Reference/test.md",
            dry_run=True
        )

        assert result['success'] is True
        # Note should still exist
        assert test_note.exists()


class TestSingletonAccess:
    """Test singleton pattern."""

    def test_get_obsidian_service_returns_singleton(self):
        """Should return same instance on multiple calls."""
        service1 = get_obsidian_service()
        service2 = get_obsidian_service()

        assert service1 is service2


class TestJobNotes:
    """Test job note creation (deprecated)."""

    def test_create_job_note_deprecated(self, obsidian_service):
        """Should return deprecation error."""
        result = obsidian_service.create_job_note(
            job_number="1234",
            job_name="Test Project"
        )

        # Function is deprecated - should return error
        assert result['success'] is False
        assert 'deprecated' in result.get('error', '').lower() or result.get('data', {}).get('deprecated', False)
