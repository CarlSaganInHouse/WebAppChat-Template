"""
Shared Ollama tool schema utilities.

This module centralizes:
- The core tool list for local Ollama models
- Tool ordering
- Conversion to Ollama tool payloads (with description truncation)
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set

MAX_OLLAMA_TOOL_DESC_LENGTH = 150

# Tool ordering matters for LLM tool selection - navigation tools first.
LOCAL_MODEL_TOOL_ORDER: List[str] = [
    # Vault navigation & reading
    "list_folder_contents", "get_vault_structure", "search_vault",
    "read_note", "read_daily_note", "find_and_read_note",
    # Vault writing
    "append_to_daily_note", "create_simple_note", "create_job_note", "get_today_tasks",
    # Microsoft To Do
    "create_todo_task", "get_todo_tasks", "mark_todo_complete",
    # Smart home
    "control_lights", "get_light_status", "control_thermostat",
    "get_thermostat_status", "control_plug", "get_plug_status",
]

# Core tools for local models (reduced set for better tool selection accuracy)
LOCAL_MODEL_CORE_TOOLS: Set[str] = set(LOCAL_MODEL_TOOL_ORDER)


def _truncate_description(desc: str, max_len: int) -> str:
    """Trim overly long descriptions while preserving the first sentence."""
    if not desc or max_len <= 0 or len(desc) <= max_len:
        return desc

    first_sentence_end = desc.find(". ")
    if 0 < first_sentence_end < max_len:
        return desc[:first_sentence_end + 1]

    trimmed = desc[:max_len].rsplit(" ", 1)[0]
    if not trimmed:
        trimmed = desc[:max_len]
    return trimmed + "..."


def build_ollama_tools(
    all_functions: Sequence[Dict],
    tool_names: Optional[Iterable[str]] = None,
    tool_order: Optional[Sequence[str]] = None,
    max_desc_length: int = MAX_OLLAMA_TOOL_DESC_LENGTH,
) -> List[Dict]:
    """
    Convert function definitions to Ollama tool schema format.

    Args:
        all_functions: Raw function definitions (name/description/parameters).
        tool_names: Optional whitelist of tool names to include.
        tool_order: Optional ordered list of tool names for stable ordering.
        max_desc_length: Max description length before truncation.

    Returns:
        List of Ollama tool schemas.
    """
    if tool_names is None:
        filtered = list(all_functions)
    else:
        tool_set = set(tool_names)
        filtered = [t for t in all_functions if t.get("name") in tool_set]

    if tool_order:
        order_map = {name: i for i, name in enumerate(tool_order)}
        filtered.sort(key=lambda t: order_map.get(t.get("name"), len(order_map)))

    ollama_tools: List[Dict] = []
    for func in filtered:
        desc = func.get("description", "")
        desc = _truncate_description(desc, max_desc_length)
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": func["name"],
                "description": desc,
                "parameters": func.get("parameters", {}),
            },
        })

    return ollama_tools
