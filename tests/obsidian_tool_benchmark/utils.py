"""
Utility functions for Tool Calling Benchmark

Provides Ollama API helpers and tool schema conversion.
"""

import json
import os
import time
import hashlib
from pathlib import Path
import requests
from typing import Any, Dict, List, Optional, Tuple

from obsidian_functions import OBSIDIAN_FUNCTIONS
try:
    from smarthome_functions import SMARTHOME_FUNCTIONS
except ImportError:
    SMARTHOME_FUNCTIONS = []

from ollama_tooling import build_ollama_tools, LOCAL_MODEL_CORE_TOOLS, LOCAL_MODEL_TOOL_ORDER


# Default Ollama URL
OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Default models to test
DEFAULT_MODELS = [
    "qwen3:4b-instruct-2507-q4_K_M",  # Fastest, 64 t/s
    "qwen3:8b",                        # Best speed/accuracy
    "qwen3:14b",                       # Near GPT-4 accuracy
]

PAYLOAD_DEBUG_DIR = os.getenv("OLLAMA_PAYLOAD_DEBUG_DIR")


def _write_payload_debug(payload: Dict, label: str) -> None:
    """Write canonical Ollama request payloads for diffing with web app."""
    if not PAYLOAD_DEBUG_DIR:
        return
    try:
        debug_path = Path(PAYLOAD_DEBUG_DIR)
        debug_path.mkdir(parents=True, exist_ok=True)
        payload_json = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        filename = f"ollama_payload_benchmark_{label}_{int(time.time() * 1000)}_{digest[:8]}.json"
        file_path = debug_path / filename
        file_path.write_text(payload_json + "\n", encoding="utf-8")
        print(f"[DEBUG] wrote payload {label} sha256={digest} path={file_path}")
    except Exception as exc:
        print(f"[DEBUG] payload write failed: {exc}")


def get_obsidian_tool_schemas() -> List[Dict]:
    """
    Get Obsidian tool schemas in Ollama format.

    Returns tool definitions for the 10 LOCAL_MODEL_CORE_TOOLS
    that are relevant for vault operations.
    """
    return build_ollama_tools(
        OBSIDIAN_FUNCTIONS,
        tool_names=LOCAL_MODEL_CORE_TOOLS,
        tool_order=LOCAL_MODEL_TOOL_ORDER,
    )


def get_smart_home_tool_schemas() -> List[Dict]:
    """
    Get smart home tool schemas in Ollama format.

    Returns the 6 smart home tools used in production.
    """
    return build_ollama_tools(
        SMARTHOME_FUNCTIONS,
        tool_names=LOCAL_MODEL_CORE_TOOLS,
        tool_order=LOCAL_MODEL_TOOL_ORDER,
    )


def get_all_tool_schemas() -> List[Dict]:
    """Get all 16 tools (10 Obsidian + 6 smart home) in Ollama format."""
    return build_ollama_tools(
        OBSIDIAN_FUNCTIONS + SMARTHOME_FUNCTIONS,
        tool_names=LOCAL_MODEL_CORE_TOOLS,
        tool_order=LOCAL_MODEL_TOOL_ORDER,
    )


def check_ollama_available(url: str = OLLAMA_URL) -> bool:
    """Check if Ollama is accessible"""
    try:
        resp = requests.get(f"{url}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def list_available_models(url: str = OLLAMA_URL) -> List[str]:
    """Get list of available models from Ollama"""
    try:
        resp = requests.get(f"{url}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        print(f"Error listing models: {e}")
        return []


def warmup_model(model: str, url: str = OLLAMA_URL) -> bool:
    """
    Warm up a model by sending a simple request.

    This ensures the model is loaded into VRAM before benchmarking.
    """
    print(f"  Warming up {model}...")
    try:
        resp = requests.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": "Hello",
                "stream": False,
                "options": {"num_predict": 5}
            },
            timeout=120
        )
        resp.raise_for_status()
        print(f"  {model} ready")
        return True
    except Exception as e:
        print(f"  Warning: warmup failed for {model}: {e}")
        return False


def call_ollama_chat(
    model: str,
    prompt: str,
    tools: List[Dict],
    url: str = OLLAMA_URL,
    timeout: int = 120,
    temperature: float = 0.1
) -> Tuple[Dict, float]:
    """
    Call Ollama chat API with tools.

    Args:
        model: Model name
        prompt: User prompt
        tools: List of tool definitions
        url: Ollama URL
        timeout: Request timeout in seconds
        temperature: Sampling temperature (low for consistency)

    Returns:
        (response_dict, latency_ms) tuple
    """
    messages = [{"role": "user", "content": prompt}]

    start_time = time.time()

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "options": {"temperature": temperature, "num_ctx": 8192},
        "stream": False,
    }
    _write_payload_debug(payload, "direct")

    resp = requests.post(
        f"{url}/api/chat",
        json=payload,
        timeout=timeout
    )

    latency_ms = (time.time() - start_time) * 1000

    resp.raise_for_status()
    return resp.json(), latency_ms


def call_ollama_chat_with_prompt(
    model: str,
    prompt: str,
    tools: List[Dict],
    system_message: Optional[Dict] = None,
    url: str = OLLAMA_URL,
    timeout: int = 120,
    temperature: float = 0.1
) -> Tuple[Dict, float]:
    """
    Call Ollama chat API with tools and optional system prompt.

    This is the variant-aware version that supports A/B testing of
    different system prompt configurations.

    Args:
        model: Model name
        prompt: User prompt
        tools: List of tool definitions
        system_message: Optional system message dict with role/content
                       (pass None for no system prompt)
        url: Ollama URL
        timeout: Request timeout in seconds
        temperature: Sampling temperature (low for consistency)

    Returns:
        (response_dict, latency_ms) tuple
    """
    messages = []

    # Add system message if provided
    if system_message is not None:
        messages.append(system_message)

    # Add user prompt
    messages.append({"role": "user", "content": prompt})

    start_time = time.time()

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "options": {"temperature": temperature, "num_ctx": 8192},
        "stream": False,
    }
    _write_payload_debug(payload, "variant")

    resp = requests.post(
        f"{url}/api/chat",
        json=payload,
        timeout=timeout
    )

    latency_ms = (time.time() - start_time) * 1000

    resp.raise_for_status()
    return resp.json(), latency_ms


def parse_tool_call(response: Dict) -> Tuple[Optional[str], Dict]:
    """
    Parse tool call from Ollama response.

    Args:
        response: Ollama chat response dict

    Returns:
        (tool_name, params) tuple. Both are None/empty if no tool call.
    """
    message = response.get("message", {})
    tool_calls = message.get("tool_calls", [])

    if not tool_calls:
        return None, {}

    # Take first tool call
    tc = tool_calls[0]

    # Handle both dict and object-like structures
    if isinstance(tc, dict):
        func = tc.get("function", {})
        name = func.get("name")
        args = func.get("arguments", {})
    else:
        # Object with attributes
        func = getattr(tc, "function", None)
        if func:
            name = getattr(func, "name", None)
            args = getattr(func, "arguments", {})
        else:
            return None, {}

    # Parse args if they're a string
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}

    return name, args if isinstance(args, dict) else {}


def get_response_content(response: Dict) -> str:
    """Extract text content from Ollama response"""
    message = response.get("message", {})
    return message.get("content", "")


def get_token_counts(response: Dict) -> Tuple[int, int, int]:
    """
    Extract token counts from Ollama response.

    Returns:
        (prompt_tokens, completion_tokens, total_tokens)
    """
    prompt = response.get("prompt_eval_count", 0)
    completion = response.get("eval_count", 0)
    return prompt, completion, prompt + completion
