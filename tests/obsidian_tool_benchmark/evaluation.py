"""
Evaluation Module for Tool Calling Benchmark

Provides scoring functions for:
- Tool selection accuracy
- Parameter extraction accuracy
- Failure mode classification
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


class FailureMode(Enum):
    """Classification of why a test failed"""

    # Tool Selection Failures
    WRONG_TOOL = "wrong_tool"               # Selected incorrect tool
    NO_TOOL_WHEN_EXPECTED = "no_tool_call"  # Should have called tool, didn't
    TOOL_WHEN_NOT_EXPECTED = "spurious_call" # Called tool when shouldn't have

    # Parameter Failures
    MISSING_REQUIRED_PARAM = "missing_param" # Required param not provided
    WRONG_PARAM_VALUE = "wrong_value"        # Param present but wrong value
    MALFORMED_PARAM = "malformed"            # Param value not parseable

    # Execution Failures
    API_ERROR = "api_error"                  # Ollama API error
    TIMEOUT = "timeout"                      # Response took too long
    JSON_PARSE_ERROR = "json_error"          # Could not parse tool call

    # Model Behavior
    HALLUCINATED_TOOL = "hallucinated"       # Called non-existent tool
    VERBOSE_NO_ACTION = "verbose_no_action"  # Long explanation, no tool call


# Tools that are related and provide partial credit
RELATED_TOOLS = {
    "search_vault": ["find_and_read_note"],
    "find_and_read_note": ["search_vault", "read_note"],
    "read_note": ["find_and_read_note"],
    "list_folder_contents": ["get_vault_structure"],
    "get_vault_structure": ["list_folder_contents"],
    "read_daily_note": ["get_today_tasks"],
}

# Valid tools that can be called
VALID_TOOLS = {
    "list_folder_contents",
    "get_vault_structure",
    "search_vault",
    "read_note",
    "read_daily_note",
    "find_and_read_note",
    "append_to_daily_note",
    "create_simple_note",
    "create_job_note",
    "get_today_tasks",
}


def evaluate_tool_selection(
    expected_tool: Optional[Union[str, List[str]]],
    actual_tool: Optional[str]
) -> Tuple[float, str, str]:
    """
    Evaluate tool selection accuracy.

    Args:
        expected_tool: Expected tool name, list of acceptable tools, or None
        actual_tool: Actually called tool name or None

    Returns:
        (score, status, details) tuple
        - score: 0.0 to 1.0
        - status: "correct", "partial", "incorrect", etc.
        - details: Human-readable explanation
    """
    if expected_tool is None:
        # Should NOT have called a tool (refusal scenario)
        if actual_tool is None:
            return (1.0, "correct_refusal", "Correctly did not call any tool")
        return (0.0, "spurious_call", f"Called {actual_tool} when no tool was expected")

    # Convert single tool to list for uniform handling
    if isinstance(expected_tool, str):
        expected_list = [expected_tool]
    else:
        expected_list = expected_tool

    if actual_tool is None:
        return (0.0, "no_tool_call", f"Expected one of {expected_list}, but no tool was called")

    # Check if actual tool is in valid tools
    if actual_tool not in VALID_TOOLS:
        return (0.0, "hallucinated", f"Called non-existent tool: {actual_tool}")

    # Exact match with any expected tool
    if actual_tool in expected_list:
        return (1.0, "correct", f"Correctly called {actual_tool}")

    # Check for related tools (partial credit)
    for expected in expected_list:
        related = RELATED_TOOLS.get(expected, [])
        if actual_tool in related:
            return (0.5, "partial", f"Called related tool {actual_tool} (expected {expected})")

    return (0.0, "incorrect", f"Expected one of {expected_list}, got {actual_tool}")


def evaluate_parameters(
    expected_params: Dict[str, Any],
    actual_params: Dict[str, Any]
) -> Tuple[float, str, str]:
    """
    Evaluate parameter extraction accuracy.

    Args:
        expected_params: Dict with values that can be:
            - callable validators (return True if valid)
            - exact values for comparison
        actual_params: Dict of actual parameters from tool call

    Returns:
        (score, status, details) tuple
    """
    if not expected_params:
        # No specific parameters expected
        return (1.0, "no_params_expected", "No specific parameters to validate")

    correct = 0
    total = len(expected_params)
    issues = []

    for param_name, expected_value in expected_params.items():
        actual_value = actual_params.get(param_name)

        if callable(expected_value):
            # Validator function
            try:
                if expected_value(actual_value):
                    correct += 1
                else:
                    issues.append(f"{param_name}: validation failed for value '{actual_value}'")
            except Exception as e:
                issues.append(f"{param_name}: validator error - {e}")
        else:
            # Exact match comparison
            if actual_value == expected_value:
                correct += 1
            elif actual_value is not None and str(actual_value).lower() == str(expected_value).lower():
                # Case-insensitive partial credit
                correct += 0.8
                issues.append(f"{param_name}: case mismatch '{actual_value}' vs '{expected_value}'")
            elif actual_value is None:
                issues.append(f"{param_name}: missing (expected '{expected_value}')")
            else:
                issues.append(f"{param_name}: expected '{expected_value}', got '{actual_value}'")

    score = correct / total if total > 0 else 1.0

    if score == 1.0:
        status = "correct"
    elif score >= 0.5:
        status = "partial"
    else:
        status = "incorrect"

    details = "; ".join(issues) if issues else "All parameters correct"
    return (score, status, details)


def classify_failure(
    test: Dict,
    actual_tool: Optional[str],
    actual_params: Dict[str, Any],
    tool_status: str,
    param_status: str
) -> Tuple[FailureMode, str]:
    """
    Classify the failure mode for a failed test.

    Args:
        test: Test definition
        actual_tool: Tool that was called (or None)
        actual_params: Parameters that were passed
        tool_status: Status from tool selection evaluation
        param_status: Status from parameter evaluation

    Returns:
        (FailureMode, details) tuple
    """
    expected_tool = test.get("expected_tool")

    # Tool selection failures
    if tool_status == "spurious_call":
        return (FailureMode.TOOL_WHEN_NOT_EXPECTED,
                f"Called {actual_tool} when no tool should have been called")

    if tool_status == "no_tool_call":
        return (FailureMode.NO_TOOL_WHEN_EXPECTED,
                f"Expected to call {expected_tool}, but no tool was called")

    if tool_status == "hallucinated":
        return (FailureMode.HALLUCINATED_TOOL,
                f"Called non-existent tool: {actual_tool}")

    if tool_status == "incorrect":
        return (FailureMode.WRONG_TOOL,
                f"Called {actual_tool} instead of {expected_tool}")

    # Parameter failures (tool was correct or partial)
    if param_status == "incorrect":
        # Check if required params are missing
        expected_params = test.get("expected_params", {})
        missing = [k for k in expected_params if k not in actual_params]
        if missing:
            return (FailureMode.MISSING_REQUIRED_PARAM,
                    f"Missing required parameters: {missing}")
        else:
            return (FailureMode.WRONG_PARAM_VALUE,
                    f"Parameters have incorrect values")

    if param_status == "partial":
        return (FailureMode.WRONG_PARAM_VALUE,
                "Some parameters have incorrect values")

    # Default - shouldn't reach here for actual failures
    return (FailureMode.WRONG_TOOL, "Unknown failure mode")


def calculate_combined_score(
    tool_score: float,
    param_score: float,
    tool_weight: float = 0.6,
    param_weight: float = 0.4
) -> float:
    """
    Calculate weighted combined score.

    Tool selection is weighted higher (60%) because wrong tool = complete failure,
    while wrong parameters might still be partially useful.

    Args:
        tool_score: Tool selection score (0-1)
        param_score: Parameter extraction score (0-1)
        tool_weight: Weight for tool selection (default 0.6)
        param_weight: Weight for parameter extraction (default 0.4)

    Returns:
        Combined score (0-1)
    """
    return tool_score * tool_weight + param_score * param_weight


def is_test_success(
    tool_score: float,
    param_score: float,
    tool_threshold: float = 0.8,
    param_threshold: float = 0.5
) -> bool:
    """
    Determine if a test passed based on scores.

    A test passes if:
    - Tool selection score >= threshold (default 0.8, allows partial matches)
    - Parameter score >= threshold (default 0.5, allows partial correctness)

    Args:
        tool_score: Tool selection score
        param_score: Parameter extraction score
        tool_threshold: Minimum tool score for success
        param_threshold: Minimum param score for success

    Returns:
        True if test passed
    """
    return tool_score >= tool_threshold and param_score >= param_threshold
