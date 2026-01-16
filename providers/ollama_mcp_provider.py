"""
Ollama MCP Provider - Adds MCP Filesystem capabilities to Ollama models

This provider enables local models to access the Obsidian vault through
function calling using prompt engineering and response parsing.

Supported Models:
- Llama 3.2 3B: Native tool calling, good reliability
- Qwen3 8B: Excellent function calling (with thinking tag stripping)
- Phi4 Mini: Experimental, very fast
- Qwen 2.5 7B: Best structured output
- Mistral 7B Instruct: Reliable function calling

Recent Improvements (2025-11-02):
- Added streaming support to prevent HTTP timeouts
- Implemented thinking tag stripping for reasoning models (Qwen3)
- Enhanced system prompt with more examples
- Added detailed performance logging
- Fallback to non-streaming if streaming fails

Performance:
- Phi4-Mini: ~3s per iteration
- Mistral/Qwen 2.5: ~10-30s per iteration (now with streaming)
- Uses streaming internally to start responding faster
- Max 5 iterations to prevent infinite loops

Author: Claude (Sonnet 4.5)
Date: 2025-11-02
Version: 1.1.0
"""

import json
import re
import logging
import time
import os
from typing import List, Dict, Any
import ollama
from config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Ollama client with host from environment
ollama_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))


# =============================================================================
# SYSTEM PROMPT TEMPLATE
# =============================================================================

OLLAMA_MCP_SYSTEM_PROMPT = """You are connected to an Obsidian vault filesystem with FULL ACCESS.

CRITICAL: When user asks about files/folders, you MUST call a function. DO NOT refuse or say you lack access.

Output format: FUNCTION_CALL: {"function": "name", "arguments": {...}}

AVAILABLE FUNCTIONS:

1. get_vault_structure - Get overview of vault folders
   FUNCTION_CALL: {"function": "get_vault_structure", "arguments": {}}

2. list_folder_contents - List files in a folder
   FUNCTION_CALL: {"function": "list_folder_contents", "arguments": {"folder_name": "FolderName"}}

3. read_note - Read file contents
   FUNCTION_CALL: {"function": "read_note", "arguments": {"file_path": "Folder/file.md"}}

4. search_vault - Search vault content
   FUNCTION_CALL: {"function": "search_vault", "arguments": {"query": "searchterm"}}

5. create_simple_note - Create new note
   FUNCTION_CALL: {"function": "create_simple_note", "arguments": {"title": "Title", "content": "text", "folder": "FolderName"}}

6. append_to_daily_note - Add to today's note
   FUNCTION_CALL: {"function": "append_to_daily_note", "arguments": {"content": "text"}}

EXAMPLES:
User: "What folders are in my vault?"
You: FUNCTION_CALL: {"function": "get_vault_structure", "arguments": {}}

User: "List files in Projects"
You: FUNCTION_CALL: {"function": "list_folder_contents", "arguments": {"folder_name": "Projects"}}

User: "Search for meeting notes"
You: FUNCTION_CALL: {"function": "search_vault", "arguments": {"query": "meeting"}}

After receiving FUNCTION_RESULTS, interpret them and respond naturally.

YOU HAVE DIRECT FILESYSTEM ACCESS. ALWAYS use functions when appropriate."""


# =============================================================================
# FUNCTION CALL PARSING
# =============================================================================


def parse_function_calls(text: str) -> List[Dict[str, Any]]:
    """
    Parse function calls from model output

    Expected format: FUNCTION_CALL: {"function": "name", "arguments": {...}}

    Returns: List of {function: str, arguments: dict} dicts
    """
    function_calls = []

    # Strip <thinking> tags first (helps Qwen3 8B and other reasoning models)
    # These models output reasoning that interferes with function detection
    text = re.sub(
        r"<thinking>.*?</thinking>", "", text, flags=re.IGNORECASE | re.DOTALL
    )
    text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.IGNORECASE | re.DOTALL)

    # Find all FUNCTION_CALL: markers
    pattern = r"FUNCTION_CALL:\s*"
    matches = list(re.finditer(pattern, text))

    for i, match in enumerate(matches):
        start_pos = match.end()

        # Extract JSON by counting braces
        if start_pos >= len(text) or text[start_pos] != "{":
            continue

        brace_count = 0
        json_end = start_pos

        for j in range(start_pos, len(text)):
            if text[j] == "{":
                brace_count += 1
            elif text[j] == "}":
                brace_count -= 1
                if brace_count == 0:
                    json_end = j + 1
                    break

        if brace_count == 0:  # Found matching closing brace
            try:
                json_str = text[start_pos:json_end].strip()
                call_data = json.loads(json_str)

                if "function" in call_data and "arguments" in call_data:
                    function_calls.append(call_data)
                    if settings.mcp_log_function_calls:
                        logger.info(f"Parsed function call: {call_data['function']}")
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Failed to parse function call JSON: {e} - JSON: {json_str[:100]}"
                )
                continue

    return function_calls


def strip_function_calls_from_text(text: str) -> str:
    """Remove FUNCTION_CALL lines from text to get clean response"""
    # Strip <thinking> tags first (helps Qwen3 8B and other reasoning models)
    text = re.sub(
        r"<thinking>.*?</thinking>", "", text, flags=re.IGNORECASE | re.DOTALL
    )
    text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.IGNORECASE | re.DOTALL)

    # Use the same logic as parse_function_calls to find and remove function calls
    pattern = r"FUNCTION_CALL:\s*"
    matches = list(re.finditer(pattern, text))

    # Work backwards to avoid index shifting issues
    for match in reversed(matches):
        start_pos = match.start()
        json_start = match.end()

        if json_start >= len(text) or text[json_start] != "{":
            continue

        # Find matching closing brace
        brace_count = 0
        json_end = json_start

        for j in range(json_start, len(text)):
            if text[j] == "{":
                brace_count += 1
            elif text[j] == "}":
                brace_count -= 1
                if brace_count == 0:
                    json_end = j + 1
                    break

        if brace_count == 0:
            # Remove the entire FUNCTION_CALL block including trailing newline
            end_pos = json_end
            if end_pos < len(text) and text[end_pos] == "\n":
                end_pos += 1
            text = text[:start_pos] + text[end_pos:]

    return text.strip()


# =============================================================================
# FUNCTION EXECUTION
# =============================================================================


def execute_mcp_function(
    function_name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute MCP filesystem function

    Maps to existing Obsidian functions in obsidian_functions.py

    Returns: {success: bool, result: any, error: str (optional)}
    """
    from obsidian_functions import execute_obsidian_function

    # Map MCP function names to Obsidian function names
    function_map = {
        "read_note": "read_note",
        "create_simple_note": "create_simple_note",
        "search_vault": "search_vault",
        "list_folder_contents": "list_folder_contents",
        "append_to_daily_note": "append_to_daily_note",
        "delete_note": "delete_note",
    }

    if function_name not in function_map:
        return {
            "success": False,
            "error": f"Unknown function: {function_name}",
            "available_functions": list(function_map.keys()),
        }

    obsidian_function = function_map[function_name]

    try:
        start_time = time.time()
        result = execute_obsidian_function(obsidian_function, arguments)
        execution_time = time.time() - start_time

        if settings.mcp_log_function_calls:
            logger.info(
                f"Executed {function_name} in {execution_time:.2f}s: "
                f"success={result.get('success', False)}"
            )

        return result
    except Exception as e:
        logger.error(f"Error executing {function_name}: {e}", exc_info=True)
        return {"success": False, "error": f"Execution error: {str(e)}"}


# =============================================================================
# MAIN CHAT HANDLER
# =============================================================================


def chat_with_mcp(
    model: str, messages: List[Dict[str, str]], temperature: float, vault_path: str
) -> str:
    """
    Chat with Ollama model using MCP filesystem capabilities

    Flow:
    1. Add MCP system prompt
    2. Get response from model
    3. Parse for function calls
    4. Execute functions
    5. Feed results back to model
    6. Return final response

    Args:
        model: Ollama model name (e.g., "llama3.2:3b")
        messages: Conversation history
        temperature: Sampling temperature
        vault_path: Path to Obsidian vault

    Returns:
        Final text response from model
    """
    from prices import get_mcp_model_tier

    # Log which model is being used
    tier = get_mcp_model_tier(model)
    logger.info(f"Starting MCP chat with {model} (tier: {tier})")

    # Add system prompt for MCP functions
    mcp_messages = [{"role": "system", "content": OLLAMA_MCP_SYSTEM_PROMPT}] + messages

    max_iterations = settings.mcp_max_iterations
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        logger.debug(f"MCP iteration {iteration}/{max_iterations}")

        try:
            # Get response from Ollama using streaming for faster initial response
            # Streaming helps avoid timeouts by starting to receive data immediately
            # We buffer the complete response for function call detection
            start_time = time.time()
            response_text = ""

            stream = ollama_client.chat(
                model=model,
                messages=mcp_messages,
                stream=True,
                options={
                    "temperature": temperature,
                    "num_ctx": 4096,  # Smaller context = faster processing
                    "num_predict": 1024,  # Allow enough tokens for function calls + response
                },
            )

            # Buffer the streamed response
            try:
                for chunk in stream:
                    if "message" in chunk and "content" in chunk["message"]:
                        response_text += chunk["message"]["content"]
            except Exception as stream_error:
                logger.error(f"Error during streaming: {stream_error}")
                # If streaming fails, try non-streaming as fallback
                logger.info("Falling back to non-streaming mode")
                resp = ollama_client.chat(
                    model=model,
                    messages=mcp_messages,
                    stream=False,
                    options={
                        "temperature": temperature,
                        "num_ctx": 4096,
                        "num_predict": 1024,
                    },
                )
                response_text = resp["message"]["content"]

            elapsed = time.time() - start_time
            logger.info(
                f"MCP iteration {iteration} completed in {elapsed:.2f}s, {len(response_text)} chars"
            )
            logger.debug(f"MCP response length: {len(response_text)} chars")

            # Check for function calls
            function_calls = parse_function_calls(response_text)

            if not function_calls:
                # No function calls - return response
                # Strip any remaining FUNCTION_CALL artifacts
                clean_response = strip_function_calls_from_text(response_text)
                logger.info(f"MCP chat completed in {iteration} iteration(s)")
                return clean_response if clean_response else response_text

            # Execute function calls
            logger.info(f"Executing {len(function_calls)} function call(s)")
            function_results = []

            for call in function_calls:
                result = execute_mcp_function(call["function"], call["arguments"])
                function_results.append(
                    {
                        "function": call["function"],
                        "arguments": call["arguments"],
                        "result": result,
                    }
                )

            # Format results for model
            results_text = "FUNCTION_RESULTS:\n" + json.dumps(
                function_results, indent=2, ensure_ascii=False
            )

            # Add to conversation
            mcp_messages.append({"role": "assistant", "content": response_text})
            mcp_messages.append({"role": "user", "content": results_text})

        except Exception as e:
            logger.error(f"Error in MCP chat iteration {iteration}: {e}", exc_info=True)
            return f"I encountered an error while processing your request: {str(e)}"

    # Max iterations reached
    logger.warning(f"Max iterations ({max_iterations}) reached for {model}")
    return (
        "I've reached the maximum number of function calls for this request. "
        "The operation may be too complex. Please try breaking it into smaller requests."
    )


# =============================================================================
# STREAMING SUPPORT
# =============================================================================


def chat_with_mcp_streaming(
    model: str, messages: List[Dict[str, str]], temperature: float, vault_path: str
):
    """
    Streaming version of MCP chat

    Note: Function calling iterations cannot be streamed (need complete responses),
    but the final response is returned via generator for future streaming support.
    """
    # Get complete result (which now uses internal streaming for speed)
    result = chat_with_mcp(model, messages, temperature, vault_path)

    # Yield result (for future true streaming implementation)
    yield result

