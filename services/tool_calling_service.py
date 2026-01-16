"""
Tool Calling Service

This service handles LLM tool/function calling operations, including:
- Tool execution via Obsidian functions
- Read-after-write verification for vault operations
- Observability logging for tool calls
- Error handling and validation
- Context memory updates after successful tool calls

Designed for LLM consumption and testability.
"""

import time
import json
from typing import Dict, Any, Tuple, Optional, Callable


class ToolCallingService:
    """
    Manages tool/function calling execution, verification, and logging.
    """

    # Write operations that require verification (all 11 operations)
    WRITE_VERIFICATION_FUNCTIONS = {
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

    def __init__(
        self,
        execute_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        verify_fn: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], Tuple[str, Optional[str]]]] = None,
        log_fn: Optional[Callable] = None,
        validate_fn: Optional[Callable[[str, Dict[str, Any]], Tuple[bool, Optional[str]]]] = None,
        update_context_fn: Optional[Callable] = None
    ):
        """
        Initialize the tool calling service.

        Args:
            execute_fn: Function to execute Obsidian tools (function_name, args) -> result
            verify_fn: Optional function to verify tool results (name, args, result) -> (status, error)
            log_fn: Optional function to log tool calls
            validate_fn: Optional function to validate tool schemas (name, args) -> (is_valid, error)
            update_context_fn: Optional function to update conversation context
        """
        self.execute_fn = execute_fn
        self.verify_fn = verify_fn
        self.log_fn = log_fn
        self.validate_fn = validate_fn
        self.update_context_fn = update_context_fn

    def execute_tool_call(
        self,
        tool_call_id: str,
        function_name: str,
        function_args: Dict[str, Any],
        model: str,
        chat_id: Optional[str] = None,
        chat_loader_fn: Optional[Callable] = None,
        chat_saver_fn: Optional[Callable] = None
    ) -> Tuple[Dict[str, Any], str]:
        """
        Execute a single tool call with validation, execution, verification, and logging.

        Includes retry logic for verification failures on write operations.
        Retry behavior is controlled by config settings:
        - verification_max_retries: Maximum number of retry attempts (default: 2)
        - verification_retry_delay: Delay between retries in seconds (default: 0.5)
        - verification_strict_mode: Whether to fail on verification failure (default: True)

        Returns:
            Tuple of (result_dict, status)
            - result_dict: Tool execution result or error dict
            - status: "success" | "validation_error" | "execution_error" | "verification_failed"
        """
        from config import get_settings
        import structlog

        logger = structlog.get_logger()
        settings = get_settings()
        call_start_time = time.time()

        # Get retry settings
        max_retries = settings.verification_max_retries if settings.verify_vault_writes else 0
        retry_delay = settings.verification_retry_delay
        strict_mode = settings.verification_strict_mode

        # Step 1: Validate schema (if validator provided) - no retry for validation errors
        if self.validate_fn:
            is_valid, validation_error = self.validate_fn(function_name, function_args)
            if not is_valid:
                if self.log_fn:
                    self.log_fn(
                        call_id=tool_call_id,
                        model=model,
                        function=function_name,
                        status="validation_error",
                        args=function_args,
                        error=validation_error,
                        duration_ms=round((time.time() - call_start_time) * 1000, 2)
                    )
                return {"error": validation_error}, "validation_error"

        # Determine if this is a write operation that might need retries
        is_write_op = function_name in self.WRITE_VERIFICATION_FUNCTIONS

        # Retry loop for execution and verification
        last_error = None
        last_verification_details = {}
        function_result = None

        for attempt in range(max_retries + 1):
            is_retry = attempt > 0

            if is_retry:
                logger.info(
                    "tool_retry_attempt",
                    function=function_name,
                    attempt=attempt,
                    max_retries=max_retries,
                    delay=retry_delay
                )
                time.sleep(retry_delay)

            # Step 2: Execute function
            try:
                function_result = self.execute_fn(function_name, function_args)
            except Exception as e:
                execution_error = str(e)
                # Don't retry execution errors - they're usually not transient
                if self.log_fn:
                    self.log_fn(
                        call_id=tool_call_id,
                        model=model,
                        function=function_name,
                        status="execution_error",
                        args=function_args,
                        error=execution_error,
                        duration_ms=round((time.time() - call_start_time) * 1000, 2),
                        success=False
                    )
                return {"error": execution_error}, "execution_error"

            # Step 3: Verify result (if verifier provided)
            if self.verify_fn and is_write_op:
                verification_result = self.verify_fn(
                    function_name, function_args, function_result
                )

                # Handle both 2-tuple (legacy) and 3-tuple (new) return formats
                if len(verification_result) == 3:
                    verification_status, verification_error, verification_details = verification_result
                else:
                    verification_status, verification_error = verification_result
                    verification_details = {}

                if verification_status == "failed":
                    last_error = verification_error
                    last_verification_details = verification_details

                    # Log the verification failure
                    logger.warning(
                        "verification_failed",
                        function=function_name,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error=verification_error,
                        checks_failed=verification_details.get("checks_failed", [])
                    )

                    # If we have more retries, continue
                    if attempt < max_retries:
                        continue

                    # No more retries - handle based on strict mode
                    if strict_mode:
                        if self.log_fn:
                            self.log_fn(
                                call_id=tool_call_id,
                                model=model,
                                function=function_name,
                                status="verification_failed",
                                args=function_args,
                                error=verification_error,
                                duration_ms=round((time.time() - call_start_time) * 1000, 2),
                                success=False
                            )

                        # Format comprehensive error message
                        from utils.obsidian_verification import format_verification_failure, VerificationResult
                        verification_obj = VerificationResult(
                            success=False,
                            operation=function_name,
                            details=verification_error,
                            checks_passed=verification_details.get("checks_passed", []),
                            checks_failed=verification_details.get("checks_failed", []),
                            suggestions=verification_details.get("suggestions", [])
                        )
                        formatted_error = format_verification_failure(
                            function_result.get("message", "Operation completed"),
                            verification_obj,
                            attempt + 1
                        )

                        error_response = {
                            "success": False,
                            "error": formatted_error,
                            "verification": {
                                "status": "failed",
                                "attempts": attempt + 1,
                                "details": verification_details
                            }
                        }
                        return error_response, "verification_failed"
                    else:
                        # Non-strict mode: log warning but continue
                        logger.warning(
                            "verification_failed_non_strict",
                            function=function_name,
                            error=verification_error,
                            continuing=True
                        )
                        # Mark as passed but with warning
                        function_result.setdefault("verification", {}).update({
                            "status": "warning",
                            "message": f"Verification failed but strict mode disabled: {verification_error}",
                            "attempts": attempt + 1
                        })
                        break

                elif verification_status == "passed":
                    # Verification successful - mark it and break out of retry loop
                    function_result.setdefault("verification", {}).update({
                        "status": "passed",
                        "checks_passed": verification_details.get("checks_passed", []),
                        "details": verification_details.get("details", ""),
                        "attempt": attempt + 1
                    })
                    break

                else:
                    # Status is "skipped" - break out of loop
                    break
            else:
                # No verification needed - break out of loop
                break

        # Step 4: Log success
        if self.log_fn:
            self.log_fn(
                call_id=tool_call_id,
                model=model,
                function=function_name,
                status="success",
                args=function_args,
                duration_ms=round((time.time() - call_start_time) * 1000, 2),
                success=True
            )

        # Step 5: Update conversation context (if context updater provided)
        if self.update_context_fn and chat_id and chat_loader_fn and chat_saver_fn:
            try:
                chat = chat_loader_fn(chat_id)
                if chat:
                    # Initialize context_memory if it doesn't exist
                    if "context_memory" not in chat.get("meta", {}):
                        from context_aware import initialize_context
                        chat.setdefault("meta", {})["context_memory"] = initialize_context()

                    context_memory = chat["meta"]["context_memory"]
                    updated_context = self.update_context_fn(
                        context_memory,
                        function_name,
                        function_args,
                        success=True
                    )
                    chat["meta"]["context_memory"] = updated_context
                    chat_saver_fn(chat)
            except Exception:
                # Don't fail tool execution if context update fails
                pass

        return function_result, "success"

    def execute_tool_calls_batch(
        self,
        tool_calls: list,
        model: str,
        chat_id: Optional[str] = None,
        chat_loader_fn: Optional[Callable] = None,
        chat_saver_fn: Optional[Callable] = None
    ) -> list:
        """
        Execute a batch of tool calls from OpenAI-style tool_calls array.

        Args:
            tool_calls: List of tool call dicts with id, function.name, function.arguments
            model: Model name for logging
            chat_id: Optional chat ID for context updates
            chat_loader_fn: Optional function to load chat
            chat_saver_fn: Optional function to save chat

        Returns:
            List of message dicts ready to append to conversation
            [{"role": "tool", "tool_call_id": "...", "content": "{...}"}]
        """
        result_messages = []

        for tool_call in tool_calls:
            call_id = tool_call.get("id", "")
            function_name = tool_call.get("function", {}).get("name", "")
            args_json = tool_call.get("function", {}).get("arguments", "{}")

            # Parse arguments
            try:
                function_args = json.loads(args_json)
            except json.JSONDecodeError as e:
                parse_error = f"JSON parse error: {str(e)}"
                if self.log_fn:
                    self.log_fn(
                        call_id=call_id,
                        model=model,
                        function=function_name,
                        status="parse_error",
                        args={},
                        error=parse_error,
                        duration_ms=0
                    )
                result_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps({"error": parse_error})
                })
                continue

            # Execute the tool
            result, status = self.execute_tool_call(
                tool_call_id=call_id,
                function_name=function_name,
                function_args=function_args,
                model=model,
                chat_id=chat_id,
                chat_loader_fn=chat_loader_fn,
                chat_saver_fn=chat_saver_fn
            )

            # Append result message
            result_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result)
            })

        return result_messages

    def execute_anthropic_tool(
        self,
        tool_use_block,
        model: str,
        chat_id: Optional[str] = None,
        chat_loader_fn: Optional[Callable] = None,
        chat_saver_fn: Optional[Callable] = None
    ) -> Tuple[Dict[str, Any], str]:
        """
        Execute a single Anthropic-style tool use block.

        Args:
            tool_use_block: Anthropic tool use block with .id, .name, .input
            model: Model name for logging
            chat_id: Optional chat ID for context updates
            chat_loader_fn: Optional function to load chat
            chat_saver_fn: Optional function to save chat

        Returns:
            Tuple of (result_dict, tool_use_id)
        """
        function_name = tool_use_block.name
        function_args = tool_use_block.input
        tool_use_id = tool_use_block.id

        result, status = self.execute_tool_call(
            tool_call_id=tool_use_id,
            function_name=function_name,
            function_args=function_args,
            model=model,
            chat_id=chat_id,
            chat_loader_fn=chat_loader_fn,
            chat_saver_fn=chat_saver_fn
        )

        # Convert error statuses to Anthropic-friendly format
        if status == "validation_error":
            result = {
                "success": False,
                "message": result.get("error", "Validation failed"),
                "validation_failed": True,
            }
        elif status == "verification_failed":
            result = {
                "success": False,
                "message": result.get("error", "Verification failed"),
                "verification_failed": True,
            }
        elif status == "execution_error":
            result = {
                "success": False,
                "message": result.get("error", "Execution failed"),
            }

        return result, tool_use_id

    def format_tool_result_for_anthropic(
        self,
        tool_use_id: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Format a tool result for Anthropic's message format.

        Args:
            tool_use_id: ID from the tool use block
            result: Tool execution result dict

        Returns:
            Message dict ready to append to conversation
        """
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(result)
                }
            ]
        }

    def convert_openai_tools_to_anthropic(
        self,
        openai_functions: list
    ) -> list:
        """
        Convert OpenAI-style function definitions to Anthropic tool format.

        Args:
            openai_functions: List of OpenAI function defs with name, description, parameters

        Returns:
            List of Anthropic tool defs with name, description, input_schema
        """
        anthropic_tools = []
        for func in openai_functions:
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {})
            })
        return anthropic_tools
