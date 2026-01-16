"""
Conversation Context Awareness System

Tracks recent notes, folders, and operations within a chat session to enable
natural language references like "move that note" or "the folder we just opened".

This enables multi-step workflows without constant explicit reference naming.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime


def initialize_context() -> Dict[str, Any]:
    """
    Initialize an empty context for a new chat.

    Returns:
        Dict with empty context structures
    """
    return {
        "last_created_note": None,
        "last_modified_note": None,
        "last_accessed_folder": None,
        "recent_notes": [],  # List of note names/paths
        "recent_operations": [],  # List of {type, note, from, to, timestamp}
        "recent_folders": [],  # List of folder names accessed
    }


def update_context_from_tool(
    context: Dict[str, Any],
    tool_name: str,
    arguments: Dict[str, Any],
    success: bool = True
) -> Dict[str, Any]:
    """
    Update context memory based on tool execution.

    Args:
        context: Current context dict
        tool_name: Name of the tool that was executed
        arguments: Arguments passed to the tool
        success: Whether the tool executed successfully

    Returns:
        Updated context dict
    """
    if not success:
        return context

    # Ensure context has all fields
    context.setdefault("last_created_note", None)
    context.setdefault("last_modified_note", None)
    context.setdefault("last_accessed_folder", None)
    context.setdefault("recent_notes", [])
    context.setdefault("recent_operations", [])
    context.setdefault("recent_folders", [])

    # Track operations
    operation = {
        "type": tool_name,
        "timestamp": datetime.now().isoformat(),
    }

    # Update context based on tool
    if tool_name == "create_simple_note":
        title = arguments.get("title", "Unknown")
        context["last_created_note"] = title
        context["last_modified_note"] = title
        context["recent_notes"].insert(0, title)
        operation["note"] = title
        operation["action"] = "created"

    elif tool_name == "create_job_note":
        title = arguments.get("title", "Unknown")
        context["last_created_note"] = title
        context["last_modified_note"] = title
        context["recent_notes"].insert(0, title)
        operation["note"] = title
        operation["action"] = "created"

    elif tool_name == "update_note":
        file_path = arguments.get("file_path", "Unknown")
        context["last_modified_note"] = file_path
        context["recent_notes"].insert(0, file_path)
        operation["note"] = file_path
        operation["action"] = "updated"

    elif tool_name == "rename_note":
        old_path = arguments.get("file_path", "Unknown")
        new_title = arguments.get("new_title", "Unknown")
        context["last_modified_note"] = new_title
        # Remove old name from recent, add new
        if old_path in context["recent_notes"]:
            context["recent_notes"].remove(old_path)
        context["recent_notes"].insert(0, new_title)
        operation["note"] = old_path
        operation["new_title"] = new_title
        operation["action"] = "renamed"

    elif tool_name == "move_note":
        file_path = arguments.get("file_path", "Unknown")
        dest_folder = arguments.get("destination_folder", "Unknown")
        context["last_modified_note"] = file_path
        context["last_accessed_folder"] = dest_folder
        context["recent_notes"].insert(0, file_path)
        context["recent_folders"].insert(0, dest_folder)
        operation["note"] = file_path
        operation["to_folder"] = dest_folder
        operation["action"] = "moved"

    elif tool_name == "list_folder_contents":
        folder = arguments.get("folder_name", "Unknown")
        context["last_accessed_folder"] = folder
        context["recent_folders"].insert(0, folder)
        operation["folder"] = folder
        operation["action"] = "listed"

    elif tool_name == "list_folder":
        folder = arguments.get("folder_name", "Unknown")
        context["last_accessed_folder"] = folder
        context["recent_folders"].insert(0, folder)
        operation["folder"] = folder
        operation["action"] = "listed"

    elif tool_name == "add_tags":
        file_path = arguments.get("file_path", "Unknown")
        tags = arguments.get("tags", [])
        context["last_modified_note"] = file_path
        context["recent_notes"].insert(0, file_path)
        operation["note"] = file_path
        operation["tags"] = tags
        operation["action"] = "tagged"

    elif tool_name == "search_vault":
        query = arguments.get("query", "Unknown")
        operation["query"] = query
        operation["action"] = "searched"

    elif tool_name == "find_related_notes":
        file_path = arguments.get("file_path", "Unknown")
        context["recent_notes"].insert(0, file_path)
        operation["note"] = file_path
        operation["action"] = "found_related"

    elif tool_name == "append_to_daily_note":
        date = arguments.get("date") or "today"
        context["last_modified_note"] = f"Daily Note ({date})"
        operation["note"] = f"Daily Note ({date})"
        operation["action"] = "appended"

    elif tool_name == "read_note":
        file_path = arguments.get("file_path", "Unknown")
        context["recent_notes"].insert(0, file_path)
        operation["note"] = file_path
        operation["action"] = "read"

    elif tool_name == "delete_note":
        file_path = arguments.get("file_path", "Unknown")
        operation["note"] = file_path
        operation["action"] = "deleted"

    elif tool_name == "create_link":
        source = arguments.get("source_file", "Unknown")
        target = arguments.get("target_file", "Unknown")
        context["recent_notes"].insert(0, source)
        operation["from"] = source
        operation["to"] = target
        operation["action"] = "linked"

    # Trim to avoid token bloat
    context["recent_notes"] = context["recent_notes"][:10]
    context["recent_folders"] = context["recent_folders"][:5]
    context["recent_operations"] = context["recent_operations"][:15]
    context["recent_operations"].insert(0, operation)

    return context


def format_context_for_prompt(context: Dict[str, Any]) -> str:
    """
    Format context as a string to include in system prompt.

    Args:
        context: Context dict from chat meta

    Returns:
        Formatted string for system prompt injection
    """
    if not context or context == initialize_context():
        return ""  # No context yet

    lines = []
    lines.append("## Recent Conversation Context")
    lines.append("")

    # Last actions
    if context.get("recent_operations"):
        lines.append("### Recent Actions (use these to understand what we just did):")
        for op in context.get("recent_operations", [])[:5]:
            action = op.get("action", "?").replace("_", " ").title()
            if op.get("note"):
                lines.append(f"  • {action}: {op.get('note')}")
            elif op.get("folder"):
                lines.append(f"  • {action}: {op.get('folder')}")
            elif op.get("query"):
                lines.append(f"  • {action}: '{op.get('query')}'")
        lines.append("")

    # Current state
    if context.get("last_created_note"):
        lines.append(f"**Last created note**: {context.get('last_created_note')}")

    if context.get("last_modified_note"):
        lines.append(f"**Last modified note**: {context.get('last_modified_note')}")

    if context.get("last_accessed_folder"):
        lines.append(f"**Last accessed folder**: {context.get('last_accessed_folder')}")

    lines.append("")

    # Natural language guidance
    lines.append(
        "**Note**: If the user says 'that note', 'that file', 'the one we just created', "
        "'the last one', 'it', etc., refer to the context above to infer what they mean. "
        "If they say 'move that note', use the last modified note. If they say 'the folder', "
        "use the last accessed folder."
    )
    lines.append("")

    return "\n".join(lines)


def should_include_context(context: Optional[Dict[str, Any]]) -> bool:
    """
    Check if context is worth including (has meaningful data).

    Args:
        context: Context dict or None

    Returns:
        True if context should be included in prompt
    """
    if not context:
        return False

    if context == initialize_context():
        return False

    # Include if we have any recent activity
    has_data = (
        context.get("last_created_note") or
        context.get("last_modified_note") or
        context.get("last_accessed_folder") or
        bool(context.get("recent_operations"))
    )

    return has_data
