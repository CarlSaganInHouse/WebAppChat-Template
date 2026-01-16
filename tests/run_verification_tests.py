#!/usr/bin/env python3
"""
Simple Test Runner for Verification System

Runs tests without pytest dependency.
Run with: python3 tests/run_verification_tests.py
"""

import os
import sys
import json
import tempfile
import shutil
import traceback
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Test results tracking
PASSED = 0
FAILED = 0
ERRORS = []


def test(name):
    """Decorator to mark and run tests"""
    def decorator(func):
        global PASSED, FAILED, ERRORS
        try:
            func()
            print(f"  \033[92m✓\033[0m {name}")
            PASSED += 1
        except AssertionError as e:
            print(f"  \033[91m✗\033[0m {name}")
            print(f"    AssertionError: {e}")
            FAILED += 1
            ERRORS.append((name, str(e)))
        except Exception as e:
            print(f"  \033[91m✗\033[0m {name}")
            print(f"    Exception: {type(e).__name__}: {e}")
            FAILED += 1
            ERRORS.append((name, f"{type(e).__name__}: {e}"))
        return func
    return decorator


def create_temp_vault():
    """Create a temporary vault directory"""
    return tempfile.mkdtemp(prefix="test_vault_")


def cleanup_temp_vault(vault_dir):
    """Clean up temporary vault"""
    shutil.rmtree(vault_dir, ignore_errors=True)


# ============================================================
# Phase 1 Tests: Verification Module
# ============================================================

print("\n\033[1m=== Phase 1: Verification Module Tests ===\033[0m\n")

@test("WRITE_OPERATIONS has 11 operations")
def test_write_operations_count():
    from utils.obsidian_verification import WRITE_OPERATIONS
    assert len(WRITE_OPERATIONS) == 11, f"Expected 11, got {len(WRITE_OPERATIONS)}"


@test("All expected operations are in WRITE_OPERATIONS")
def test_all_operations_present():
    from utils.obsidian_verification import WRITE_OPERATIONS
    expected = {
        "create_simple_note", "create_job_note", "create_from_template",
        "create_custom_template", "update_note", "update_note_section",
        "replace_note_content", "append_to_daily_note", "apply_tags_to_note",
        "research_and_save", "create_scheduled_task"
    }
    assert WRITE_OPERATIONS == expected, f"Missing: {expected - WRITE_OPERATIONS}"


@test("VerificationResult dataclass works")
def test_verification_result():
    from utils.obsidian_verification import VerificationResult
    result = VerificationResult(
        success=True,
        operation="test",
        details="Test details",
        checks_passed=["a", "b"],
        checks_failed=[],
        suggestions=[]
    )
    assert result.success is True
    assert result.operation == "test"
    assert len(result.checks_passed) == 2


@test("Non-write operation skips verification")
def test_non_write_skip():
    from utils.obsidian_verification import verify_operation
    result = verify_operation(
        "search_vault",
        {"query": "test"},
        {"success": True}
    )
    assert result.success is True
    assert "not_write_operation" in result.checks_passed


@test("Failed operation skips verification")
def test_failed_op_skip():
    from utils.obsidian_verification import verify_operation
    result = verify_operation(
        "create_simple_note",
        {"title": "Test"},
        {"success": False}
    )
    assert result.success is True
    assert "operation_failure_skipped" in result.checks_passed


# File existence tests
print("\n\033[1m--- File Verification Tests ---\033[0m\n")


@test("File exists verification passes")
def test_file_exists_pass():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        test_file = Path(vault) / "test.md"
        test_file.write_text("# Test\n\nContent here")
        result = verify_operation(
            "create_simple_note",
            {"title": "Test", "content": "Content here"},
            {"success": True, "file_path": str(test_file)}
        )
        assert result.success is True, f"Expected success, got: {result.checks_failed}"
        assert "file_exists" in result.checks_passed
    finally:
        cleanup_temp_vault(vault)


@test("Missing file fails verification")
def test_file_missing_fail():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        fake_file = Path(vault) / "nonexistent.md"
        result = verify_operation(
            "create_simple_note",
            {"title": "Test"},
            {"success": True, "file_path": str(fake_file)}
        )
        assert result.success is False, "Should fail when file missing"
    finally:
        cleanup_temp_vault(vault)


@test("Empty file fails verification")
def test_empty_file_fail():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        test_file = Path(vault) / "empty.md"
        test_file.write_text("")  # Empty
        result = verify_operation(
            "create_simple_note",
            {"title": "Test", "content": "Expected content"},
            {"success": True, "file_path": str(test_file)}
        )
        assert result.success is False, "Should fail for empty file"
    finally:
        cleanup_temp_vault(vault)


@test("Content mismatch fails verification")
def test_content_mismatch():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        test_file = Path(vault) / "wrong.md"
        test_file.write_text("# Wrong\n\nDifferent content")
        result = verify_operation(
            "create_simple_note",
            {"title": "Test", "content": "Expected content not present anywhere"},
            {"success": True, "file_path": str(test_file)}
        )
        assert result.success is False, "Should fail on content mismatch"
    finally:
        cleanup_temp_vault(vault)


@test("Content match passes verification")
def test_content_match():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        content = "This is the expected content."
        test_file = Path(vault) / "correct.md"
        test_file.write_text(f"# Test\n\n{content}")
        result = verify_operation(
            "create_simple_note",
            {"title": "Test", "content": content},
            {"success": True, "file_path": str(test_file)}
        )
        assert result.success is True, f"Should pass: {result.checks_failed}"
        assert "content_verified" in result.checks_passed
    finally:
        cleanup_temp_vault(vault)


# Append tests
print("\n\033[1m--- Append Operation Tests ---\033[0m\n")


@test("Appended content found passes")
def test_append_found():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        appended = "This was appended."
        test_file = Path(vault) / "daily.md"
        test_file.write_text(f"# Daily\n\n## Quick Captures\n\n{appended}")
        result = verify_operation(
            "append_to_daily_note",
            {"content": appended, "section": "Quick Captures"},
            {"success": True, "file_path": str(test_file)}
        )
        assert result.success is True, f"Should pass: {result.checks_failed}"
        assert "content_appended" in result.checks_passed
    finally:
        cleanup_temp_vault(vault)


@test("Missing appended content fails")
def test_append_missing():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        test_file = Path(vault) / "daily.md"
        test_file.write_text("# Daily\n\nSome other content")
        result = verify_operation(
            "append_to_daily_note",
            {"content": "This content is not in the file"},
            {"success": True, "file_path": str(test_file)}
        )
        assert result.success is False, "Should fail when content missing"
    finally:
        cleanup_temp_vault(vault)


# Metadata tests
print("\n\033[1m--- Metadata Operation Tests ---\033[0m\n")


@test("Tags in frontmatter passes")
def test_tags_found():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        test_file = Path(vault) / "tagged.md"
        test_file.write_text("""---
tags: [project, important]
---

# Note""")
        result = verify_operation(
            "apply_tags_to_note",
            {"tags": ["project", "important"]},
            {"success": True, "file_path": str(test_file)}
        )
        assert result.success is True, f"Should pass: {result.checks_failed}"
    finally:
        cleanup_temp_vault(vault)


@test("Missing frontmatter fails")
def test_no_frontmatter():
    from utils.obsidian_verification import verify_operation
    vault = create_temp_vault()
    try:
        test_file = Path(vault) / "no_fm.md"
        test_file.write_text("# Note\n\nNo frontmatter here")
        result = verify_operation(
            "apply_tags_to_note",
            {"tags": ["test"]},
            {"success": True, "file_path": str(test_file)}
        )
        assert result.success is False, "Should fail without frontmatter"
    finally:
        cleanup_temp_vault(vault)


# ============================================================
# Phase 2 Tests: Retry Logic
# ============================================================

print("\n\033[1m=== Phase 2: Retry Logic Tests ===\033[0m\n")


@test("Retry on verification failure")
def test_retry_on_failure():
    from services.tool_calling_service import ToolCallingService

    call_count = {"execute": 0, "verify": 0}

    def mock_execute(name, args):
        call_count["execute"] += 1
        return {"success": True, "file_path": "/fake/path.md"}

    def mock_verify(name, args, result):
        call_count["verify"] += 1
        if call_count["verify"] <= 2:
            return ("failed", "Failed", {"checks_failed": ["test"]})
        return ("passed", None, {"checks_passed": ["test"]})

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
            tool_call_id="test",
            function_name="create_simple_note",
            function_args={"title": "Test"},
            model="gpt-4o",
        )

    assert call_count["execute"] == 3, f"Should retry 3 times, got {call_count['execute']}"
    assert status == "success"


@test("Max retries respected")
def test_max_retries():
    from services.tool_calling_service import ToolCallingService

    verify_count = 0

    def mock_execute(name, args):
        return {"success": True, "file_path": "/fake/path.md"}

    def mock_verify(name, args, result):
        nonlocal verify_count
        verify_count += 1
        return ("failed", "Always fails", {"checks_failed": ["always"]})

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
            tool_call_id="test",
            function_name="create_simple_note",
            function_args={"title": "Test"},
            model="gpt-4o",
        )

    assert verify_count == 3, f"Should verify 3 times (1 + 2 retries), got {verify_count}"
    assert status == "verification_failed"


@test("Non-strict mode continues on failure")
def test_non_strict_mode():
    from services.tool_calling_service import ToolCallingService

    def mock_execute(name, args):
        return {"success": True, "file_path": "/fake/path.md"}

    def mock_verify(name, args, result):
        return ("failed", "Failed", {"checks_failed": ["test"]})

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
            tool_call_id="test",
            function_name="create_simple_note",
            function_args={"title": "Test"},
            model="gpt-4o",
        )

    assert status == "success", "Should succeed in non-strict mode"
    assert result.get("verification", {}).get("status") == "warning"


# ============================================================
# Phase 3 Tests: Config and Prompts
# ============================================================

print("\n\033[1m=== Phase 3: Config and Prompt Tests ===\033[0m\n")


@test("Config has verification settings")
def test_config_settings():
    from config import Settings
    settings = Settings()
    assert hasattr(settings, "verify_vault_writes")
    assert hasattr(settings, "verification_max_retries")
    assert hasattr(settings, "verification_retry_delay")
    assert hasattr(settings, "verification_strict_mode")


@test("Config defaults are correct")
def test_config_defaults():
    from config import Settings
    settings = Settings()
    assert settings.verify_vault_writes is True
    assert settings.verification_max_retries == 2
    assert settings.verification_retry_delay == 0.5
    assert settings.verification_strict_mode is True


@test("LLM service has verification guidance in prompts")
def test_prompt_has_verification():
    llm_path = PROJECT_ROOT / "services" / "llm_service.py"
    source = llm_path.read_text()

    # Check for key phrases that should be in the prompt
    assert "VERIFICATION AND ERROR HANDLING" in source, "Missing verification section"
    assert "Never claim success when" in source or "verification.status" in source
    count = source.count("VERIFICATION AND ERROR HANDLING")
    assert count >= 2, f"Should appear in both providers, found {count} times"


@test("WRITE_VERIFICATION_FUNCTIONS in chat_routes has 11 ops")
def test_chat_routes_write_ops():
    from routes.chat_routes import WRITE_VERIFICATION_FUNCTIONS
    assert len(WRITE_VERIFICATION_FUNCTIONS) == 11


@test("WRITE_VERIFICATION_FUNCTIONS in tool_calling_service has 11 ops")
def test_tool_service_write_ops():
    from services.tool_calling_service import ToolCallingService
    assert len(ToolCallingService.WRITE_VERIFICATION_FUNCTIONS) == 11


# ============================================================
# Integration Tests
# ============================================================

print("\n\033[1m=== Integration Tests ===\033[0m\n")


@test("Full flow: successful verification")
def test_full_flow_success():
    from services.tool_calling_service import ToolCallingService
    from routes.chat_routes import verify_tool_result

    vault = create_temp_vault()
    try:
        test_file = Path(vault) / "test.md"
        test_file.write_text("# Test\n\nThis is the content.")

        def mock_execute(name, args):
            return {
                "success": True,
                "file_path": str(test_file),
                "message": "Created"
            }

        with patch("services.tool_calling_service.get_settings") as mock_settings, \
             patch("routes.chat_routes.settings", mock_settings.return_value):
            mock_settings.return_value.verify_vault_writes = True
            mock_settings.return_value.verification_max_retries = 2
            mock_settings.return_value.verification_retry_delay = 0.01
            mock_settings.return_value.verification_strict_mode = True

            service = ToolCallingService(
                execute_fn=mock_execute,
                verify_fn=verify_tool_result,
                log_fn=None,
                validate_fn=None,
            )

            result, status = service.execute_tool_call(
                tool_call_id="test",
                function_name="create_simple_note",
                function_args={"title": "Test", "content": "This is the content."},
                model="gpt-4o",
            )

        assert status == "success", f"Should succeed, got {status}"
        assert result.get("verification", {}).get("status") == "passed"
    finally:
        cleanup_temp_vault(vault)


@test("Full flow: failed verification")
def test_full_flow_failure():
    from services.tool_calling_service import ToolCallingService
    from routes.chat_routes import verify_tool_result

    vault = create_temp_vault()
    try:
        fake_file = Path(vault) / "nonexistent.md"

        def mock_execute(name, args):
            return {
                "success": True,
                "file_path": str(fake_file),
                "message": "Created"
            }

        with patch("services.tool_calling_service.get_settings") as mock_settings, \
             patch("routes.chat_routes.settings", mock_settings.return_value):
            mock_settings.return_value.verify_vault_writes = True
            mock_settings.return_value.verification_max_retries = 0
            mock_settings.return_value.verification_retry_delay = 0.01
            mock_settings.return_value.verification_strict_mode = True

            service = ToolCallingService(
                execute_fn=mock_execute,
                verify_fn=verify_tool_result,
                log_fn=None,
                validate_fn=None,
            )

            result, status = service.execute_tool_call(
                tool_call_id="test",
                function_name="create_simple_note",
                function_args={"title": "Test"},
                model="gpt-4o",
            )

        assert status == "verification_failed", f"Should fail, got {status}"
        assert result.get("success") is False
    finally:
        cleanup_temp_vault(vault)


# ============================================================
# Summary
# ============================================================

print("\n" + "=" * 60)
print(f"\033[1mTest Results: {PASSED} passed, {FAILED} failed\033[0m")
print("=" * 60)

if ERRORS:
    print("\n\033[91mFailures:\033[0m")
    for name, error in ERRORS:
        print(f"  - {name}: {error}")

if FAILED == 0:
    print("\n\033[92m✓ All tests passed!\033[0m\n")
    sys.exit(0)
else:
    print(f"\n\033[91m✗ {FAILED} test(s) failed\033[0m\n")
    sys.exit(1)
