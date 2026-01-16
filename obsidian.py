"""
Obsidian vault integration for WebApp Chat - Service Layer Wrapper

This module provides backward compatibility by delegating to ObsidianService.
The heavy lifting is now done by services/obsidian_service.py (958 lines).

REFACTORED: 2025-11-16 - Phase 3
Original size: 2,274 lines → New size: ~150 lines (93% reduction)

For new code, use ObsidianService directly:
    from services.obsidian_service import ObsidianService
    service = ObsidianService()
    result = service.create_note(...)
"""

from pathlib import Path
from typing import Optional, List, Dict, Any

from services.obsidian_service import ObsidianService

# Create singleton service instance
_service = ObsidianService()


# ============================================================================
# VAULT OPERATIONS - Thin wrappers for backward compatibility
# ============================================================================

def get_vault_path() -> Path:
    """
    Get the vault path and ensure it exists.

    DEPRECATED: Use ObsidianService().get_vault_path() directly.
    """
    return _service.get_vault_path()


def fix_file_ownership(file_path):
    """
    Fix ownership of files created by the app.

    DEPRECATED: Use ObsidianService().fix_file_ownership() directly.
    """
    file_path = Path(file_path) if not isinstance(file_path, Path) else file_path
    return _service.fix_file_ownership(file_path)


def get_vault_folders() -> List[str]:
    """
    Get list of all folders in the vault.

    DEPRECATED: Use ObsidianService().get_vault_folders() directly.
    """
    return _service.get_vault_folders()


def validate_obsidian_function_args(function_name: str, arguments: dict):
    """
    Validate function arguments before execution.

    DEPRECATED: Use ObsidianService().validate_function_args() directly.
    """
    return _service.validate_function_args(function_name, arguments)


# ============================================================================
# DAILY NOTE OPERATIONS
# ============================================================================

def get_daily_note_path(date_str: Optional[str] = None):
    """
    Resolve the path to a daily note.

    DEPRECATED: Use ObsidianService().get_daily_note_path() directly.
    """
    return _service.get_daily_note_path(date_str)


def get_today_note_path():
    """
    Get the path to today's daily note.

    DEPRECATED: Use ObsidianService().get_daily_note_path()[0] directly.
    """
    return _service.get_daily_note_path()[0]


def ensure_daily_note(date_str: Optional[str] = None):
    """
    Ensure a daily note exists.

    DEPRECATED: Use ObsidianService().ensure_daily_note() directly.
    """
    return _service.ensure_daily_note(date_str)


def append_to_daily(content, section="Quick Captures", date=None, dry_run=False):
    """
    Append content to a daily note.

    DEPRECATED: Use ObsidianService().append_to_daily() directly.
    """
    return _service.append_to_daily(content, section, date, dry_run)


def read_daily_note(date_str=None, dry_run=False):
    """
    Read a daily note.

    DEPRECATED: Use ObsidianService().read_note() directly.
    """
    # Construct the daily note path using configured folder
    from config import get_settings
    settings = get_settings()

    if date_str is None:
        from datetime import datetime
        date_str = datetime.now().strftime('%Y-%m-%d')

    file_path = f"{settings.daily_notes_folder}/{date_str}.md"
    return _service.read_note(file_path, dry_run)


# ============================================================================
# NOTE CRUD OPERATIONS
# ============================================================================

def read_note(file_path, dry_run=False):
    """
    Read any note from the vault.

    DEPRECATED: Use ObsidianService().read_note() directly.
    """
    return _service.read_note(file_path, dry_run)


def create_note(content, destination, filename=None, mode="create"):
    """
    Universal note creation function.

    DEPRECATED: Use ObsidianService().create_note() directly.
    """
    return _service.create_note(content, destination, filename, mode)


def update_note_section(file_path, section_name, new_content, dry_run=False):
    """
    Update a specific section in a note.

    DEPRECATED: Use ObsidianService().update_note_section() directly.
    """
    return _service.update_note_section(file_path, section_name, new_content, dry_run)


def replace_note_content(file_path, old_text, new_text):
    """
    Find and replace text in a note.

    NOTE: This is NOT yet in ObsidianService - uses local implementation.
    TODO: Move to service in future phase.
    """
    try:
        from utils.vault_security import safe_vault_path, VaultPathError

        vault = get_vault_path()
        note_path = safe_vault_path(vault, file_path, must_exist=True)
        content = note_path.read_text(encoding='utf-8')

        if old_text not in content:
            return {
                "success": False,
                "error": f"Text '{old_text}' not found in note"
            }

        new_content = content.replace(old_text, new_text)
        count = content.count(old_text)
        note_path.write_text(new_content, encoding='utf-8')

        return {
            "success": True,
            "message": f"Replaced {count} occurrence(s) in {file_path}",
            "count": count
        }

    except VaultPathError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_note(file_path, dry_run=False):
    """
    Delete a note from the vault.

    DEPRECATED: Use ObsidianService().delete_note() directly.
    """
    return _service.delete_note(file_path, dry_run)


# ============================================================================
# JOB NOTE OPERATIONS
# ============================================================================

def create_job_note(job_number, job_name, client="", dry_run=False):
    """
    Create a new job note from template.

    DEPRECATED: Use ObsidianService().create_job_note() directly.
    """
    return _service.create_job_note(job_number, job_name, client, dry_run)


# ============================================================================
# SEARCH & DISCOVERY OPERATIONS
# ============================================================================

def list_vault_structure():
    """
    List the vault structure.

    DEPRECATED: Use ObsidianService().list_vault_structure() directly.
    """
    return _service.list_vault_structure()


def list_folder_contents(folder_name, limit=50):
    """
    List all files in a specific vault folder.

    DEPRECATED: Use ObsidianService().list_folder_contents() directly.
    """
    return _service.list_folder_contents(folder_name, limit)


def search_vault(query, folders=None, case_sensitive=False):
    """
    Search for text across all vault files.

    DEPRECATED: Use ObsidianService().search_vault() directly.
    """
    return _service.search_vault(query, folders, case_sensitive)


# ============================================================================
# TEMPLATE SYSTEM
# ============================================================================

def list_templates():
    """
    List all available templates.

    DEPRECATED: Use ObsidianService().list_templates() directly.
    """
    return _service.list_templates()


def create_note_from_template(template_name, destination, variables=None):
    """
    Create a new note from a template with variable substitution.

    DEPRECATED: Use ObsidianService().create_note_from_template() directly.
    """
    return _service.create_note_from_template(template_name, destination, variables)


def create_custom_template(template_name, content):
    """
    Save a new custom template.

    DEPRECATED: Use ObsidianService().create_custom_template() directly.
    """
    return _service.create_custom_template(template_name, content)


# ============================================================================
# SMART LINKING
# ============================================================================

def find_linkable_notes(content, current_file=None):
    """
    Find notes in vault that should be linked from content.

    DEPRECATED: Use ObsidianService().find_linkable_notes() directly.
    """
    return _service.find_linkable_notes(content, current_file)


def auto_link_content(content, current_file=None):
    """
    Automatically add wikilinks to content.

    DEPRECATED: Use ObsidianService().auto_link_content() directly.
    """
    return _service.auto_link_content(content, current_file)


# ============================================================================
# TAG MANAGEMENT
# ============================================================================

def suggest_tags(content, existing_tags=None):
    """
    Analyze content and suggest relevant tags using GPT-4o-mini.

    DEPRECATED: Use ObsidianService().suggest_tags() directly.
    """
    return _service.suggest_tags(content, existing_tags)


def get_all_tags():
    """
    Extract all tags currently used in the vault.

    DEPRECATED: Use ObsidianService().get_all_tags() directly.
    """
    return _service.get_all_tags()


def apply_tags_to_note(file_path, tags):
    """
    Add tags to a note's frontmatter.

    DEPRECATED: Use ObsidianService().apply_tags_to_note() directly.
    """
    return _service.apply_tags_to_note(file_path, tags)


# ============================================================================
# GRAPH ANALYSIS
# ============================================================================

def build_vault_graph():
    """
    Build a network graph of all notes and their [[wikilink]] connections.

    DEPRECATED: Use ObsidianService().build_vault_graph() directly.
    """
    return _service.build_vault_graph()


def find_orphaned_notes():
    """
    Find notes with no incoming or outgoing links.

    DEPRECATED: Use ObsidianService().find_orphaned_notes() directly.
    """
    return _service.find_orphaned_notes()


def suggest_connections(file_path=None, limit=5):
    """
    Suggest potential connections based on shared tags, similar titles, or content.

    DEPRECATED: Use ObsidianService().suggest_connections() directly.
    """
    return _service.suggest_connections(file_path, limit)


def analyze_clusters():
    """
    Identify clusters/communities of related notes based on tags.

    DEPRECATED: Use ObsidianService().analyze_clusters() directly.
    """
    return _service.analyze_clusters()


def get_note_neighbors(file_path, depth=1):
    """
    Get all notes connected to a specific note
    
    Args:
        file_path: Note to analyze
        depth: How many hops out (1=direct, 2=friends-of-friends)
    
    Returns:
        dict: Connected notes
    """
    try:
        graph = build_vault_graph()
        
        if not graph.get('success'):
            return graph
        
        nodes = graph['nodes']
        
        if file_path not in nodes:
            return {
                "success": False,
                "error": f"Note not found: {file_path}"
            }
        
        # BFS to find neighbors
        visited = {file_path}
        current_level = {file_path}
        neighbors = []
        
        for _ in range(depth):
            next_level = set()
            
            for node_path in current_level:
                node_data = nodes[node_path]
                
                # Add outgoing links
                for link_target in node_data['links_out']:
                    # Find actual path
                    for path, data in nodes.items():
                        if data['title'] == link_target or path.endswith(f"{link_target}.md"):
                            if path not in visited:
                                next_level.add(path)
                                neighbors.append({
                                    "path": path,
                                    "title": nodes[path]['title'],
                                    "relationship": "links_to"
                                })
                            break
                
                # Add incoming links
                for link_source in node_data['links_in']:
                    if link_source not in visited:
                        next_level.add(link_source)
                        neighbors.append({
                            "path": link_source,
                            "title": nodes[link_source]['title'],
                            "relationship": "linked_from"
                        })
            
            visited.update(next_level)
            current_level = next_level
        
        return {
            "success": True,
            "note": file_path,
            "neighbors": neighbors,
            "count": len(neighbors)
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# RESEARCH
# ============================================================================

def research_and_save(topic, save_location="Reference", depth="quick"):
    """
    Research a topic on the web and save to vault.

    DEPRECATED: Use ObsidianService().research_and_save() directly.
    """
    return _service.research_and_save(topic, save_location, depth)


# ============================================================================
# SCHEDULED TASKS
# ============================================================================

def list_scheduled_tasks():
    """
    List all scheduled tasks
    
    Returns:
        dict: List of tasks with schedules
    """
    try:
        vault = get_vault_path()
        tasks_file = vault / ".scheduled_tasks.json"
        
        if not tasks_file.exists():
            return {
                "success": True,
                "tasks": [],
                "count": 0
            }
        
        import json
        tasks = json.loads(tasks_file.read_text(encoding='utf-8'))
        
        return {
            "success": True,
            "tasks": tasks,
            "count": len(tasks)
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def create_scheduled_task(name, schedule, action, parameters=None):
    """
    Create a new scheduled task
    
    Args:
        name: Task name/description
        schedule: Cron-like schedule (daily, weekly, monthly, or specific)
        action: Function to call (e.g., "create_from_template", "append_to_daily")
        parameters: Dict of parameters for the action
    
    Returns:
        dict: Success status
    """
    try:
        vault = get_vault_path()
        tasks_file = vault / ".scheduled_tasks.json"
        
        # Load existing tasks
        if tasks_file.exists():
            import json
            tasks = json.loads(tasks_file.read_text(encoding='utf-8'))
        else:
            tasks = []
        
        # Create new task
        from datetime import datetime
        task = {
            "id": len(tasks) + 1,
            "name": name,
            "schedule": schedule,
            "action": action,
            "parameters": parameters or {},
            "created": datetime.now().isoformat(),
            "last_run": None,
            "enabled": True
        }
        
        tasks.append(task)
        
        # Save
        import json
        tasks_file.write_text(json.dumps(tasks, indent=2), encoding='utf-8')
        
        return {
            "success": True,
            "message": f"Created scheduled task: {name}",
            "task_id": task['id']
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
