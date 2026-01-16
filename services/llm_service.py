"""
LLM Service - Provider abstraction for chat completions

This service handles:
- Provider selection (Claude, OpenAI, Ollama, Ollama MCP)
- Provider-specific API call formatting
- Tool calling orchestration
- Response parsing and normalization

Used by: routes/chat_routes.py (in /ask endpoint)

This service extracts the 980-line /ask endpoint logic into a clean, testable service layer.
Each provider has its own implementation method, and the main complete_chat() entry point
routes to the appropriate provider based on model type.
"""

import os
import json
import uuid
import datetime
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import structlog
import pytz

from config import get_settings
from prices import get_provider_type

# OpenAI client
from openai import OpenAI

# Anthropic client (optional)
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Ollama client
import ollama

# Tool-related imports
from obsidian_functions import OBSIDIAN_FUNCTIONS, execute_obsidian_function
from observability import log_tool_call
from tool_schema import validate_tool_call
from context_aware import initialize_context, update_context_from_tool
from storage import load_chat, save_chat
from services.tool_calling_service import ToolCallingService
# Note: verify_tool_result imported lazily in __init__ to avoid circular import

# Prompt variants for Ollama A/B testing
from prompt_variants import get_system_message, PROMPT_VARIANTS
from ollama_tooling import build_ollama_tools, LOCAL_MODEL_CORE_TOOLS, LOCAL_MODEL_TOOL_ORDER

# Autonomous mode imports
from general_tools import (
    GENERAL_TOOLS, 
    GENERAL_FUNCTION_NAMES,
    execute_general_function,
    get_general_tools_openai_format,
    get_general_tools_anthropic_format
)
from autonomous_prompts import get_autonomous_system_prompt, get_autonomous_system_prompt_minimal

# Smart home integration
try:
    from smarthome_functions import SMARTHOME_FUNCTIONS, execute_smarthome_function
    SMARTHOME_AVAILABLE = True
except ImportError:
    SMARTHOME_FUNCTIONS = []
    SMARTHOME_AVAILABLE = False
    print("INFO: Smart home functions not available (smarthome_functions.py not found)")

# Microsoft To Do integration
try:
    from microsoft_todo_functions import TODO_FUNCTIONS, execute_todo_function
    TODO_AVAILABLE = True
except ImportError:
    TODO_FUNCTIONS = []
    TODO_AVAILABLE = False
    print("INFO: Microsoft To Do functions not available (microsoft_todo_functions.py not found)")

# Combined functions list for all tools
# ToDo functions first so models see them before the 30+ vault functions
ALL_FUNCTIONS = TODO_FUNCTIONS + SMARTHOME_FUNCTIONS + OBSIDIAN_FUNCTIONS

# Smart home function names for routing
SMARTHOME_FUNCTION_NAMES = {f["name"] for f in SMARTHOME_FUNCTIONS} if SMARTHOME_FUNCTIONS else set()

# To Do function names for routing
TODO_FUNCTION_NAMES = {f["name"] for f in TODO_FUNCTIONS} if TODO_FUNCTIONS else set()



def execute_function(function_name: str, arguments: dict) -> dict:
    """
    Unified function executor that routes to appropriate handler.
    
    Routes to:
    - General tools (autonomous mode): read_file, write_file, etc.
    - Smart home tools: light controls, etc.
    - Todo tools: Microsoft To Do integration
    - Obsidian tools (structured mode): create_job_note, append_to_daily_note, etc.
    
    Args:
        function_name: Name of the function to execute
        arguments: Dictionary of function arguments
    
    Returns:
        dict: Result of the function execution
    """
    # Check for general/autonomous mode tools first
    if function_name in GENERAL_FUNCTION_NAMES:
        return execute_general_function(function_name, arguments)
    elif function_name in SMARTHOME_FUNCTION_NAMES:
        return execute_smarthome_function(function_name, arguments)
    elif function_name in TODO_FUNCTION_NAMES:
        return execute_todo_function(function_name, arguments)
    else:
        return execute_obsidian_function(function_name, arguments)

logger = structlog.get_logger()
settings = get_settings()

# Tool-calling guard constant
WRITE_TOOL_REMINDER = (
    "Reminder: Vault operations require calling the appropriate Obsidian tool. "
    "Do not claim success until the tool call succeeds."
)
READ_TOOL_REMINDER = (
    "Reminder: This request requires checking the vault or task list. "
    "Use the appropriate tool to retrieve the information."
)


class LLMService:
    """Handles LLM provider interactions and tool calling"""

    def __init__(self):
        self.settings = get_settings()
        self.ollama_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
        
        # Initialize ToolCallingService for centralized tool execution
        # Import verify_tool_result here to avoid circular import with chat_routes
        from routes.chat_routes import verify_tool_result
        self.tool_service = ToolCallingService(
            execute_fn=execute_function,  # Use unified executor for all tools
            verify_fn=verify_tool_result,
            log_fn=log_tool_call,
            validate_fn=validate_tool_call,
            update_context_fn=update_context_from_tool,
        )

    def get_provider(self, model: str) -> str:
        """
        Determine which provider to use for a given model.

        Args:
            model: Model identifier

        Returns:
            Provider name: 'anthropic', 'openai', 'ollama', 'ollama_mcp'
        """
        return get_provider_type(model)

    def get_tools_for_mode(self, provider: str = 'openai') -> list:
        """
        Get the appropriate tools based on agent_mode setting.
        
        Args:
            provider: 'openai', 'anthropic', or 'ollama'
            
        Returns:
            List of tool definitions in provider-appropriate format
        """
        if self.settings.agent_mode == 'autonomous':
            # Autonomous mode: general vault tools + smart home tools
            # This gives ~11 focused tools instead of 30+ complex ones
            if provider == 'anthropic':
                todo = [
                    {
                        'name': func['name'],
                        'description': func.get('description', ''),
                        'input_schema': func.get('parameters', {}),
                    }
                    for func in TODO_FUNCTIONS
                ]
                general = get_general_tools_anthropic_format()
                smarthome = [
                    {
                        'name': func['name'],
                        'description': func.get('description', ''),
                        'input_schema': func.get('parameters', {}),
                    }
                    for func in SMARTHOME_FUNCTIONS
                ]
                return todo + general + smarthome
            else:  # openai or ollama
                todo = [{'type': 'function', 'function': fn} for fn in TODO_FUNCTIONS]
                general = get_general_tools_openai_format()
                smarthome = [{'type': 'function', 'function': fn} for fn in SMARTHOME_FUNCTIONS]
                return todo + general + smarthome
        else:  # structured mode
            if provider == 'anthropic':
                return [
                    {
                        'name': func['name'],
                        'description': func.get('description', ''),
                        'input_schema': func.get('parameters', {}),
                    }
                    for func in ALL_FUNCTIONS
                ]
            else:
                return [{'type': 'function', 'function': fn_def} for fn_def in ALL_FUNCTIONS]

    def get_system_prompt_for_mode(self, current_date: str, current_time: str, timezone: str) -> dict:
        """
        Get the appropriate system prompt based on agent_mode setting.
        
        Args:
            current_date: Current date string
            current_time: Current time string
            timezone: Timezone string
            
        Returns:
            System message dict
        """
        if self.settings.agent_mode == 'autonomous':
            return get_autonomous_system_prompt(current_date, current_time, timezone)
        else:
            return None  # Structured mode uses existing vault_guidance

    def is_autonomous_mode(self) -> bool:
        """Check if running in autonomous mode."""
        return self.settings.agent_mode == 'autonomous'

    def _strip_json_prefix(self, text: str) -> str:
        """
        Strip preamble, JSON objects/arrays, and tool echoes from a response.

        Some models echo tool parameters or results as JSON, or add preamble
        like "I'll check..." before giving the actual answer.

        Args:
            text: Response text that may contain noise

        Returns:
            Cleaned text with just the answer
        """
        import re

        if not text:
            return text

        original = text

        # First, strip common preamble patterns
        preamble_patterns = [
            r"^I'll\s+(check|open|read|look|search|find)[^.]*\.\s*",
            r"^Let\s+me\s+(check|open|read|look|search|find)[^.]*\.\s*",
            r"^I'm\s+going\s+to\s+(check|open|read|look|search|find)[^.]*\.\s*",
            r"^Checking[^.]*\.\s*",
            r"^Reading[^.]*\.\s*",
            r"^Opening[^.]*\.\s*",
        ]
        for pattern in preamble_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Repeatedly strip JSON objects and tool patterns from the beginning
        max_iterations = 10
        for _ in range(max_iterations):
            text = text.lstrip()
            if not text:
                break

            if text[0] == '{':
                end = self._find_matching_brace(text, '{', '}')
                if end > 0:
                    text = text[end:].lstrip()
                    continue
            elif text[0] == '[':
                end = self._find_matching_brace(text, '[', ']')
                if end > 0:
                    text = text[end:].lstrip()
                    continue

            # Patterns like (read_file)/path or [tool: path]
            tool_pattern = re.compile(r'^[\[\(]\w+[\)\]][/\\]?[^\s]*\s*', re.DOTALL)
            match = tool_pattern.match(text)
            if match:
                text = text[match.end():]
                continue

            break

        if text != original:
            print(f"[CLEAN] Stripped preamble/JSON from response")

        return text.strip()

    def _parse_pseudo_tool_call(self, content: str) -> Optional[Dict]:
        """
        Parse a pseudo tool call from model content that looks like a tool call.

        Handles patterns like:
        - [read_file: path] {"path": "..."}
        - (read_file){"path": "..."}
        - {"path": "..."} (infer read_file)
        - [search: query] {"query": "..."}

        Args:
            content: Model response content

        Returns:
            Dict with 'name' and 'arguments' if parsed, None otherwise
        """
        import re
        import json

        if not content:
            return None

        content = content.strip()

        # Pattern 1: [tool_name: target] or (tool_name) followed by JSON
        tool_bracket_pattern = re.compile(
            r'^[\[\(](\w+)[:\s\)\]].*?(\{[^{}]*\})',
            re.DOTALL
        )
        match = tool_bracket_pattern.match(content)
        if match:
            tool_name = match.group(1)
            json_str = match.group(2)
            try:
                args = json.loads(json_str)
                # Filter to known parameters only
                if tool_name == 'read_file':
                    args = {'path': args.get('path', '')}
                elif tool_name == 'search':
                    args = {'query': args.get('query', ''), 'folder': args.get('folder', '')}
                elif tool_name == 'write_file':
                    args = {'path': args.get('path', ''), 'content': args.get('content', '')}
                print(f"[FALLBACK] Parsed pseudo tool call: {tool_name}({args})")
                return {'name': tool_name, 'arguments': json.dumps(args)}
            except json.JSONDecodeError:
                pass

        # Pattern 2: Bare JSON with "path" key -> assume read_file
        if content.startswith('{'):
            end = self._find_matching_brace(content, '{', '}')
            if end > 0:
                try:
                    args = json.loads(content[:end])
                    if 'path' in args:
                        filtered_args = {'path': args['path']}
                        print(f"[FALLBACK] Inferred read_file from JSON: {filtered_args}")
                        return {'name': 'read_file', 'arguments': json.dumps(filtered_args)}
                    elif 'query' in args:
                        filtered_args = {'query': args['query'], 'folder': args.get('folder', '')}
                        print(f"[FALLBACK] Inferred search from JSON: {filtered_args}")
                        return {'name': 'search', 'arguments': json.dumps(filtered_args)}
                except json.JSONDecodeError:
                    pass

        return None

    def _find_matching_brace(self, text: str, open_char: str, close_char: str) -> int:
        """
        Find the position after the matching closing brace/bracket.

        Args:
            text: String starting with open_char
            open_char: Opening character ('{' or '[')
            close_char: Closing character ('}' or ']')

        Returns:
            Position after the closing brace, or -1 if not found
        """
        if not text or text[0] != open_char:
            return -1

        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    return i + 1

        return -1  # No matching brace found

    def robust_usage(self, resp_usage) -> Tuple[int, int]:
        """
        Extract token counts from API response usage object.

        Handles both OpenAI and Anthropic response formats.

        Args:
            resp_usage: Usage object from API response

        Returns:
            (input_tokens, output_tokens) tuple
        """
        if not resp_usage:
            return 0, 0

        in_tok = getattr(resp_usage, "prompt_tokens", None) or getattr(
            resp_usage, "input_tokens", 0
        )
        out_tok = getattr(resp_usage, "completion_tokens", None) or getattr(
            resp_usage, "output_tokens", 0
        )

        return int(in_tok or 0), int(out_tok or 0)

    def complete_chat(
        self,
        model: str,
        messages: List[Dict],
        temperature: float = 0.7,
        write_intent: bool = False,
        read_intent: bool = False,
        chat_id: Optional[str] = None,
        chat_mode: str = "agentic",
    ) -> Dict:
        """
        Execute chat completion with appropriate provider.

        Args:
            model: Model identifier (e.g., 'claude-sonnet-4.5', 'gpt-4o')
            messages: Conversation history [{"role": "user", "content": "..."}]
            temperature: Sampling temperature
            write_intent: Whether user intent indicates write operation
            read_intent: Whether user intent indicates read/search operation
            chat_id: Optional chat ID for context updates
            chat_mode: Chat mode ('agentic' or 'chat'). In 'chat' mode, tools
                      and vault guidance are disabled for streaming conversation.

        Returns:
            {
                "text": str,              # Assistant response
                "input_tokens": int,      # Tokens in prompt
                "output_tokens": int,     # Tokens in completion
            }
        """
        provider_type = self.get_provider(model)

        if provider_type == "ollama_tools":
            return self._complete_ollama_tools(model, messages, temperature, write_intent, chat_id, chat_mode)
        elif provider_type == "ollama_mcp":
            return self._complete_ollama_mcp(model, messages, temperature, chat_mode)
        elif provider_type == "ollama":
            return self._complete_ollama(model, messages, temperature, chat_mode)
        elif provider_type == "anthropic":
            return self._complete_anthropic(model, messages, temperature, write_intent, read_intent, chat_id, chat_mode)
        else:
            # Default to OpenAI
            return self._complete_openai(model, messages, temperature, write_intent, read_intent, chat_id, chat_mode)

    def _complete_ollama_tools(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        write_intent: bool,
        chat_id: Optional[str],
        chat_mode: str = "agentic"
    ) -> Dict:
        """
        Handle Ollama models with native tool calling support.

        Uses Ollama's native 'tools' API parameter for reliable function calling.
        Supports: qwen2.5:7b, qwen2.5:14b, llama3.2:3b

        Args:
            model: Ollama model name
            messages: Conversation messages
            temperature: Sampling temperature
            write_intent: Whether user intent indicates write operation
            chat_id: Optional chat ID for context updates
            chat_mode: Chat mode ('agentic' or 'chat')

        Returns:
            {"text": str, "input_tokens": int, "output_tokens": int}
        """
        from prices import get_model_tier

        tier = get_model_tier(model)

        # Use configured temperature for Ollama (overrides caller value for consistency)
        ollama_temperature = self.settings.ollama_temperature
        logger.info(f"Using Ollama native tools provider for model: {model} (tier: {tier}, temp: {ollama_temperature}, mode: {chat_mode})")

        # Preprocess messages: convert any multimodal content to plain text
        # Ollama expects string content, not dict
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, dict) and content.get("_multimodal"):
                # Extract text and image info from multimodal content
                text = content.get("text", "")
                image_name = content.get("image_name", "attached image")
                msg["content"] = f"{text}\n[Image attached: {image_name}]"

        # In chat mode, skip vault guidance and tools entirely
        if chat_mode == "chat":
            logger.info("Chat mode: skipping vault guidance and tools for streaming conversation")
            ollama_tools = []
        else:
            # Build system prompt with vault guidance
            user_tz_str = self.settings.timezone or "US/Eastern"
            try:
                user_tz = pytz.timezone(user_tz_str)
                current_time_tz = datetime.datetime.now(user_tz)
                current_date = current_time_tz.strftime("%Y-%m-%d")
                current_time = current_time_tz.strftime("%H:%M:%S %Z")
                tomorrow_date = (current_time_tz + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                current_time_tz = datetime.datetime.utcnow()
                current_date = current_time_tz.strftime("%Y-%m-%d")
                current_time = current_time_tz.strftime("%H:%M:%S UTC")
                tomorrow_date = (current_time_tz + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

            # Add system prompt based on mode
            variant_name = self.settings.ollama_prompt_variant
            if variant_name not in PROMPT_VARIANTS:
                logger.warning(f"Unknown prompt variant '{variant_name}', falling back to CURRENT")
                variant_name = "CURRENT"

            # Get system message - check autonomous mode first
            if self.is_autonomous_mode():
                vault_guidance = self.get_system_prompt_for_mode(current_date, current_time, user_tz_str)
                logger.info("ollama_autonomous_mode", chars=len(vault_guidance.get("content", "")) if vault_guidance else 0)
            else:
                vault_guidance = get_system_message(variant_name, current_date, current_time, user_tz_str)
                if vault_guidance is not None:
                    logger.debug("ollama_prompt_variant", variant=variant_name, chars=len(vault_guidance.get("content", "")))
                else:
                    logger.debug("ollama_prompt_variant", variant=variant_name, chars=0)

            if vault_guidance is not None:
                system_count = sum(1 for m in messages if m.get("role") == "system")
                messages.insert(system_count, vault_guidance)

            # Select tools based on agent mode
            if self.is_autonomous_mode():
                # Autonomous mode: TODO + general + smart home tools
                ollama_tools = []
                for func in TODO_FUNCTIONS:
                    ollama_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": func["name"],
                                "description": func.get("description", ""),
                                "parameters": func.get("parameters", {})
                            }
                        }
                    )
                for t in GENERAL_TOOLS:
                    ollama_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": t["name"],
                                "description": t["description"],
                                "parameters": t["parameters"]
                            }
                        }
                    )
                for func in SMARTHOME_FUNCTIONS:
                    ollama_tools.append({
                        "type": "function",
                        "function": {
                            "name": func["name"],
                            "description": func.get("description", ""),
                            "parameters": func.get("parameters", {})
                        }
                    })
                logger.info(
                    "ollama_autonomous_tools",
                    count=len(ollama_tools),
                    todo=len(TODO_FUNCTIONS),
                    general=len(GENERAL_TOOLS),
                    smarthome=len(SMARTHOME_FUNCTIONS),
                )
            else:
            # Filter tools for local models to improve selection accuracy
                # Local models struggle with large tool sets (30+), so we offer a curated subset
                available_tools = {t.get("name") for t in ALL_FUNCTIONS}
                missing_tools = sorted(LOCAL_MODEL_CORE_TOOLS.difference(available_tools))
                if missing_tools:
                    logger.warning("ollama_tool_missing", missing=missing_tools)

                # Convert function definitions to Ollama tool format (ordering + truncation)
                ollama_tools = build_ollama_tools(
                    ALL_FUNCTIONS,
                    tool_names=LOCAL_MODEL_CORE_TOOLS,
                    tool_order=LOCAL_MODEL_TOOL_ORDER,
                )

        debug_id = uuid.uuid4().hex[:8]

        def _debug_write_payload(label: str, payload: Dict) -> None:
            debug_dir = self.settings.ollama_payload_debug_dir
            if not debug_dir:
                return
            try:
                debug_dir_str = str(debug_dir).strip()
                if not debug_dir_str:
                    return
                debug_path = Path(debug_dir_str)
                debug_path.mkdir(parents=True, exist_ok=True)
                payload_json = json.dumps(
                    payload,
                    sort_keys=True,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    default=str,
                )
                digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
                filename = f"ollama_payload_{label}_{debug_id}_{digest[:8]}.json"
                file_path = debug_path / filename
                file_path.write_text(payload_json + "\n", encoding="utf-8")
                logger.debug(
                    "ollama_payload_saved",
                    label=label,
                    model=model,
                    chat_id=chat_id,
                    sha256=digest,
                    path=str(file_path),
                    chars=len(payload_json),
                )
            except Exception as e:
                logger.warning(
                    "ollama_payload_save_failed",
                    label=label,
                    model=model,
                    chat_id=chat_id,
                    error=str(e),
                )

        print(f"[FUNC] Ollama {model} - offering {len(ollama_tools)} core tools (filtered from {len(ALL_FUNCTIONS)} total)")

        import time as _time
        _t0 = _time.time()

        try:
            # Initial API call with tools
            payload = {
                "model": model,
                "messages": messages,
                "tools": ollama_tools,
                "options": {"temperature": ollama_temperature, "num_ctx": 8192},
                "stream": False,
            }
            _debug_write_payload("tool_select", payload)

            # Debug: log exact message content
            print(f"[DEBUG] Messages count: {len(messages)}")
            for i, m in enumerate(messages):
                role = m.get('role', 'unknown')
                content = str(m.get('content', ''))[:100]
                print(f"[DEBUG] Message {i}: role={role}, content={content}...")

            resp = self.ollama_client.chat(**payload)

            _t1 = _time.time()
            _prompt_tokens = resp.get("prompt_eval_count", 0)
            _gen_tokens = resp.get("eval_count", 0)
            print(f"[TIMING] Ollama tool selection: {(_t1-_t0)*1000:.0f}ms ({_prompt_tokens} prompt tok, {_gen_tokens} gen tok)")

            response_message = resp.get("message", {})
            tool_calls = response_message.get("tool_calls", [])
            tool_calls_debug = []

            # Track token usage
            in_tok = resp.get("prompt_eval_count", 0)
            out_tok = resp.get("eval_count", 0)

            if tool_calls:
                # Log each tool call explicitly for benchmark detection
                for tc in tool_calls:
                    if hasattr(tc, 'function'):
                        tool_name = getattr(tc.function, 'name', 'unknown')
                    else:
                        tool_name = tc.get('function', {}).get('name', 'unknown')
                    print(f"[FUNC] Ollama tool_call: {tool_name}")
                print(f"[FUNC] Ollama requested {len(tool_calls)} tool call(s)")

                # Convert Ollama ToolCall objects to dictionaries for processing
                # The Ollama Python client returns ToolCall objects, not dicts
                # We need two versions:
                # - tool_calls_for_ollama: dict args (for appending to Ollama messages)
                # - tool_calls_for_service: JSON string args (for tool_calling_service)
                tool_calls_for_ollama = []
                tool_calls_for_service = []

                for tc in tool_calls:
                    if hasattr(tc, 'function'):
                        # It's a ToolCall object - convert to dict
                        func = tc.function
                        args = getattr(func, 'arguments', {})
                        args_dict = args if isinstance(args, dict) else json.loads(args or "{}")
                        args_str = json.dumps(args_dict)
                        call_id = getattr(tc, 'id', None) or f"call_{uuid.uuid4().hex[:8]}"
                        func_name = getattr(func, 'name', '')

                        tool_calls_for_ollama.append({
                            "id": call_id,
                            "type": "function",
                            "function": {"name": func_name, "arguments": args_dict}
                        })
                        tool_calls_for_service.append({
                            "id": call_id,
                            "type": "function",
                            "function": {"name": func_name, "arguments": args_str}
                        })
                        tool_calls_debug.append({
                            "name": func_name,
                            "arguments": args_dict,
                        })
                    elif isinstance(tc, dict):
                        # Already a dict
                        if not tc.get("id"):
                            tc["id"] = f"call_{uuid.uuid4().hex[:8]}"
                        func_data = tc.get("function", {})
                        args = func_data.get("arguments", {})
                        args_dict = args if isinstance(args, dict) else json.loads(args or "{}")
                        args_str = json.dumps(args_dict) if isinstance(args, dict) else args
                        func_name = func_data.get("name", "")

                        tool_calls_for_ollama.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": func_name, "arguments": args_dict}
                        })
                        tool_calls_for_service.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": func_name, "arguments": args_str}
                        })
                        tool_calls_debug.append({
                            "name": func_name,
                            "arguments": args_dict,
                        })
                    else:
                        logger.warning(f"Unknown tool_call type: {type(tc)}")
                        continue

                # Process tool calls - use dict args for Ollama message
                messages.append({
                    "role": "assistant",
                    "content": response_message.get("content", ""),
                    "tool_calls": tool_calls_for_ollama
                })

                # Use JSON string args for the service
                _t2 = _time.time()
                tool_result_messages = self.tool_service.execute_tool_calls_batch(
                    tool_calls=tool_calls_for_service,
                    model=model,
                    chat_id=chat_id,
                    chat_loader_fn=load_chat,
                    chat_saver_fn=save_chat,
                )
                _t3 = _time.time()
                print(f"[TIMING] Tool execution: {(_t3-_t2)*1000:.0f}ms")

                # Check if ALL tool calls were smart home tools
                # If so, we can return the pre-formatted results directly (single-call optimization)
                called_function_names = {
                    tc.get("function", {}).get("name", "")
                    for tc in tool_calls_for_service
                }
                all_smarthome = called_function_names.issubset(SMARTHOME_FUNCTION_NAMES)
                all_todo = called_function_names.issubset(TODO_FUNCTION_NAMES)

                if (all_smarthome or all_todo) and tool_result_messages:
                    # SINGLE-CALL PATH: Return smart home results directly
                    # These are already well-formatted (e.g., "🌡️ Thermostat Status:\n• Current: 72°F")
                    print(f"[TIMING] Single-call optimization: returning smart home results directly")

                    # Extract formatted messages from tool results
                    # Content is JSON string like '{"success": true, "message": "🌡️ Status..."}'
                    formatted_parts = []
                    for msg in tool_result_messages:
                        content = msg.get("content", "")
                        try:
                            result_dict = json.loads(content)
                            # Extract the human-readable message
                            if isinstance(result_dict, dict) and "message" in result_dict:
                                formatted_parts.append(result_dict["message"])
                            else:
                                formatted_parts.append(str(result_dict))
                        except (json.JSONDecodeError, TypeError):
                            formatted_parts.append(content)

                    combined_results = "\n\n".join(formatted_parts)
                    print(f"[TIMING] TOTAL: {(_t3-_t0)*1000:.0f}ms (single-call)")
                    text = combined_results
                else:
                    # TWO-CALL PATH: Need LLM to interpret vault results
                    # Convert tool result messages to Ollama format
                    for msg in tool_result_messages:
                        messages.append({
                            "role": "tool",
                            "content": msg.get("content", "")
                        })

                    # Get final response after tool execution
                    second_payload = {
                        "model": model,
                        "messages": messages,
                        "tools": ollama_tools,
                        "options": {"temperature": ollama_temperature, "num_ctx": 8192},
                        "stream": False,
                    }
                    _debug_write_payload("final", second_payload)
                    second_resp = self.ollama_client.chat(**second_payload)
                    _t4 = _time.time()
                    _prompt_tokens2 = second_resp.get("prompt_eval_count", 0) if isinstance(second_resp, dict) else 0
                    _gen_tokens2 = second_resp.get("eval_count", 0) if isinstance(second_resp, dict) else 0
                    print(f"[TIMING] Ollama final response: {(_t4-_t3)*1000:.0f}ms ({_prompt_tokens2} prompt tok, {_gen_tokens2} gen tok)")
                    print(f"[TIMING] TOTAL: {(_t4-_t0)*1000:.0f}ms")

                    # Extract response - handle both dict and object responses
                    if isinstance(second_resp, dict):
                        second_message = second_resp.get("message", {})
                        if isinstance(second_message, dict):
                            text = second_message.get("content", "")
                        else:
                            text = getattr(second_message, 'content', "")
                    else:
                        # It's an object
                        second_message = getattr(second_resp, 'message', None)
                        text = getattr(second_message, 'content', "") if second_message else ""

                    if isinstance(second_resp, dict):
                        in_tok += second_resp.get("prompt_eval_count", 0)
                        out_tok += second_resp.get("eval_count", 0)
                    else:
                        in_tok += getattr(second_resp, "prompt_eval_count", 0) or 0
                        out_tok += getattr(second_resp, "eval_count", 0) or 0

            else:
                # No tool calls - return response directly
                print(f"[FUNC] Ollama chose NOT to call any function")
                text = response_message.get("content", "")
                tool_calls_debug = []

            return {
                "text": text,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "tool_calls": tool_calls_debug,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "ollama_tools_chat_error",
                model=model,
                error=error_msg,
                exc_info=True,
            )
            # Provide helpful error message
            if "does not support tools" in error_msg.lower():
                raise RuntimeError(
                    f"Model '{model}' does not support native tool calling. "
                    "Try using qwen2.5:7b, qwen2.5:14b, or llama3.2:3b instead."
                )
            raise RuntimeError(f"Ollama tools error: {error_msg}")

    def _complete_ollama_mcp(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        chat_mode: str = "agentic"
    ) -> Dict:
        """
        Handle Ollama with MCP filesystem support.

        Args:
            model: Ollama model name
            messages: Conversation messages
            temperature: Sampling temperature
            chat_mode: Chat mode ('agentic' or 'chat')

        Returns:
            {"text": str, "input_tokens": int, "output_tokens": int}
        """
        # In chat mode, skip MCP and use plain Ollama
        if chat_mode == "chat":
            logger.info("Chat mode: skipping MCP, using plain Ollama")
            return self._complete_ollama(model, messages, temperature, chat_mode)
        from providers.ollama_mcp_provider import chat_with_mcp

        # Preprocess messages: convert any multimodal content to plain text
        # Ollama expects string content, not dict
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, dict) and content.get("_multimodal"):
                text = content.get("text", "")
                image_name = content.get("image_name", "attached image")
                msg["content"] = f"{text}\n[Image attached: {image_name}]"

        logger.info(f"Using MCP provider for model: {model}")

        try:
            response_text = chat_with_mcp(
                model=model,
                messages=messages,
                temperature=temperature,
                vault_path=str(self.settings.vault_path),
            )

            text = response_text or ""
            # Estimate token usage for local models
            in_tok = sum(len(m.get("content", "")) // 4 for m in messages)
            out_tok = len(text) // 4

            return {
                "text": text,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "ollama_mcp_chat_error",
                model=model,
                error=error_msg,
                exc_info=True,
            )
            raise RuntimeError(f"MCP Ollama error: {error_msg}")

    def _complete_ollama(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        chat_mode: str = "agentic"
    ) -> Dict:
        """
        Handle Ollama for local models.

        Args:
            model: Ollama model name
            messages: Conversation messages
            temperature: Sampling temperature
            chat_mode: Chat mode ('agentic' or 'chat') - no special handling needed

        Returns:
            {"text": str, "input_tokens": int, "output_tokens": int}
        """
        try:
            # Preprocess messages: convert any multimodal content to plain text
            # Ollama expects string content, not dict
            for msg in messages:
                content = msg.get("content")
                if isinstance(content, dict) and content.get("_multimodal"):
                    # Extract text and image info from multimodal content
                    text = content.get("text", "")
                    image_name = content.get("image_name", "attached image")
                    msg["content"] = f"{text}\n[Image attached: {image_name}]"

            # Check if model is currently loaded for better error messages
            try:
                ps_result = subprocess.run(
                    ["ollama", "ps"], capture_output=True, text=True, timeout=2
                )
                model_loaded = (
                    model in ps_result.stdout if ps_result.returncode == 0 else False
                )
            except:
                model_loaded = False

            # Make the chat request with appropriate timeout
            # Longer timeout for cold models, shorter for hot models
            timeout = 60 if not model_loaded else 30

            resp = self.ollama_client.chat(
                model=model, messages=messages, options={"temperature": temperature}
            )
            text = resp["message"]["content"] or ""
            # For local models, we'll estimate token usage
            in_tok = sum(len(m.get("content", "")) // 4 for m in messages)
            out_tok = len(text) // 4

            return {
                "text": text,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "ollama_chat_error",
                model=model,
                error=error_msg,
                exc_info=True,
            )
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                if not model_loaded:
                    error_msg = f"Model '{model}' is loading for the first time. This can take 30-60 seconds. Please try again."
                else:
                    error_msg = f"Model '{model}' request timed out. It may be overloaded."
            raise RuntimeError(f"Ollama error: {error_msg}")

    def _complete_anthropic(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        write_intent: bool,
        read_intent: bool,
        chat_id: Optional[str],
        chat_mode: str = "agentic"
    ) -> Dict:
        """
        Handle Anthropic/Claude models with tool calling support.

        Args:
            model: Claude model name
            messages: Conversation messages
            temperature: Sampling temperature
            write_intent: Whether user intent indicates write operation
            read_intent: Whether user intent indicates read/search operation
            chat_id: Optional chat ID for context updates
            chat_mode: Chat mode ('agentic' or 'chat')

        Returns:
            {"text": str, "input_tokens": int, "output_tokens": int}
        """
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError(
                "Anthropic package not installed. Run: pip install anthropic>=0.39.0"
            )

        api_key = self.settings.anthropic_api_key
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Please add it to your .env file."
            )

        client = Anthropic(api_key=api_key)

        # In chat mode, skip vault guidance and tools entirely
        if chat_mode == "chat":
            logger.info("Chat mode: skipping vault guidance and tools for Anthropic")
            vault_guidance_text = ""
        else:
            # Build system prompt with vault guidance
            user_tz_str = self.settings.timezone or "US/Eastern"
            try:
                user_tz = pytz.timezone(user_tz_str)
                current_time_tz = datetime.datetime.now(user_tz)
                current_date = current_time_tz.strftime("%Y-%m-%d")
                current_time = current_time_tz.strftime("%H:%M:%S %Z")
                tomorrow_date = (current_time_tz + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception as e:
                current_time_tz = datetime.datetime.utcnow()
                current_date = current_time_tz.strftime("%Y-%m-%d")
                current_time = current_time_tz.strftime("%H:%M:%S UTC")
                tomorrow_date = (current_time_tz + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

            # Check agent mode for system prompt selection
            vault_guidance_text = ""
            if self.is_autonomous_mode():
                autonomous_prompt = self.get_system_prompt_for_mode(current_date, current_time, user_tz_str)
                vault_guidance_text = autonomous_prompt.get("content", "") if autonomous_prompt else ""
            elif self.settings.enable_enhanced_vault_guidance:
                vault_guidance_text = f"""CURRENT TIME CONTEXT:
- Today's date: {current_date}
- Current time: {current_time}
- Timezone: {user_tz_str}
- Tomorrow's date: {tomorrow_date}

🔀 FUNCTION ROUTING:

MICROSOFT TODO (task list management):
- "add to my todo list", "task list", "remind me to X", "I need to X"
  → create_todo_task(title="X")
- "what's on my todo list", "show my tasks", "my task list"
  → get_todo_tasks()
- "mark X complete", "done with X"
  → mark_todo_complete(task_id="...")
- "sync tasks to obsidian"
  → sync_todo_to_obsidian()

OBSIDIAN VAULT:

1. Quick daily captures → append_to_daily_note
   - "Add to today", "quick note", "remember this", "capture X"
   - Short tasks, ideas, reminders

2. Standalone notes → create_simple_note
   - Meeting notes, documentation, reference material
   - Use get_vault_structure to discover available folders

3. Structured notes → create_from_template
   - Meeting notes, weekly reviews, project briefs
   - Use list_templates to see available templates

CRITICAL - Listing vs Searching:
- User asks "What's in [folder]?" → use list_folder_contents(folder_name)
- User asks "Find notes about X" → use search_vault(query)
- Use get_vault_structure first to discover available folders

CRITICAL - Search Term Extraction:
When using search_vault, extract MAIN KEYWORD:
- "Find notes about meetings" → search_vault(query="meeting")

CRITICAL - Template Variables:
When using create_from_template, extract info as 'variables':
  destination: folder from get_vault_structure
  variables: (include title, attendees, date keys as needed)

Date parsing:
- "today" = {current_date} (use append_to_daily_note)
- "tomorrow" = {tomorrow_date}
- When user gives relative dates, calculate from today's date: {current_date}

Folder discovery:
- Use get_vault_structure to see all available folders
- Let user decide where to save notes based on their folder organization
- Daily captures → append_to_daily_note (auto-managed)

Be proactive: Execute vault operations immediately.

RESPONSE STYLE:
If a tool call is required, return only the tool call(s) with no user-facing text.
After tool results arrive, respond with the answer directly.
Never narrate intent ("I'll check...", "Let me search...") - just act, then report results.

⚠️ CRITICAL - VERIFICATION AND ERROR HANDLING:

1. **Always Check Operation Success:**
   - Every vault operation returns 'success' and 'verification' fields
   - If success=False OR verification.status="failed", the operation FAILED
   - Never claim success when these indicate failure

2. **Verification Results Mean:**
   - verified="passed" → Operation confirmed successful, safe to report
   - verified="failed" → Operation FAILED verification - treat as complete failure
   - When verification fails, tell user the operation FAILED and why

3. **Correct Response Examples:**
   ✅ "I tried to create the note, but verification failed. Error: [specific error]. Let me try a different approach."
   ❌ "I've created the note for you!" (when verified=False)

4. **When Operations Fail:**
   - Be honest: "The operation failed" + explain error
   - Suggest alternatives or ask user to check vault manually
   - Never say "the file should be there" when verification failed

5. **Never Ignore Errors:**
   - Don't make up success when verification fails
   - Don't claim operations worked when success=False
   - User trust depends on accurate reporting"""

        # Extract system messages and build combined system prompt
        system_messages = [
            m.get("content", "") for m in messages if m.get("role") == "system"
        ]
        if vault_guidance_text:
            system_messages.append(vault_guidance_text)
        combined_system = "\n\n".join(system_messages)

        # Filter out system messages from conversation (Claude handles them separately)
        # Also clean messages to only include role and content
        # Handle multimodal content (images) for vision models
        conversation_messages = []
        for m in messages:
            if m.get("role") != "system":
                content = m.get("content", "")
                # Handle multimodal content for vision
                if isinstance(content, dict) and content.get("_multimodal"):
                    # Build Anthropic vision content array
                    anthropic_content = [
                        {"type": "text", "text": content.get("text", "")},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": content.get("image_type", "image/png"),
                                "data": content.get("image_base64", "")
                            }
                        }
                    ]
                    conversation_messages.append({"role": m.get("role"), "content": anthropic_content})
                else:
                    conversation_messages.append({"role": m.get("role"), "content": content})

        # Ensure we have at least one user message (Claude requirement)
        if not conversation_messages:
            conversation_messages = [{"role": "user", "content": "Hello"}]

        # Ensure first message is from user (Claude requirement)
        if conversation_messages[0].get("role") != "user":
            conversation_messages.insert(0, {"role": "user", "content": "..."})

        print(f"[FUNC] Claude model {model} - {len(conversation_messages)} messages (mode: {chat_mode})")

        # Select tools based on mode
        if chat_mode == "chat":
            anthropic_tools = []
            print(f"[FUNC] Claude model {model} - chat mode, no tools")
        elif self.is_autonomous_mode():
            anthropic_tools = self.get_tools_for_mode('anthropic')
            print(f"[FUNC] Claude model {model} - AUTONOMOUS MODE - offering {len(anthropic_tools)} general tools")
        else:
            anthropic_tools = []
            for func in ALL_FUNCTIONS:
                anthropic_tools.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    }
                )
            print(f"[FUNC] Claude model {model} - offering {len(anthropic_tools)} tools (incl. {len(SMARTHOME_FUNCTIONS)} smart home)")

        # Initial API call with tools
        try:
            print(f"[FUNC] Calling Claude API with model: {model}")
            anthropic_write_retry_used = False
            anthropic_read_retry_used = False
            while True:
                resp = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=combined_system,
                    messages=conversation_messages,
                    temperature=temperature,
                    tools=anthropic_tools,
                )
                print(f"[FUNC] Claude API call successful")

                if (
                    self.settings.require_tool_for_writes
                    and write_intent
                    and resp.stop_reason != "tool_use"
                    and not anthropic_write_retry_used
                ):
                    print("[GUARD] Forcing tool call retry due to write intent without tool usage (Claude).")
                    system_messages.append(WRITE_TOOL_REMINDER)
                    combined_system = "\n\n".join(system_messages)
                    anthropic_write_retry_used = True
                    continue

                if (
                    self.settings.require_tool_for_reads
                    and read_intent
                    and resp.stop_reason != "tool_use"
                    and not anthropic_read_retry_used
                ):
                    print("[GUARD] Forcing tool call retry due to read intent without tool usage (Claude).")
                    system_messages.append(READ_TOOL_REMINDER)
                    combined_system = "\n\n".join(system_messages)
                    anthropic_read_retry_used = True
                    continue

                break

            # Check if Claude wants to use a tool
            if resp.stop_reason == "tool_use":
                # Find the tool use block
                tool_use_block = None
                for block in resp.content:
                    if block.type == "tool_use":
                        tool_use_block = block
                        break

                if tool_use_block:
                    print(f"[FUNC] Claude requested tool: {tool_use_block.name}")

                    # Use ToolCallingService for centralized tool execution
                    function_result, tool_use_id = self.tool_service.execute_anthropic_tool(
                        tool_use_block=tool_use_block,
                        model=model,
                        chat_id=chat_id,
                        chat_loader_fn=load_chat,
                        chat_saver_fn=save_chat,
                    )

                    # Add assistant's tool use to conversation, stripping any preamble text
                    tool_use_content = [
                        block for block in resp.content
                        if getattr(block, "type", None) == "tool_use"
                    ]
                    conversation_messages.append(
                        {"role": "assistant", "content": tool_use_content}
                    )

                    # Add tool result using service helper
                    tool_result_message = self.tool_service.format_tool_result_for_anthropic(
                        tool_use_id=tool_use_id,
                        result=function_result,
                    )
                    conversation_messages.append(tool_result_message)

                    # Post-tool response clamp: instruct model to respond with answer only
                    post_tool_system = combined_system + "\n\nTools have executed. Respond with the answer only. Do not mention tool calls, file reads, or include JSON."

                    # Get final response from Claude
                    second_resp = client.messages.create(
                        model=model,
                        max_tokens=4096,
                        system=post_tool_system,
                        messages=conversation_messages,
                        temperature=temperature,
                        tools=anthropic_tools,
                    )

                    # Extract text from content blocks
                    text_blocks = [
                        block.text
                        for block in second_resp.content
                        if hasattr(block, "text")
                    ]
                    text = "\n".join(text_blocks)

                    # Strip JSON echo from beginning of response
                    text = self._strip_json_prefix(text)

                    # Combine token usage
                    in_tok = resp.usage.input_tokens + second_resp.usage.input_tokens
                    out_tok = resp.usage.output_tokens + second_resp.usage.output_tokens
                else:
                    # No tool use block found, treat as normal
                    text_blocks = [
                        block.text for block in resp.content if hasattr(block, "text")
                    ]
                    text = "\n".join(text_blocks)
                    in_tok = resp.usage.input_tokens
                    out_tok = resp.usage.output_tokens
            else:
                # Normal response without tool use
                print(f"[FUNC] Claude chose NOT to use any tools")
                text_blocks = [
                    block.text for block in resp.content if hasattr(block, "text")
                ]
                text = "\n".join(text_blocks)
                in_tok = resp.usage.input_tokens
                out_tok = resp.usage.output_tokens

            return {
                "text": text,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            }

        except Exception as e:
            logger.error(
                "anthropic_chat_error",
                model=model,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Claude error: {str(e)}")

    def _complete_openai(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        write_intent: bool,
        read_intent: bool,
        chat_id: Optional[str],
        chat_mode: str = "agentic"
    ) -> Dict:
        """
        Handle OpenAI models with function calling support.

        Args:
            model: OpenAI model name
            messages: Conversation messages
            temperature: Sampling temperature
            write_intent: Whether user intent indicates write operation
            read_intent: Whether user intent indicates read/search operation
            chat_id: Optional chat ID for context updates
            chat_mode: Chat mode ('agentic' or 'chat')

        Returns:
            {"text": str, "input_tokens": int, "output_tokens": int}
        """
        api_key = self.settings.openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        client = OpenAI(api_key=api_key)

        # In chat mode, skip vault guidance and tools entirely
        if chat_mode == "chat":
            logger.info("Chat mode: skipping vault guidance and tools for OpenAI")
            vault_guidance = None
        else:
            # Get current time in user's timezone for accurate date calculations
            user_tz_str = self.settings.timezone or "US/Eastern"
            try:
                user_tz = pytz.timezone(user_tz_str)
                current_time_tz = datetime.datetime.now(user_tz)
                current_date = current_time_tz.strftime("%Y-%m-%d")
                current_time = current_time_tz.strftime("%H:%M:%S %Z")
                tomorrow_date = (current_time_tz + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception as e:
                current_time_tz = datetime.datetime.utcnow()
                current_date = current_time_tz.strftime("%Y-%m-%d")
                current_time = current_time_tz.strftime("%H:%M:%S UTC")
                tomorrow_date = (current_time_tz + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

            # Check agent mode for system prompt selection
            if self.is_autonomous_mode():
                vault_guidance = self.get_system_prompt_for_mode(current_date, current_time, user_tz_str)
            elif self.settings.enable_enhanced_vault_guidance:
                vault_guidance = {
                    "role": "system",
                    "content": f"""CURRENT TIME CONTEXT:
- Today's date: {current_date}
- Current time: {current_time}
- Timezone: {user_tz_str}
- Tomorrow's date: {tomorrow_date}

🔀 FUNCTION ROUTING:

MICROSOFT TODO (task list management):
- "add to my todo list", "task list", "remind me to X", "I need to X"
  → create_todo_task(title="X")
- "what's on my todo list", "show my tasks", "my task list"
  → get_todo_tasks()
- "mark X complete", "done with X"
  → mark_todo_complete(task_id="...")
- "sync tasks to obsidian"
  → sync_todo_to_obsidian()

OBSIDIAN VAULT:

1. Quick daily captures → append_to_daily_note
   - "Add to today", "quick note", "remember this", "capture X"
   - Short tasks, ideas, reminders

2. Standalone notes → create_simple_note
   - Meeting notes, documentation, reference material
   - Use get_vault_structure to discover available folders

3. Structured notes → create_from_template
   - Meeting notes, weekly reviews, project briefs
   - Use list_templates to see available templates

CRITICAL - Listing vs Searching:
- User asks "What's in [folder]?" → use list_folder_contents(folder_name)
- User asks "Find notes about X" → use search_vault(query)
- Use get_vault_structure first to discover available folders

CRITICAL - Search Term Extraction:
When using search_vault, extract MAIN KEYWORD:
- "Find notes about meetings" → search_vault(query="meeting")

CRITICAL - Template Variables:
When using create_from_template, extract info as 'variables':
  destination: folder from get_vault_structure
  variables: (include title, attendees, date keys as needed)

Date parsing:
- "today" = {current_date} (use append_to_daily_note)
- "tomorrow" = {tomorrow_date}
- When user gives relative dates, calculate from today's date: {current_date}

Folder discovery:
- Use get_vault_structure to see all available folders
- Let user decide where to save notes based on their folder organization
- Daily captures → append_to_daily_note (auto-managed)

Be proactive: Execute vault operations immediately.

RESPONSE STYLE:
If a tool call is required, return only the tool call(s) with no user-facing text.
After tool results arrive, respond with the answer directly.
Never narrate intent ("I'll check...", "Let me search...") - just act, then report results.

⚠️ CRITICAL - VERIFICATION AND ERROR HANDLING:

1. **Always Check Operation Success:**
   - Every vault operation returns 'success' and 'verification' fields
   - If success=False OR verification.status="failed", the operation FAILED
   - Never claim success when these indicate failure

2. **Verification Results Mean:**
   - verified="passed" → Operation confirmed successful, safe to report
   - verified="failed" → Operation FAILED verification - treat as complete failure
   - When verification fails, tell user the operation FAILED and why

3. **Correct Response Examples:**
   ✅ "I tried to create the note, but verification failed. Error: [specific error]. Let me try a different approach."
   ❌ "I've created the note for you!" (when verified=False)

4. **When Operations Fail:**
   - Be honest: "The operation failed" + explain error
   - Suggest alternatives or ask user to check vault manually
   - Never say "the file should be there" when verification failed

5. **Never Ignore Errors:**
   - Don't make up success when verification fails
   - Don't claim operations worked when success=False
   - User trust depends on accurate reporting""",
            }

        if vault_guidance:
            # Insert guidance before user messages (after any existing system messages)
            system_msg_count = sum(1 for m in messages if m.get("role") == "system")
            messages.insert(system_msg_count, vault_guidance)

        # Convert multimodal content to OpenAI format for vision models
        for i, m in enumerate(messages):
            content = m.get("content", "")
            if isinstance(content, dict) and content.get("_multimodal"):
                # Build OpenAI vision content array
                openai_content = [
                    {"type": "text", "text": content.get("text", "")},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{content.get('image_type', 'image/png')};base64,{content.get('image_base64', '')}",
                            "detail": "auto"
                        }
                    }
                ]
                messages[i] = {"role": m.get("role"), "content": openai_content}

        # Check if model supports function calling (reasoning models like gpt-5 don't)
        # Also skip tools in chat mode
        reasoning_models = {"gpt-5"}
        is_reasoning_model = (model in reasoning_models) or model.startswith("o1")
        skip_tools = is_reasoning_model or chat_mode == "chat"

        write_retry_used = False
        read_retry_used = False
        while True:
            # Initial API call with tool definitions (skip for reasoning models and chat mode)
            if skip_tools:
                reason = "reasoning model" if is_reasoning_model else "chat mode"
                print(
                    f"[FUNC] Model {model} - {reason} - skipping function calling"
                )
                resp = client.chat.completions.create(
                    model=model, messages=messages, temperature=temperature
                )
            else:
                # Select tools based on agent mode
                if self.is_autonomous_mode():
                    tools_payload = self.get_tools_for_mode('openai')
                    print(f"[FUNC] Model {model} - AUTONOMOUS MODE - offering {len(tools_payload)} general tools")
                else:
                    tools_payload = [
                        {"type": "function", "function": fn_def}
                        for fn_def in ALL_FUNCTIONS
                    ]
                    print(f"[FUNC] Model {model} supports functions - offering {len(tools_payload)} tools (incl. {len(SMARTHOME_FUNCTIONS)} smart home)")
                tool_choice_value = "required" if (write_intent or read_intent) else "auto"
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    tools=tools_payload,
                    tool_choice=tool_choice_value,
                )

            response_message = resp.choices[0].message
            print(f"[DEBUG] OpenAI response - content: {(response_message.content or '')[:100]!r}, has_tool_calls: {bool(getattr(response_message, 'tool_calls', None))}")

            tool_calls_data = []
            if not skip_tools:
                if getattr(response_message, "tool_calls", None):
                    tool_calls_data = [
                        tc.model_dump() for tc in response_message.tool_calls
                    ]
                    print(f"[DEBUG] Extracted {len(tool_calls_data)} tool calls")
                elif getattr(response_message, "function_call", None):
                    fc = response_message.function_call
                    tool_calls_data = [
                        {
                            "id": f"call_{uuid.uuid4().hex}",
                            "type": "function",
                            "function": {
                                "name": fc.name,
                                "arguments": fc.arguments or "{}",
                            },
                        }
                    ]

            if (
                self.settings.require_tool_for_writes
                and write_intent
                and not is_reasoning_model
                and not tool_calls_data
                and not write_retry_used
            ):
                print("[GUARD] Forcing tool call retry due to write intent without tool usage (OpenAI).")
                from routes.chat_routes import insert_write_tool_reminder
                insert_write_tool_reminder(messages)
                write_retry_used = True
                continue

            if (
                self.settings.require_tool_for_reads
                and read_intent
                and not is_reasoning_model
                and not tool_calls_data
                and not read_retry_used
            ):
                print("[GUARD] Forcing tool call retry due to read intent without tool usage (OpenAI).")
                from routes.chat_routes import insert_read_tool_reminder
                insert_read_tool_reminder(messages)
                read_retry_used = True
                continue

            # Fallback: parse pseudo tool call from content if intent requires tools but none returned
            if (
                (write_intent or read_intent)
                and not tool_calls_data
                and response_message.content
            ):
                pseudo_tool = self._parse_pseudo_tool_call(response_message.content)
                if pseudo_tool:
                    tool_calls_data = [{
                        "id": f"call_{uuid.uuid4().hex}",
                        "type": "function",
                        "function": pseudo_tool,
                    }]
                    print(f"[FALLBACK] Created synthetic tool call from pseudo tool in content")

            break

        if tool_calls_data:
            print(
                f"[FUNC] AI requested {len(tool_calls_data)} tool call(s)"
            )
        else:
            print(f"[FUNC] AI chose NOT to call any function")

        if tool_calls_data:
            assistant_message = {
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls_data,
            }
            messages.append(assistant_message)

            # Use ToolCallingService for centralized tool execution
            # Ensure all tool calls have IDs
            for tool_call in tool_calls_data:
                if not tool_call.get("id"):
                    tool_call["id"] = f"call_{uuid.uuid4().hex}"

            tool_result_messages = self.tool_service.execute_tool_calls_batch(
                tool_calls=tool_calls_data,
                model=model,
                chat_id=chat_id,
                chat_loader_fn=load_chat,
                chat_saver_fn=save_chat,
            )
            messages.extend(tool_result_messages)

            # Post-tool response clamp: instruct model to respond with answer only
            post_tool_guidance = {
                "role": "system",
                "content": "Tools have executed. Respond with the answer only. Do not mention tool calls, file reads, or include JSON."
            }
            messages.append(post_tool_guidance)

            second_resp = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature
            )
            text = second_resp.choices[0].message.content or ""
            print(f"[DEBUG] Second response (post-tool) raw: {text[:150]!r}")

            # Strip JSON echo from beginning of response (model sometimes echoes tool params/results)
            text = self._strip_json_prefix(text)
            print(f"[DEBUG] Second response (post-tool) cleaned: {text[:150]!r}")

            # Combine token usage from both calls
            usage1 = getattr(resp, "usage", None)
            usage2 = getattr(second_resp, "usage", None)
            in_tok1, out_tok1 = self.robust_usage(usage1)
            in_tok2, out_tok2 = self.robust_usage(usage2)
            in_tok = in_tok1 + in_tok2
            out_tok = out_tok1 + out_tok2

        else:
            # Normal response without tool call
            text = response_message.content or ""
            print(f"[DEBUG] No tool calls - returning first response: {text[:150]!r}")
            usage = getattr(resp, "usage", None)
            in_tok, out_tok = self.robust_usage(usage)

        return {
            "text": text,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
        }
