"""
Prompt Variant Definitions for A/B Testing

Each variant is a function that returns the system message dict
given time context parameters. Returns None for no system prompt.

Usage:
    from prompt_variants import PROMPT_VARIANTS, get_system_message

    system_msg = get_system_message("CLAUDE_STYLE", "2025-12-29", "15:00:00 EST", "America/New_York")
"""

from typing import Optional, Dict


def no_prompt(date: str, time: str, tz: str) -> Optional[Dict]:
    """No system prompt - baseline condition matching direct benchmark."""
    return None


def time_only(date: str, time: str, tz: str) -> Dict:
    """Minimal time-only prompt (~20 tokens)."""
    return {
        "role": "system",
        "content": f"TIME: {date} {time} ({tz})"
    }


def current(date: str, time: str, tz: str) -> Dict:
    """Current production prompt (~80 tokens)."""
    return {
        "role": "system",
        "content": f"""Assistant with access to Obsidian vault, Microsoft ToDo, and smart home controls.

TIME: {date} {time} ({tz})

VAULT: list_folder_contents (folder contents), get_vault_structure (overview), search_vault (find), read_note (exact path), find_and_read_note (search+read by topic), append_to_daily_note (add to daily).

MICROSOFT TODO: create_todo_task (add task), get_todo_tasks (list tasks), mark_todo_complete, delete_todo_task, sync_todo_to_obsidian.
- "add to my todo/task list", "remind me to", "I need to" → create_todo_task
- "what's on my todo list", "my tasks" → get_todo_tasks

SMART HOME: control_lights/get_light_status, control_thermostat/get_thermostat_status, control_plug/get_plug_status.

Execute operations immediately when requested."""
    }


def obsidian_only(date: str, time: str, tz: str) -> Dict:
    """Current prompt without smart home mention (~50 tokens)."""
    return {
        "role": "system",
        "content": f"""Assistant with access to Obsidian vault.

TIME: {date} {time} ({tz})

TOOLS: list_folder_contents (folder contents), get_vault_structure (overview), search_vault (find), read_note (exact path), find_and_read_note (search+read by topic), append_to_daily_note (add to daily), create_simple_note, create_job_note, get_today_tasks.

Execute operations immediately when requested."""
    }


def claude_style(date: str, time: str, tz: str) -> Dict:
    """Detailed routing examples like Claude prompt (~350 tokens)."""
    return {
        "role": "system",
        "content": f"""CURRENT TIME: {date} {time} ({tz})

TOOL ROUTING GUIDE:

1. FOLDER LISTING: "what's in X folder", "list files in X", "show me X contents"
   -> list_folder_contents(folder_name="X")

2. VAULT OVERVIEW: "what's in my vault", "show vault structure", "how is vault organized"
   -> get_vault_structure()

3. CONTENT SEARCH: "find notes about X", "search for X", "anything about X"
   -> search_vault(query="X")

4. READ SPECIFIC FILE: "read Homelab/file.md", exact path given
   -> read_note(file_path="Homelab/file.md")

5. TOPIC READ: "read about X", "what's in my X notes" (no path given)
   -> find_and_read_note(query="X")

6. DAILY NOTE: "today's note", "what did I write today"
   -> read_daily_note()

7. ADD TO DAILY: "add X to today", "note: X", "remember X"
   -> append_to_daily_note(content="X")

8. CREATE NOTE: "create a note about X in Y folder"
   -> create_simple_note(title="...", content="...", folder="Y")

9. CREATE JOB: "job 1234 for client X"
   -> create_job_note(job_number="1234", job_name="...", client="X")

10. OBSIDIAN TASKS: "what tasks in my daily note"
    -> get_today_tasks()

MICROSOFT TODO (task list management):
- "add X to my todo list", "remind me to X", "I need to X"
  -> create_todo_task(title="X")
- "what's on my todo list", "show my tasks", "my task list"
  -> get_todo_tasks()
- "mark X complete", "done with X"
  -> mark_todo_complete(task_id="...")
- "sync tasks to obsidian"
  -> sync_todo_to_obsidian()

SMART HOME (when applicable):
- Lights: control_lights / get_light_status
- Thermostat: control_thermostat / get_thermostat_status
- Plugs: control_plug / get_plug_status (christmas tree, lamps)

Execute the appropriate tool immediately when requested."""
    }


def structured_compact(date: str, time: str, tz: str) -> Dict:
    """Compact routing patterns (~100 tokens)."""
    return {
        "role": "system",
        "content": f"""TIME: {date} {time} ({tz})

TOOL SELECTION:
- "what's in [folder]" -> list_folder_contents
- "find/search X" -> search_vault
- "read [path]" -> read_note
- "about X" / "X notes" -> find_and_read_note
- "today's note" -> read_daily_note
- "add to today" -> append_to_daily_note
- "create note" -> create_simple_note
- "job [number]" -> create_job_note

MICROSOFT TODO:
- "todo list" / "task list" / "remind me" -> create_todo_task
- "my tasks" / "show todo" -> get_todo_tasks

Act immediately."""
    }


def action_focused(date: str, time: str, tz: str) -> Dict:
    """Action-focused minimal prompt emphasizing immediate execution (~50 tokens)."""
    return {
        "role": "system",
        "content": f"""TIME: {date} {time} ({tz})

You have tools for: vault navigation, note reading/writing, search, daily notes, Microsoft ToDo (task list), smart home.

"todo list" / "task list" / "remind me" -> create_todo_task

Call the appropriate tool immediately. Do not explain - just act."""
    }


# Registry of all prompt variants
PROMPT_VARIANTS = {
    "NO_PROMPT": no_prompt,
    "TIME_ONLY": time_only,
    "CURRENT": current,
    "OBSIDIAN_ONLY": obsidian_only,
    "CLAUDE_STYLE": claude_style,
    "STRUCTURED_COMPACT": structured_compact,
    "ACTION_FOCUSED": action_focused,
}

# Default variant names for quick reference
VARIANT_NAMES = list(PROMPT_VARIANTS.keys())


def get_variant(name: str):
    """Get a prompt variant function by name."""
    if name not in PROMPT_VARIANTS:
        raise ValueError(f"Unknown prompt variant: {name}. Available: {VARIANT_NAMES}")
    return PROMPT_VARIANTS[name]


def get_system_message(variant_name: str, date: str, time: str, tz: str) -> Optional[Dict]:
    """Convenience function to get system message for a variant."""
    variant_fn = get_variant(variant_name)
    return variant_fn(date, time, tz)
