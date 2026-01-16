"""
Tests for Pydantic parameter validation in obsidian_tool_models.py
"""

import pytest
from pydantic import ValidationError
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from obsidian_tool_models import (
    AppendToDailyNoteParams,
    CreateSimpleNoteParams,
    UpdateNoteSectionParams,
    CreateFromTemplateParams
)


class TestAppendToDailyNoteValidation:
    """Test AppendToDailyNoteParams validation."""

    def test_valid_parameters(self):
        """Should accept valid parameters."""
        params = AppendToDailyNoteParams(
            content="Test content",
            section="Quick Captures"
        )
        assert params.content == "Test content"
        assert params.section == "Quick Captures"

    def test_rejects_empty_content(self):
        """Should reject empty/whitespace content."""
        with pytest.raises(ValidationError) as exc:
            AppendToDailyNoteParams(content="   ")

        errors = exc.value.errors()
        assert any("empty" in str(e['msg']).lower() for e in errors)

    def test_rejects_invalid_section(self):
        """Should reject invalid section names."""
        with pytest.raises(ValidationError):
            AppendToDailyNoteParams(
                content="Test",
                section="Invalid Section"
            )

    def test_default_section(self):
        """Should use default section if not provided."""
        params = AppendToDailyNoteParams(content="Test")
        assert params.section == "Quick Captures"


class TestCreateSimpleNoteValidation:
    """Test CreateSimpleNoteParams validation."""

    def test_valid_parameters(self):
        """Should accept valid parameters."""
        params = CreateSimpleNoteParams(
            title="My Note",
            content="Note content here",
            folder="Reference"
        )
        assert params.title == "My Note"
        assert params.folder == "Reference"

    def test_rejects_path_separators_in_title(self):
        """Should reject path separators in title."""
        with pytest.raises(ValidationError) as exc:
            CreateSimpleNoteParams(
                title="../etc/passwd",
                content="Test",
                folder="Reference"
            )

        errors = exc.value.errors()
        assert any("separator" in str(e['msg']).lower() for e in errors)

    def test_rejects_traversal_in_folder(self):
        """Should reject traversal attempts in folder."""
        with pytest.raises(ValidationError) as exc:
            CreateSimpleNoteParams(
                title="Test",
                content="Content",
                folder="../etc"
            )

        errors = exc.value.errors()
        assert any("invalid" in str(e['msg']).lower() for e in errors)


class TestUpdateNoteSectionValidation:
    """Test UpdateNoteSectionParams validation."""

    def test_valid_parameters(self):
        """Should accept valid parameters."""
        params = UpdateNoteSectionParams(
            file_path="Daily Notes/2025-10-30.md",
            section_name="Work Notes",
            new_content="Updated content"
        )
        assert params.file_path == "Daily Notes/2025-10-30.md"
        assert params.section_name == "Work Notes"

    def test_rejects_non_md_file_path(self):
        """Should reject file paths without .md extension."""
        with pytest.raises(ValidationError) as exc:
            UpdateNoteSectionParams(
                file_path="Daily Notes/note.txt",
                section_name="Section",
                new_content="Content"
            )

        errors = exc.value.errors()
        assert any(".md" in str(e['msg']) for e in errors)

    def test_rejects_absolute_paths(self):
        """Should reject absolute paths."""
        with pytest.raises(ValidationError):
            UpdateNoteSectionParams(
                file_path="/etc/passwd.md",
                section_name="Section",
                new_content="Content"
            )

    def test_rejects_hash_prefix_in_section_name(self):
        """Should reject section names with # prefix."""
        with pytest.raises(ValidationError) as exc:
            UpdateNoteSectionParams(
                file_path="test.md",
                section_name="## Work Notes",  # Has ##
                new_content="Content"
            )

        errors = exc.value.errors()
        assert any("#" in str(e['msg']) for e in errors)


class TestCreateFromTemplateValidation:
    """Test CreateFromTemplateParams validation."""

    def test_valid_parameters(self):
        """Should accept valid parameters."""
        params = CreateFromTemplateParams(
            template_name="Meeting Notes",
            destination="Meetings",
            variables={"title": "Project Review"}
        )
        assert params.template_name == "Meeting Notes"
        assert params.destination == "Meetings"
        assert params.variables == {"title": "Project Review"}

    def test_strips_md_extension_from_template_name(self):
        """Should remove .md extension if provided."""
        params = CreateFromTemplateParams(
            template_name="Meeting Notes.md",
            destination="Meetings"
        )
        assert params.template_name == "Meeting Notes"

    def test_rejects_path_separators_in_template_name(self):
        """Should reject path separators in template name."""
        with pytest.raises(ValidationError) as exc:
            CreateFromTemplateParams(
                template_name="../etc/template",
                destination="Meetings"
            )

        errors = exc.value.errors()
        assert any("separator" in str(e['msg']).lower() for e in errors)

    def test_rejects_absolute_destination(self):
        """Should reject absolute destination paths."""
        with pytest.raises(ValidationError):
            CreateFromTemplateParams(
                template_name="Meeting",
                destination="/etc/meetings"
            )


class TestIntegrationWithExecuteFunction:
    """Test that validation is properly integrated with execute_obsidian_function."""

    def test_validation_error_returns_helpful_message(self):
        """Validation errors should return helpful messages to the LLM."""
        from obsidian_functions import execute_obsidian_function

        # Test with invalid job number (no digits)
        result = execute_obsidian_function(
            "create_job_note",
            {
                "job_number": "General Meeting",  # Invalid
                "job_name": "Test"
            }
        )

        assert result['success'] is False
        assert "Invalid parameters" in result['message']
        assert "digit" in result['message'].lower()
        # Should guide to correct function
        assert "create_simple_note" in result['message'].lower()

    def test_valid_parameters_pass_validation(self):
        """Valid parameters should pass through validation."""
        from obsidian_functions import execute_obsidian_function

        # This will fail later (vault setup), but should pass Pydantic validation
        result = execute_obsidian_function(
            "create_job_note",
            {
                "job_number": "1234",
                "job_name": "Test Project",
                "client": "Acme"
            }
        )

        # Should not fail at validation stage
        if not result['success']:
            assert "Invalid parameters" not in result['message']
            assert "ValidationError" not in str(result.get('error', ''))
