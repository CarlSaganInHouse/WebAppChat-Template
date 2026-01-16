"""
Tests for standardized response format and dry-run functionality.
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian import (
    append_to_daily,
    create_job_note,
    update_note_section
)


@pytest.fixture
def mock_vault(tmp_path, monkeypatch):
    """Create a mock vault directory."""
    vault = tmp_path / "test_vault"
    vault.mkdir()

    # Create standard folders
    (vault / "Daily Notes").mkdir()
    (vault / "Jobs").mkdir()
    (vault / "Reference").mkdir()

    # Patch environment
    monkeypatch.setenv('VAULT_PATH', str(vault))

    import importlib
    import config
    import obsidian
    importlib.reload(config)
    importlib.reload(obsidian)

    return vault


class TestStandardizedResponseFormat:
    """Test that responses follow the standardized format."""

    def test_success_response_format(self, mock_vault):
        """Success responses should have consistent format."""
        result = append_to_daily("Test content", "Quick Captures")

        # Standard fields
        assert "success" in result
        assert result["success"] is True
        assert "message" in result
        assert isinstance(result["message"], str)

        # New data field
        assert "data" in result
        assert isinstance(result["data"], dict)
        assert "path" in result["data"]
        assert "section" in result["data"]
        assert "action" in result["data"]

        # Legacy field preserved for backward compatibility
        assert "path" in result

    def test_error_response_format(self, mock_vault):
        """Error responses should have consistent format."""
        # Create a note to test section update
        note_path = mock_vault / "Daily Notes" / "test.md"
        note_path.write_text("# Test\n\n## Section1\nContent")

        result = update_note_section(
            "Daily Notes/test.md",
            "NonexistentSection",
            "New content"
        )

        # Standard error fields
        assert "success" in result
        assert result["success"] is False
        assert "error" in result
        assert isinstance(result["error"], str)

        # Error data
        assert "data" in result
        assert "available_sections" in result["data"]

    @pytest.mark.skip(reason="create_job_note is deprecated - function returns deprecation error")
    def test_job_note_error_with_data(self, mock_vault):
        """Job note error should include useful data."""
        # Create job note first
        create_job_note("1234", "Test Job")

        # Try to create again
        result = create_job_note("1234", "Test Job")

        assert result["success"] is False
        assert "error" in result
        assert "already exists" in result["error"].lower()

        # Should have data about the existing note
        assert "data" in result
        assert result["data"]["exists"] is True
        assert result["data"]["job_number"] == "1234"


class TestDryRunFunctionality:
    """Test dry-run preview mode."""

    def test_append_to_daily_dry_run(self, mock_vault):
        """Dry run should preview without executing."""
        # Dry run
        result = append_to_daily("Test content", "Tasks", dry_run=True)

        # Should indicate dry run
        assert result["success"] is True
        assert result.get("dry_run") is True
        assert "Would append" in result["message"]

        # Should have preview data
        assert "data" in result
        assert result["data"]["action"] == "append"
        assert result["data"]["section"] == "Tasks"
        assert "content_length" in result["data"]

        # Should NOT actually create the note
        today_note = list((mock_vault / "Daily Notes").glob("*.md"))
        # Daily note might exist from ensure_daily_note, but content should not be there
        if today_note:
            content = today_note[0].read_text(encoding='utf-8')
            assert "Test content" not in content

    @pytest.mark.skip(reason="create_job_note is deprecated - function returns deprecation error")
    def test_create_job_note_dry_run(self, mock_vault):
        """Dry run should preview job note creation."""
        result = create_job_note("1234", "Test Job", "Acme Corp", dry_run=True)

        assert result["success"] is True
        assert result.get("dry_run") is True
        assert "Would create" in result["message"]

        # Should have preview data
        assert "data" in result
        assert result["data"]["job_number"] == "1234"
        assert result["data"]["job_name"] == "Test Job"
        assert result["data"]["client"] == "Acme Corp"
        assert result["data"]["action"] == "create"

        # Should NOT actually create the job folder
        assert not (mock_vault / "Jobs" / "1234 - Test Job").exists()

    def test_update_note_section_dry_run(self, mock_vault):
        """Dry run should preview section update."""
        # Create a test note
        note_path = mock_vault / "Reference" / "test.md"
        note_path.write_text("# Test\n\n## Overview\nOld content here\n\n## Details\nMore stuff")

        result = update_note_section(
            "Reference/test.md",
            "Overview",
            "New content here",
            dry_run=True
        )

        assert result["success"] is True
        assert result.get("dry_run") is True
        assert "Would update" in result["message"]

        # Should have preview data
        assert "data" in result
        assert result["data"]["section"] == "Overview"
        assert "old_content_preview" in result["data"]
        assert "new_content_preview" in result["data"]
        assert result["data"]["old_length"] > 0
        assert result["data"]["new_length"] > 0

        # Should NOT actually modify the note
        content = note_path.read_text()
        assert "Old content here" in content
        assert "New content here" not in content

    @pytest.mark.skip(reason="create_job_note is deprecated - function returns deprecation error")
    def test_dry_run_then_real_execution(self, mock_vault):
        """Can preview with dry_run=True, then execute with dry_run=False."""
        # Preview
        preview = create_job_note("5678", "Another Job", dry_run=True)
        assert preview["dry_run"] is True
        assert not (mock_vault / "Jobs" / "5678 - Another Job").exists()

        # Execute for real
        result = create_job_note("5678", "Another Job", dry_run=False)
        assert "dry_run" not in result or result.get("dry_run") is False
        assert result["success"] is True
        assert (mock_vault / "Jobs" / "5678 - Another Job").exists()


class TestBackwardCompatibility:
    """Test that legacy code still works."""

    def test_legacy_path_field_present(self, mock_vault):
        """Legacy 'path' field should still be available."""
        result = append_to_daily("Test", "Quick Captures")

        # Both new data.path and legacy path should exist
        assert "path" in result  # legacy
        assert "data" in result  # new
        assert "path" in result["data"]  # new location

        # They should have the same value
        assert result["path"] == result["data"]["path"]

    @pytest.mark.skip(reason="create_job_note is deprecated - function returns deprecation error")
    def test_legacy_error_handling(self, mock_vault):
        """Error responses should work with existing error handling code."""
        result = create_job_note("bad", "job")  # Will be created
        result2 = create_job_note("bad", "job")  # Will fail

        # Old code checking for result['success'] should work
        assert result2["success"] is False

        # Old code checking for result.get('error') should work
        assert result2.get("error") is not None
        assert isinstance(result2["error"], str)
