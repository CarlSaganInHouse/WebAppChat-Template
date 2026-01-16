"""
Comprehensive Test Suite for Obsidian Verification System

Tests all three phases of the verification implementation:
- Phase 1: Verification coverage for all 11 write operations
- Phase 2: Retry logic for failed verifications
- Phase 3: System prompt verification guidance

Run with: pytest tests/test_verification_system.py -v
"""

import os
import sys
import json
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.obsidian_verification import (
    verify_operation,
    VerificationResult,
    WRITE_OPERATIONS,
    FILE_CREATION_OPS,
    CONTENT_APPEND_OPS,
    CONTENT_UPDATE_OPS,
    METADATA_OPS,
    TASK_OPS,
    RESEARCH_OPS,
    format_verification_failure,
)
from services.tool_calling_service import ToolCallingService
from routes.chat_routes import verify_tool_result, WRITE_VERIFICATION_FUNCTIONS


class TestVerificationModule:
    """Test the core verification module (utils/obsidian_verification.py)"""

    def test_write_operations_set_has_11_operations(self):
        """Verify all 11 write operations are in the set"""
        assert len(WRITE_OPERATIONS) == 11
        expected_ops = {
            "create_simple_note",
            "create_job_note",
            "create_from_template",
            "create_custom_template",
            "update_note",
            "update_note_section",
            "replace_note_content",
            "append_to_daily_note",
            "apply_tags_to_note",
            "research_and_save",
            "create_scheduled_task",
        }
        assert WRITE_OPERATIONS == expected_ops

    def test_operation_categories_are_complete(self):
        """Verify all operations are categorized"""
        all_categorized = (
            FILE_CREATION_OPS |
            CONTENT_APPEND_OPS |
            CONTENT_UPDATE_OPS |
            METADATA_OPS |
            TASK_OPS |
            RESEARCH_OPS
        )
        # Note: update_note is in CONTENT_UPDATE_OPS
        assert all_categorized == WRITE_OPERATIONS

    def test_verification_result_dataclass(self):
        """Test VerificationResult dataclass structure"""
        result = VerificationResult(
            success=True,
            operation="test_op",
            details="Test details",
            checks_passed=["check1", "check2"],
            checks_failed=[],
            suggestions=[]
        )
        assert result.success is True
        assert result.operation == "test_op"
        assert len(result.checks_passed) == 2

    def test_non_write_operation_skips_verification(self):
        """Non-write operations should pass without verification"""
        result = verify_operation(
            "search_vault",  # Not a write operation
            {"query": "test"},
            {"success": True}
        )
        assert result.success is True
        assert "not_write_operation" in result.checks_passed

    def test_failed_operation_skips_verification(self):
        """Operations that reported failure should skip verification"""
        result = verify_operation(
            "create_simple_note",
            {"title": "Test", "content": "Content"},
            {"success": False, "error": "Some error"}
        )
        assert result.success is True
        assert "operation_failure_skipped" in result.checks_passed


class TestFileCreationVerification:
    """Test verification for file creation operations"""

    @pytest.fixture
    def temp_vault(self):
        """Create a temporary vault directory for testing"""
        vault_dir = tempfile.mkdtemp(prefix="test_vault_")
        yield vault_dir
        shutil.rmtree(vault_dir, ignore_errors=True)

    def test_verify_file_exists(self, temp_vault):
        """Test that file existence is verified"""
        # Create a test file
        test_file = Path(temp_vault) / "test_note.md"
        test_file.write_text("# Test Note\n\nSome content here.")

        result = verify_operation(
            "create_simple_note",
            {"title": "Test Note", "content": "Some content here."},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is True
        assert "file_exists" in result.checks_passed

    def test_verify_file_not_found_fails(self, temp_vault):
        """Test that missing file fails verification"""
        nonexistent_file = Path(temp_vault) / "does_not_exist.md"

        result = verify_operation(
            "create_simple_note",
            {"title": "Test", "content": "Content"},
            {"success": True, "file_path": str(nonexistent_file)}
        )

        assert result.success is False
        assert any("not exist" in check.lower() or "not found" in check.lower()
                   for check in result.checks_failed)

    def test_verify_empty_file_fails(self, temp_vault):
        """Test that empty files fail verification"""
        test_file = Path(temp_vault) / "empty_note.md"
        test_file.write_text("")  # Empty file

        result = verify_operation(
            "create_simple_note",
            {"title": "Empty", "content": "Should have content"},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is False
        assert any("empty" in check.lower() for check in result.checks_failed)

    def test_verify_content_mismatch_fails(self, temp_vault):
        """Test that content mismatch fails verification"""
        test_file = Path(temp_vault) / "wrong_content.md"
        test_file.write_text("# Wrong Content\n\nThis is different content.")

        result = verify_operation(
            "create_simple_note",
            {"title": "Test", "content": "Expected content that is not present"},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is False
        assert any("mismatch" in check.lower() or "not found" in check.lower()
                   for check in result.checks_failed)

    def test_verify_content_match_passes(self, temp_vault):
        """Test that matching content passes verification"""
        expected_content = "This is the expected content."
        test_file = Path(temp_vault) / "correct_note.md"
        test_file.write_text(f"# Test Note\n\n{expected_content}")

        result = verify_operation(
            "create_simple_note",
            {"title": "Test Note", "content": expected_content},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is True
        assert "content_verified" in result.checks_passed


class TestContentAppendVerification:
    """Test verification for content append operations"""

    @pytest.fixture
    def temp_vault(self):
        vault_dir = tempfile.mkdtemp(prefix="test_vault_")
        yield vault_dir
        shutil.rmtree(vault_dir, ignore_errors=True)

    def test_verify_appended_content_present(self, temp_vault):
        """Test that appended content is found in file"""
        appended_text = "This was appended to the daily note."
        test_file = Path(temp_vault) / "daily_note.md"
        test_file.write_text(f"# Daily Note\n\n## Quick Captures\n\n{appended_text}")

        result = verify_operation(
            "append_to_daily_note",
            {"content": appended_text, "section": "Quick Captures"},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is True
        assert "content_appended" in result.checks_passed

    def test_verify_appended_content_missing_fails(self, temp_vault):
        """Test that missing appended content fails"""
        test_file = Path(temp_vault) / "daily_note.md"
        test_file.write_text("# Daily Note\n\n## Quick Captures\n\nSome other content.")

        result = verify_operation(
            "append_to_daily_note",
            {"content": "This content is not in the file", "section": "Quick Captures"},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is False
        assert any("not found" in check.lower() for check in result.checks_failed)


class TestContentUpdateVerification:
    """Test verification for content update operations"""

    @pytest.fixture
    def temp_vault(self):
        vault_dir = tempfile.mkdtemp(prefix="test_vault_")
        yield vault_dir
        shutil.rmtree(vault_dir, ignore_errors=True)

    def test_verify_section_exists(self, temp_vault):
        """Test that section header is found"""
        test_file = Path(temp_vault) / "note_with_sections.md"
        test_file.write_text("# Main Title\n\n## Target Section\n\nUpdated content here.")

        result = verify_operation(
            "update_note_section",
            {"section": "Target Section", "content": "Updated content here."},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is True
        assert any("section_exists" in check for check in result.checks_passed)

    def test_verify_replacement_text_present(self, temp_vault):
        """Test that replacement text is found after replace_note_content"""
        test_file = Path(temp_vault) / "replaced_note.md"
        test_file.write_text("# Note\n\nNew replacement text here.")

        result = verify_operation(
            "replace_note_content",
            {"old_text": "Old text", "new_text": "New replacement text"},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is True
        assert "new_content_present" in result.checks_passed


class TestMetadataVerification:
    """Test verification for metadata operations (tags)"""

    @pytest.fixture
    def temp_vault(self):
        vault_dir = tempfile.mkdtemp(prefix="test_vault_")
        yield vault_dir
        shutil.rmtree(vault_dir, ignore_errors=True)

    def test_verify_tags_in_frontmatter(self, temp_vault):
        """Test that tags are found in frontmatter"""
        test_file = Path(temp_vault) / "tagged_note.md"
        test_file.write_text("""---
tags: [project, important, work]
---

# Note with Tags

Content here.""")

        result = verify_operation(
            "apply_tags_to_note",
            {"tags": ["project", "important"]},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is True
        assert any("tags" in check.lower() for check in result.checks_passed)

    def test_verify_missing_frontmatter_fails(self, temp_vault):
        """Test that missing frontmatter fails tag verification"""
        test_file = Path(temp_vault) / "no_frontmatter.md"
        test_file.write_text("# Note Without Frontmatter\n\nNo tags here.")

        result = verify_operation(
            "apply_tags_to_note",
            {"tags": ["test"]},
            {"success": True, "file_path": str(test_file)}
        )

        assert result.success is False
        assert any("frontmatter" in check.lower() for check in result.checks_failed)


class TestTaskVerification:
    """Test verification for scheduled task operations"""

    @pytest.fixture
    def temp_vault(self):
        vault_dir = tempfile.mkdtemp(prefix="test_vault_")
        yield vault_dir
        shutil.rmtree(vault_dir, ignore_errors=True)

    def test_verify_task_file_exists(self, temp_vault):
        """Test that scheduled tasks file is found"""
        tasks_file = Path(temp_vault) / ".scheduled_tasks.json"
        tasks_data = {
            "tasks": [
                {"id": "task_123", "name": "Test Task", "schedule": "daily"}
            ]
        }
        tasks_file.write_text(json.dumps(tasks_data))

        with patch("utils.obsidian_verification.get_settings") as mock_settings:
            mock_settings.return_value.vault_path = Path(temp_vault)

            result = verify_operation(
                "create_scheduled_task",
                {"name": "Test Task", "schedule": "daily"},
                {"success": True, "task_id": "task_123"}
            )

        assert result.success is True
        assert "tasks_file_exists" in result.checks_passed


class TestResearchVerification:
    """Test verification for research_and_save operation"""

    @pytest.fixture
    def temp_vault(self):
        vault_dir = tempfile.mkdtemp(prefix="test_vault_")
        yield vault_dir
        shutil.rmtree(vault_dir, ignore_errors=True)

    def test_verify_research_output_file(self, temp_vault):
        """Test that research output file is verified"""
        test_file = Path(temp_vault) / "research_output.md"
        test_file.write_text("# Research Results\n\nSome research content here.")

        result = verify_operation(
            "research_and_save",
            {"query": "test research"},
            {"success": True, "file_path": str(test_file), "action": "created_new_file"}
        )

        assert result.success is True
        assert "file_exists" in result.checks_passed
        assert any("non_empty" in check for check in result.checks_passed)


class TestRetryLogic:
    """Test the retry logic in ToolCallingService"""

    def test_retry_on_verification_failure(self):
        """Test that retries happen on verification failure"""
        call_count = {"execute": 0, "verify": 0}

        def mock_execute(name, args):
            call_count["execute"] += 1
            return {"success": True, "file_path": "/fake/path.md"}

        def mock_verify(name, args, result):
            call_count["verify"] += 1
            # Fail first 2 times, succeed on 3rd
            if call_count["verify"] <= 2:
                return ("failed", "Verification failed", {"checks_failed": ["test_check"]})
            return ("passed", None, {"checks_passed": ["test_check"]})

        with patch("services.tool_calling_service.get_settings") as mock_settings:
            mock_settings.return_value.verify_vault_writes = True
            mock_settings.return_value.verification_max_retries = 2
            mock_settings.return_value.verification_retry_delay = 0.01  # Fast for testing
            mock_settings.return_value.verification_strict_mode = True

            service = ToolCallingService(
                execute_fn=mock_execute,
                verify_fn=mock_verify,
                log_fn=None,
                validate_fn=None,
            )

            result, status = service.execute_tool_call(
                tool_call_id="test_123",
                function_name="create_simple_note",
                function_args={"title": "Test"},
                model="gpt-4o",
            )

        # Should have executed 3 times (initial + 2 retries)
        assert call_count["execute"] == 3
        assert call_count["verify"] == 3
        assert status == "success"

    def test_max_retries_respected(self):
        """Test that retries stop after max_retries"""
        call_count = {"verify": 0}

        def mock_execute(name, args):
            return {"success": True, "file_path": "/fake/path.md"}

        def mock_verify(name, args, result):
            call_count["verify"] += 1
            # Always fail
            return ("failed", "Always fails", {"checks_failed": ["always_fail"]})

        with patch("services.tool_calling_service.get_settings") as mock_settings:
            mock_settings.return_value.verify_vault_writes = True
            mock_settings.return_value.verification_max_retries = 2
            mock_settings.return_value.verification_retry_delay = 0.01
            mock_settings.return_value.verification_strict_mode = True

            service = ToolCallingService(
                execute_fn=mock_execute,
                verify_fn=mock_verify,
                log_fn=None,
                validate_fn=None,
            )

            result, status = service.execute_tool_call(
                tool_call_id="test_123",
                function_name="create_simple_note",
                function_args={"title": "Test"},
                model="gpt-4o",
            )

        # Should have verified 3 times (initial + 2 retries)
        assert call_count["verify"] == 3
        assert status == "verification_failed"
        assert result.get("success") is False

    def test_no_retry_for_non_write_operations(self):
        """Test that non-write operations don't trigger retries"""
        call_count = {"execute": 0}

        def mock_execute(name, args):
            call_count["execute"] += 1
            return {"success": True, "results": []}

        def mock_verify(name, args, result):
            return ("skipped", None, {"reason": "not_write_operation"})

        with patch("services.tool_calling_service.get_settings") as mock_settings:
            mock_settings.return_value.verify_vault_writes = True
            mock_settings.return_value.verification_max_retries = 2
            mock_settings.return_value.verification_retry_delay = 0.01
            mock_settings.return_value.verification_strict_mode = True

            service = ToolCallingService(
                execute_fn=mock_execute,
                verify_fn=mock_verify,
                log_fn=None,
                validate_fn=None,
            )

            result, status = service.execute_tool_call(
                tool_call_id="test_123",
                function_name="search_vault",  # Not a write operation
                function_args={"query": "test"},
                model="gpt-4o",
            )

        # Should only execute once (no retries for non-write ops)
        assert call_count["execute"] == 1
        assert status == "success"

    def test_non_strict_mode_continues_on_failure(self):
        """Test that non-strict mode doesn't fail on verification failure"""
        def mock_execute(name, args):
            return {"success": True, "file_path": "/fake/path.md"}

        def mock_verify(name, args, result):
            return ("failed", "Verification failed", {"checks_failed": ["test"]})

        with patch("services.tool_calling_service.get_settings") as mock_settings:
            mock_settings.return_value.verify_vault_writes = True
            mock_settings.return_value.verification_max_retries = 0
            mock_settings.return_value.verification_retry_delay = 0.01
            mock_settings.return_value.verification_strict_mode = False  # Non-strict

            service = ToolCallingService(
                execute_fn=mock_execute,
                verify_fn=mock_verify,
                log_fn=None,
                validate_fn=None,
            )

            result, status = service.execute_tool_call(
                tool_call_id="test_123",
                function_name="create_simple_note",
                function_args={"title": "Test"},
                model="gpt-4o",
            )

        # Should succeed despite verification failure in non-strict mode
        assert status == "success"
        assert result.get("verification", {}).get("status") == "warning"


class TestVerifyToolResult:
    """Test the verify_tool_result function in chat_routes.py"""

    def test_write_verification_functions_has_11_ops(self):
        """Verify WRITE_VERIFICATION_FUNCTIONS matches expected operations"""
        assert len(WRITE_VERIFICATION_FUNCTIONS) == 11
        assert "create_simple_note" in WRITE_VERIFICATION_FUNCTIONS
        assert "append_to_daily_note" in WRITE_VERIFICATION_FUNCTIONS
        assert "apply_tags_to_note" in WRITE_VERIFICATION_FUNCTIONS
        assert "research_and_save" in WRITE_VERIFICATION_FUNCTIONS
        assert "create_scheduled_task" in WRITE_VERIFICATION_FUNCTIONS

    def test_verify_tool_result_returns_tuple(self):
        """Test that verify_tool_result returns proper tuple format"""
        with patch("routes.chat_routes.settings") as mock_settings:
            mock_settings.verify_vault_writes = False

            result = verify_tool_result(
                "create_simple_note",
                {"title": "Test"},
                {"success": True}
            )

        # Should return 3-tuple
        assert len(result) == 3
        status, error, details = result
        assert status == "skipped"
        assert error is None
        assert "verification_disabled" in str(details)


class TestConfigSettings:
    """Test the configuration settings"""

    def test_config_has_verification_settings(self):
        """Test that config has all verification settings"""
        from config import Settings

        settings = Settings()

        # Check default values
        assert hasattr(settings, "verify_vault_writes")
        assert hasattr(settings, "verification_max_retries")
        assert hasattr(settings, "verification_retry_delay")
        assert hasattr(settings, "verification_strict_mode")

        # Check default values
        assert settings.verify_vault_writes is True
        assert settings.verification_max_retries == 2
        assert settings.verification_retry_delay == 0.5
        assert settings.verification_strict_mode is True

    def test_config_validation(self):
        """Test config validation bounds"""
        from config import Settings
        from pydantic import ValidationError

        # max_retries must be 0-5
        with pytest.raises(ValidationError):
            Settings(verification_max_retries=10)

        # retry_delay must be 0-5
        with pytest.raises(ValidationError):
            Settings(verification_retry_delay=10.0)


class TestFormatVerificationFailure:
    """Test the error message formatting"""

    def test_format_includes_all_details(self):
        """Test that formatted message includes all relevant details"""
        verification = VerificationResult(
            success=False,
            operation="create_simple_note",
            details="File not found after creation",
            checks_passed=["validation_passed"],
            checks_failed=["file_exists", "content_verified"],
            suggestions=["Check vault path", "Verify permissions"]
        )

        formatted = format_verification_failure(
            "Created note at /path/to/note.md",
            verification,
            attempts=3
        )

        assert "3 attempt(s)" in formatted
        assert "file_exists" in formatted
        assert "content_verified" in formatted
        assert "Check vault path" in formatted
        assert "did NOT complete successfully" in formatted


class TestSystemPromptVerificationGuidance:
    """Test that system prompts include verification guidance"""

    def test_anthropic_prompt_has_verification_section(self):
        """Test that Anthropic system prompt includes verification guidance"""
        from services.llm_service import LLMService

        # Read the source file to check the prompt content
        llm_service_path = Path(__file__).parent.parent / "services" / "llm_service.py"
        source_code = llm_service_path.read_text()

        # Check for key verification guidance phrases
        assert "VERIFICATION AND ERROR HANDLING" in source_code
        assert "verification.status" in source_code or "verified=" in source_code
        assert "Never claim success when" in source_code or "Never Ignore Errors" in source_code

    def test_openai_prompt_has_verification_section(self):
        """Test that OpenAI system prompt includes verification guidance"""
        llm_service_path = Path(__file__).parent.parent / "services" / "llm_service.py"
        source_code = llm_service_path.read_text()

        # The verification guidance should appear twice (for both providers)
        count = source_code.count("VERIFICATION AND ERROR HANDLING")
        assert count >= 2, "Verification guidance should be in both Anthropic and OpenAI prompts"


class TestIntegration:
    """Integration tests that test the full verification flow"""

    @pytest.fixture
    def temp_vault(self):
        vault_dir = tempfile.mkdtemp(prefix="test_vault_")
        yield vault_dir
        shutil.rmtree(vault_dir, ignore_errors=True)

    def test_full_verification_flow_success(self, temp_vault):
        """Test complete verification flow for successful operation"""
        # Create the file that would be created by the operation
        test_file = Path(temp_vault) / "test_note.md"
        test_file.write_text("# Test Note\n\nThis is the content.")

        def mock_execute(name, args):
            return {
                "success": True,
                "file_path": str(test_file),
                "message": "Note created successfully"
            }

        with patch("services.tool_calling_service.get_settings") as mock_settings:
            mock_settings.return_value.verify_vault_writes = True
            mock_settings.return_value.verification_max_retries = 2
            mock_settings.return_value.verification_retry_delay = 0.01
            mock_settings.return_value.verification_strict_mode = True

            with patch("routes.chat_routes.settings", mock_settings.return_value):
                service = ToolCallingService(
                    execute_fn=mock_execute,
                    verify_fn=verify_tool_result,
                    log_fn=None,
                    validate_fn=None,
                )

                result, status = service.execute_tool_call(
                    tool_call_id="test_123",
                    function_name="create_simple_note",
                    function_args={"title": "Test Note", "content": "This is the content."},
                    model="gpt-4o",
                )

        assert status == "success"
        assert result.get("verification", {}).get("status") == "passed"

    def test_full_verification_flow_failure(self, temp_vault):
        """Test complete verification flow for failed operation"""
        # Don't create the file - simulate failed write
        nonexistent_file = Path(temp_vault) / "nonexistent.md"

        def mock_execute(name, args):
            return {
                "success": True,  # Operation claims success but file doesn't exist
                "file_path": str(nonexistent_file),
                "message": "Note created"
            }

        with patch("services.tool_calling_service.get_settings") as mock_settings:
            mock_settings.return_value.verify_vault_writes = True
            mock_settings.return_value.verification_max_retries = 0  # No retries for this test
            mock_settings.return_value.verification_retry_delay = 0.01
            mock_settings.return_value.verification_strict_mode = True

            with patch("routes.chat_routes.settings", mock_settings.return_value):
                service = ToolCallingService(
                    execute_fn=mock_execute,
                    verify_fn=verify_tool_result,
                    log_fn=None,
                    validate_fn=None,
                )

                result, status = service.execute_tool_call(
                    tool_call_id="test_123",
                    function_name="create_simple_note",
                    function_args={"title": "Test"},
                    model="gpt-4o",
                )

        assert status == "verification_failed"
        assert result.get("success") is False


if __name__ == "__main__":
    # Run all tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
