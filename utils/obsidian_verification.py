"""
Obsidian Verification Module

Centralized verification logic for all Obsidian write operations.
Provides operation-specific verification to ensure data integrity.

Categories:
- File Creation: create_simple_note, create_job_note, create_from_template, create_custom_template
- Content Append: append_to_daily_note, research_and_save (append mode)
- Content Update: update_note, update_note_section, replace_note_content
- Metadata: apply_tags_to_note
- Task Operations: create_scheduled_task
- Research: research_and_save (external API - file write only)
"""

import os
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
import structlog

logger = structlog.get_logger()


@dataclass
class VerificationResult:
    """Result of a verification check."""
    success: bool
    operation: str
    details: str
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


# All write operations that require verification
WRITE_OPERATIONS = {
    # File creation
    "create_simple_note",
    "create_job_note",
    "create_from_template",
    "create_custom_template",

    # Content modification
    "update_note",
    "update_note_section",
    "replace_note_content",

    # Append operations
    "append_to_daily_note",

    # Metadata operations
    "apply_tags_to_note",

    # Special operations
    "research_and_save",
    "create_scheduled_task",
}

# Operation categories for verification logic
FILE_CREATION_OPS = {
    "create_simple_note",
    "create_job_note",
    "create_from_template",
    "create_custom_template",
}

CONTENT_APPEND_OPS = {
    "append_to_daily_note",
}

CONTENT_UPDATE_OPS = {
    "update_note",
    "update_note_section",
    "replace_note_content",
}

METADATA_OPS = {
    "apply_tags_to_note",
}

TASK_OPS = {
    "create_scheduled_task",
}

RESEARCH_OPS = {
    "research_and_save",
}


def _normalize_content(text: str, limit: Optional[int] = None) -> str:
    """Normalize content for comparison (strip, collapse whitespace)."""
    if not text:
        return ""
    fragment = text.strip().replace("\r", " ").replace("\n", " ")
    if limit is not None and limit > 0:
        fragment = fragment[:limit]
    return " ".join(fragment.split())


def _get_file_path(result: Dict[str, Any]) -> Optional[str]:
    """Extract file path from result dict, checking multiple possible keys."""
    return (
        result.get("file_path") or
        result.get("absolute_path") or
        result.get("path") or
        result.get("full_path")
    )


def _file_recently_modified(file_path: str, window_seconds: float = 5.0) -> bool:
    """Check if file was modified within the given time window."""
    try:
        mtime = os.path.getmtime(file_path)
        return (time.time() - mtime) <= window_seconds
    except OSError:
        return False


def verify_operation(
    function_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any]
) -> VerificationResult:
    """
    Main verification dispatcher.

    Args:
        function_name: Name of the operation executed
        arguments: Arguments passed to the operation
        result: Result dict returned by the operation

    Returns:
        VerificationResult with success status and details
    """
    # Skip verification if operation not in write operations
    if function_name not in WRITE_OPERATIONS:
        return VerificationResult(
            success=True,
            operation=function_name,
            details="Operation does not require verification",
            checks_passed=["not_write_operation"]
        )

    # Skip if operation itself reported failure
    if not result.get("success", False):
        return VerificationResult(
            success=True,  # Verification skipped, not failed
            operation=function_name,
            details="Operation reported failure, verification skipped",
            checks_passed=["operation_failure_skipped"]
        )

    # Dispatch to appropriate verifier
    try:
        if function_name in FILE_CREATION_OPS:
            return _verify_file_creation(function_name, arguments, result)
        elif function_name in CONTENT_APPEND_OPS:
            return _verify_content_append(function_name, arguments, result)
        elif function_name in CONTENT_UPDATE_OPS:
            return _verify_content_update(function_name, arguments, result)
        elif function_name in METADATA_OPS:
            return _verify_metadata_operation(function_name, arguments, result)
        elif function_name in TASK_OPS:
            return _verify_task_operation(function_name, arguments, result)
        elif function_name in RESEARCH_OPS:
            return _verify_research_operation(function_name, arguments, result)
        else:
            # Unknown operation type - perform basic verification
            return _verify_basic(function_name, arguments, result)
    except Exception as e:
        logger.error(
            "verification_error",
            function=function_name,
            error=str(e),
            exc_info=True
        )
        return VerificationResult(
            success=False,
            operation=function_name,
            details=f"Verification error: {str(e)}",
            checks_failed=["verification_exception"],
            suggestions=["Check file system permissions", "Verify vault path is accessible"]
        )


def _verify_file_creation(
    function_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any]
) -> VerificationResult:
    """
    Verify file creation operations.

    Checks:
    1. File exists at specified path
    2. File is non-empty (size > 0 bytes)
    3. Content sample check (for create_simple_note)
    4. For templates: Verify in Templates folder with .md extension
    """
    checks_passed = []
    checks_failed = []
    suggestions = []

    file_path = _get_file_path(result)

    # Check 1: File exists
    if not file_path:
        checks_failed.append("No file path returned in result")
        suggestions.append("Check that the operation returned a valid file path")
        return VerificationResult(
            success=False,
            operation=function_name,
            details="No file path in operation result",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=suggestions
        )

    if not os.path.isfile(file_path):
        checks_failed.append(f"File does not exist: {file_path}")
        suggestions.append("Check vault path configuration")
        suggestions.append("Verify parent directory exists and is writable")
        return VerificationResult(
            success=False,
            operation=function_name,
            details=f"File not found after creation: {file_path}",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=suggestions
        )

    checks_passed.append("file_exists")

    # Check 2: File is non-empty
    try:
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            checks_failed.append("File is empty (0 bytes)")
            suggestions.append("Verify content was provided to the operation")
            return VerificationResult(
                success=False,
                operation=function_name,
                details="File created but is empty",
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                suggestions=suggestions
            )
        checks_passed.append(f"file_non_empty ({file_size} bytes)")
    except OSError as e:
        checks_failed.append(f"Could not check file size: {e}")

    # Check 3: Content verification for create_simple_note
    if function_name == "create_simple_note":
        requested_content = arguments.get("content", "").strip()
        if requested_content:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    actual_content = f.read()

                # Normalize and compare content snippet
                requested_norm = _normalize_content(requested_content, limit=200)
                actual_norm = _normalize_content(actual_content, limit=500)

                if requested_norm and requested_norm not in actual_norm:
                    checks_failed.append("Content mismatch - requested content not found in file")
                    suggestions.append("Verify content encoding")
                    suggestions.append("Check for content transformation during save")
                    return VerificationResult(
                        success=False,
                        operation=function_name,
                        details=f"Content mismatch in {file_path}",
                        checks_passed=checks_passed,
                        checks_failed=checks_failed,
                        suggestions=suggestions
                    )
                checks_passed.append("content_verified")
            except Exception as e:
                checks_failed.append(f"Content verification error: {e}")

    # Check 4: Template-specific verification
    if function_name == "create_custom_template":
        if not file_path.endswith(".md"):
            checks_failed.append("Template file should have .md extension")
        else:
            checks_passed.append("template_extension_correct")

        # Check if in Templates folder (case-insensitive)
        path_lower = file_path.lower()
        if "template" not in path_lower:
            suggestions.append("Consider placing template in a Templates folder")

    # Check: Recently modified
    if _file_recently_modified(file_path, window_seconds=10.0):
        checks_passed.append("recently_modified")

    return VerificationResult(
        success=len(checks_failed) == 0,
        operation=function_name,
        details=f"File creation verified: {file_path}" if not checks_failed else f"Verification failed: {', '.join(checks_failed)}",
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        suggestions=suggestions
    )


def _verify_content_append(
    function_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any]
) -> VerificationResult:
    """
    Verify content append operations.

    Checks:
    1. File exists
    2. File contains the appended content
    3. Content is in correct section (for append_to_daily_note)
    4. File modification timestamp is recent
    """
    checks_passed = []
    checks_failed = []
    suggestions = []

    file_path = _get_file_path(result)

    # Check 1: File exists
    if not file_path:
        checks_failed.append("No file path returned in result")
        suggestions.append("Check daily note configuration")
        return VerificationResult(
            success=False,
            operation=function_name,
            details="No file path in operation result",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=suggestions
        )

    if not os.path.isfile(file_path):
        checks_failed.append(f"File does not exist: {file_path}")
        suggestions.append("Verify daily note folder exists")
        suggestions.append("Check date format configuration")
        return VerificationResult(
            success=False,
            operation=function_name,
            details=f"Target file not found: {file_path}",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=suggestions
        )

    checks_passed.append("file_exists")

    # Check 2: Appended content is present
    appended_content = arguments.get("content", "").strip()
    if appended_content:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                actual_content = f.read()

            appended_norm = _normalize_content(appended_content, limit=200)

            if appended_norm and appended_norm not in actual_content:
                checks_failed.append("Appended content not found in file")
                suggestions.append("Check if file was modified by another process")
                suggestions.append("Verify section header exists in daily note template")
                return VerificationResult(
                    success=False,
                    operation=function_name,
                    details=f"Appended content not found in {file_path}",
                    checks_passed=checks_passed,
                    checks_failed=checks_failed,
                    suggestions=suggestions
                )
            checks_passed.append("content_appended")

            # Check 3: Section verification for daily notes
            if function_name == "append_to_daily_note":
                section = arguments.get("section", "Quick Captures")
                if section:
                    # Look for section header
                    section_headers = [f"## {section}", f"# {section}", f"### {section}"]
                    section_found = any(header in actual_content for header in section_headers)

                    if section_found:
                        checks_passed.append(f"section_exists ({section})")
                    else:
                        suggestions.append(f"Section '{section}' header not found - content may be appended at end")

        except Exception as e:
            checks_failed.append(f"Content verification error: {e}")

    # Check 4: Recently modified
    if _file_recently_modified(file_path, window_seconds=10.0):
        checks_passed.append("recently_modified")
    else:
        suggestions.append("File modification time is not recent - verify write succeeded")

    return VerificationResult(
        success=len(checks_failed) == 0,
        operation=function_name,
        details=f"Content append verified: {file_path}" if not checks_failed else f"Verification failed: {', '.join(checks_failed)}",
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        suggestions=suggestions
    )


def _verify_content_update(
    function_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any]
) -> VerificationResult:
    """
    Verify content update operations.

    Checks:
    1. File exists
    2. New content is present (for update operations)
    3. Old content is gone (for replace operations)
    4. Section header exists (for section updates)
    """
    checks_passed = []
    checks_failed = []
    suggestions = []

    file_path = _get_file_path(result)

    # Check 1: File exists
    if not file_path:
        checks_failed.append("No file path returned in result")
        return VerificationResult(
            success=False,
            operation=function_name,
            details="No file path in operation result",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=["Verify note path is correct"]
        )

    if not os.path.isfile(file_path):
        checks_failed.append(f"File does not exist: {file_path}")
        return VerificationResult(
            success=False,
            operation=function_name,
            details=f"Target file not found: {file_path}",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=["Note may have been moved or deleted"]
        )

    checks_passed.append("file_exists")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            actual_content = f.read()

        # Check 2: New content is present
        if function_name == "replace_note_content":
            new_text = arguments.get("new_text", "").strip()
            if new_text:
                new_norm = _normalize_content(new_text, limit=100)
                if new_norm and new_norm not in actual_content:
                    checks_failed.append("Replacement text not found in file")
                    suggestions.append("Check if text replacement pattern matched")
                else:
                    checks_passed.append("new_content_present")

            # Check 3: Old content is gone
            old_text = arguments.get("old_text", "").strip()
            if old_text:
                old_norm = _normalize_content(old_text, limit=100)
                if old_norm and old_norm in actual_content:
                    # Old text still present - might be multiple occurrences
                    suggestions.append("Original text may have multiple occurrences")
                else:
                    checks_passed.append("old_content_replaced")

        elif function_name == "update_note_section":
            section = arguments.get("section", "").strip()
            new_content = arguments.get("content", "").strip()

            # Check section exists
            if section:
                section_headers = [f"## {section}", f"# {section}", f"### {section}"]
                if any(header in actual_content for header in section_headers):
                    checks_passed.append(f"section_exists ({section})")
                else:
                    checks_failed.append(f"Section '{section}' not found")
                    suggestions.append("Verify section name matches exactly")

            # Check new content is present
            if new_content:
                content_norm = _normalize_content(new_content, limit=100)
                if content_norm and content_norm in actual_content:
                    checks_passed.append("new_content_present")
                else:
                    checks_failed.append("Updated content not found")

        elif function_name == "update_note":
            # Generic update - just check file was modified recently
            if _file_recently_modified(file_path, window_seconds=10.0):
                checks_passed.append("recently_modified")
            else:
                suggestions.append("File may not have been modified")

    except Exception as e:
        checks_failed.append(f"Content verification error: {e}")

    return VerificationResult(
        success=len(checks_failed) == 0,
        operation=function_name,
        details=f"Content update verified: {file_path}" if not checks_failed else f"Verification failed: {', '.join(checks_failed)}",
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        suggestions=suggestions
    )


def _verify_metadata_operation(
    function_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any]
) -> VerificationResult:
    """
    Verify metadata operations (tags).

    Checks:
    1. File exists
    2. Frontmatter present (starts with ---)
    3. Tags line exists in frontmatter
    4. All specified tags present
    """
    checks_passed = []
    checks_failed = []
    suggestions = []

    file_path = _get_file_path(result)

    # Check 1: File exists
    if not file_path or not os.path.isfile(file_path):
        checks_failed.append("File does not exist")
        return VerificationResult(
            success=False,
            operation=function_name,
            details="Target file not found",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=["Verify note exists before applying tags"]
        )

    checks_passed.append("file_exists")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check 2: Frontmatter present
        if not content.startswith("---"):
            checks_failed.append("No frontmatter found (file should start with ---)")
            suggestions.append("Tags require YAML frontmatter at the start of the file")
            return VerificationResult(
                success=False,
                operation=function_name,
                details="No frontmatter in file",
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                suggestions=suggestions
            )

        checks_passed.append("frontmatter_present")

        # Find frontmatter end
        frontmatter_end = content.find("---", 3)
        if frontmatter_end == -1:
            checks_failed.append("Malformed frontmatter (no closing ---)")
            return VerificationResult(
                success=False,
                operation=function_name,
                details="Malformed frontmatter",
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                suggestions=["Check frontmatter YAML syntax"]
            )

        frontmatter = content[3:frontmatter_end]

        # Check 3: Tags line exists
        if "tags:" not in frontmatter.lower():
            checks_failed.append("No tags field in frontmatter")
            suggestions.append("The tags field may not have been added")
        else:
            checks_passed.append("tags_field_exists")

        # Check 4: Specified tags are present
        requested_tags = arguments.get("tags", [])
        if isinstance(requested_tags, str):
            requested_tags = [requested_tags]

        missing_tags = []
        for tag in requested_tags:
            tag_clean = tag.strip().lstrip("#")
            if tag_clean and tag_clean.lower() not in frontmatter.lower():
                missing_tags.append(tag)

        if missing_tags:
            checks_failed.append(f"Tags not found: {', '.join(missing_tags)}")
            suggestions.append("Some tags may not have been added to frontmatter")
        else:
            checks_passed.append(f"all_tags_present ({len(requested_tags)} tags)")

    except Exception as e:
        checks_failed.append(f"Verification error: {e}")

    return VerificationResult(
        success=len(checks_failed) == 0,
        operation=function_name,
        details=f"Tags verified: {file_path}" if not checks_failed else f"Verification failed: {', '.join(checks_failed)}",
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        suggestions=suggestions
    )


def _verify_task_operation(
    function_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any]
) -> VerificationResult:
    """
    Verify scheduled task operations.

    Checks:
    1. .scheduled_tasks.json file exists in vault root
    2. JSON is valid and parseable
    3. Task ID exists in tasks array
    4. Task has required fields
    """
    checks_passed = []
    checks_failed = []
    suggestions = []

    # Get vault path from result or config
    from config import get_settings
    settings = get_settings()
    vault_path = Path(settings.vault_path)

    tasks_file = vault_path / ".scheduled_tasks.json"

    # Check 1: Tasks file exists
    if not tasks_file.exists():
        checks_failed.append("Scheduled tasks file does not exist")
        suggestions.append("The .scheduled_tasks.json file should be created in vault root")
        return VerificationResult(
            success=False,
            operation=function_name,
            details="Tasks file not found",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=suggestions
        )

    checks_passed.append("tasks_file_exists")

    try:
        # Check 2: Valid JSON
        with open(tasks_file, "r", encoding="utf-8") as f:
            tasks_data = json.load(f)

        checks_passed.append("valid_json")

        # Check 3: Task ID exists (if returned in result)
        task_id = result.get("task_id") or arguments.get("task_id")
        tasks_list = tasks_data.get("tasks", [])

        if task_id:
            task_found = any(t.get("id") == task_id for t in tasks_list)
            if task_found:
                checks_passed.append(f"task_exists (id: {task_id})")
            else:
                checks_failed.append(f"Task ID {task_id} not found in tasks list")

        # Check 4: Has required fields
        if tasks_list:
            latest_task = tasks_list[-1] if tasks_list else None
            if latest_task:
                required_fields = ["name", "schedule"]
                missing_fields = [f for f in required_fields if f not in latest_task]
                if missing_fields:
                    checks_failed.append(f"Task missing fields: {', '.join(missing_fields)}")
                else:
                    checks_passed.append("task_has_required_fields")

    except json.JSONDecodeError as e:
        checks_failed.append(f"Invalid JSON: {e}")
        suggestions.append("Check .scheduled_tasks.json file syntax")
    except Exception as e:
        checks_failed.append(f"Verification error: {e}")

    return VerificationResult(
        success=len(checks_failed) == 0,
        operation=function_name,
        details="Task operation verified" if not checks_failed else f"Verification failed: {', '.join(checks_failed)}",
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        suggestions=suggestions
    )


def _verify_research_operation(
    function_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any]
) -> VerificationResult:
    """
    Verify research_and_save operation.

    Checks (file write only - skip API content validation per requirements):
    1. File exists at returned path
    2. File is non-empty
    3. Verify write action (created_new_file vs appended_to_existing)
    """
    checks_passed = []
    checks_failed = []
    suggestions = []

    file_path = _get_file_path(result)

    # Check 1: File exists
    if not file_path:
        checks_failed.append("No file path returned")
        return VerificationResult(
            success=False,
            operation=function_name,
            details="Research operation did not return a file path",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=["Check research parameters"]
        )

    if not os.path.isfile(file_path):
        checks_failed.append(f"Research output file not found: {file_path}")
        return VerificationResult(
            success=False,
            operation=function_name,
            details="Research output file not created",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            suggestions=["Verify research completed successfully"]
        )

    checks_passed.append("file_exists")

    # Check 2: File is non-empty
    try:
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            checks_failed.append("Research output file is empty")
            suggestions.append("Research may have returned no results")
        else:
            checks_passed.append(f"file_non_empty ({file_size} bytes)")
    except OSError as e:
        checks_failed.append(f"Could not check file: {e}")

    # Check 3: Verify action type matches reality
    action = result.get("action", "")
    if action == "created_new_file":
        if _file_recently_modified(file_path, window_seconds=30.0):
            checks_passed.append("new_file_recently_created")
    elif action == "appended_to_existing":
        checks_passed.append("content_appended")

    return VerificationResult(
        success=len(checks_failed) == 0,
        operation=function_name,
        details=f"Research operation verified: {file_path}" if not checks_failed else f"Verification failed: {', '.join(checks_failed)}",
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        suggestions=suggestions
    )


def _verify_basic(
    function_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any]
) -> VerificationResult:
    """
    Basic verification for unrecognized write operations.
    Just checks if file exists and was recently modified.
    """
    checks_passed = []
    checks_failed = []

    file_path = _get_file_path(result)

    if file_path and os.path.isfile(file_path):
        checks_passed.append("file_exists")
        if _file_recently_modified(file_path, window_seconds=10.0):
            checks_passed.append("recently_modified")
    elif file_path:
        checks_failed.append(f"File not found: {file_path}")

    return VerificationResult(
        success=len(checks_failed) == 0,
        operation=function_name,
        details=f"Basic verification: {file_path or 'no path'}",
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        suggestions=[]
    )


def format_verification_failure(
    original_message: str,
    verification: VerificationResult,
    attempts: int
) -> str:
    """
    Format a clear error message when verification fails after retries.

    Args:
        original_message: Original operation result message
        verification: VerificationResult object
        attempts: Number of attempts made

    Returns:
        Formatted error message for LLM consumption
    """
    failed_checks = "\n".join(f"  - {check}" for check in verification.checks_failed)
    suggestions_text = "\n".join(f"  - {s}" for s in verification.suggestions)

    return (
        f"Operation failed verification after {attempts} attempt(s)\n\n"
        f"**Original Operation:** {original_message}\n\n"
        f"**Verification Failed:**\n{verification.details}\n\n"
        f"**Failed Checks:**\n{failed_checks}\n\n"
        f"**Suggestions:**\n{suggestions_text}\n\n"
        f"**Important:** This operation did NOT complete successfully. "
        f"Please try again or check the vault manually."
    )
