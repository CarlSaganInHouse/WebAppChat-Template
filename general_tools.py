"""
General-purpose tools for autonomous agent mode.

Instead of 30+ specific tools that require complex routing decisions,
this module provides 5 fundamental operations that let the model
decide how to accomplish tasks using its own judgment.

Tools:
- read_file: Read any file from the vault
- write_file: Create or overwrite a file
- append_file: Append content to existing file
- search: Full-text search across vault
- list_directory: List files and folders
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from config import get_settings


# =============================================================================
# Tool Definitions (OpenAI/Anthropic function calling format)
# =============================================================================

GENERAL_TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of any file from the Obsidian vault. Returns the full text content of the file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file relative to vault root (use list_directory to discover folders)"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Create a new file or completely overwrite an existing file in the vault. Use for creating new notes or replacing content entirely.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path for the file relative to vault root (use list_directory to discover folders)"
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file (markdown format recommended)"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "append_file",
        "description": "Append content to the end of an existing file. Use for adding to daily notes, logs, or any file where you want to add without replacing.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the existing file relative to vault root"
                },
                "content": {
                    "type": "string",
                    "description": "Content to append (will be added after existing content with a newline)"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "search",
        "description": "Search across all files in the vault for matching text. Returns file paths and matching snippets. Use to find notes by content when you don't know the exact path.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query - can be a word, phrase, or partial match"
                },
                "folder": {
                    "type": "string",
                    "description": "Optional: limit search to a specific folder (use list_directory to discover folders)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_directory",
        "description": "List all files and subfolders in a directory. Use to explore vault structure or see what's in a folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to directory relative to vault root. Empty string or '/' for vault root."
                }
            },
            "required": []
        }
    }
]


# =============================================================================
# Tool Execution Handlers
# =============================================================================

def _get_vault_path() -> Path:
    """Get the vault path from settings."""
    settings = get_settings()
    return settings.vault_path


def _safe_path(relative_path: str) -> Path:
    """
    Safely resolve a path within the vault, preventing directory traversal.
    
    Args:
        relative_path: User-provided path relative to vault root
        
    Returns:
        Absolute path guaranteed to be within vault
        
    Raises:
        ValueError: If path attempts to escape vault
    """
    vault = _get_vault_path()
    
    # Normalize the path and resolve any .. components
    clean_path = relative_path.strip().lstrip('/')
    full_path = (vault / clean_path).resolve()
    
    # Security check: ensure path is within vault
    try:
        full_path.relative_to(vault.resolve())
    except ValueError:
        raise ValueError(f"Path '{relative_path}' is outside the vault")
    
    return full_path


def execute_read_file(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Read a file from the vault."""
    path = arguments.get("path", "")
    
    if not path:
        return {"success": False, "error": "No path provided"}
    
    try:
        full_path = _safe_path(path)
        
        if not full_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        
        if not full_path.is_file():
            return {"success": False, "error": f"Path is a directory, not a file: {path}"}
        
        content = full_path.read_text(encoding='utf-8')
        
        return {
            "success": True,
            "path": path,
            "content": content,
            "size_bytes": len(content.encode('utf-8'))
        }
        
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Error reading file: {str(e)}"}


def execute_write_file(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Write/create a file in the vault."""
    path = arguments.get("path", "")
    content = arguments.get("content", "")
    
    if not path:
        return {"success": False, "error": "No path provided"}
    
    try:
        full_path = _safe_path(path)
        
        # Ensure parent directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if file existed (for messaging)
        existed = full_path.exists()
        
        # Write the file
        full_path.write_text(content, encoding='utf-8')
        
        # Fix ownership to match vault
        _fix_ownership(full_path)
        
        action = "Updated" if existed else "Created"
        return {
            "success": True,
            "message": f"{action} file: {path}",
            "path": path,
            "action": action.lower(),
            "size_bytes": len(content.encode('utf-8'))
        }
        
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Error writing file: {str(e)}"}


def execute_append_file(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Append content to an existing file."""
    path = arguments.get("path", "")
    content = arguments.get("content", "")
    
    if not path:
        return {"success": False, "error": "No path provided"}
    
    try:
        full_path = _safe_path(path)
        
        if not full_path.exists():
            return {"success": False, "error": f"File not found: {path}. Use write_file to create new files."}
        
        # Read existing content and append
        existing = full_path.read_text(encoding='utf-8')
        
        # Add newline separator if needed
        if existing and not existing.endswith('\n'):
            new_content = existing + '\n' + content
        else:
            new_content = existing + content
        
        full_path.write_text(new_content, encoding='utf-8')
        _fix_ownership(full_path)
        
        return {
            "success": True,
            "message": f"Appended to: {path}",
            "path": path,
            "appended_bytes": len(content.encode('utf-8'))
        }
        
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Error appending to file: {str(e)}"}


def execute_search(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Search vault for matching content."""
    query = arguments.get("query", "")
    folder = arguments.get("folder", "")
    
    if not query:
        return {"success": False, "error": "No search query provided"}
    
    try:
        vault = _get_vault_path()
        search_path = vault / folder if folder else vault
        
        if not search_path.exists():
            return {"success": False, "error": f"Folder not found: {folder}"}
        
        results = []
        query_lower = query.lower()
        
        # Search through all markdown files
        for md_file in search_path.rglob("*.md"):
            # Skip hidden files/folders
            if any(part.startswith('.') for part in md_file.parts):
                continue
            
            try:
                content = md_file.read_text(encoding='utf-8')
                if query_lower in content.lower():
                    # Find matching line for context
                    lines = content.split('\n')
                    matching_lines = [
                        line.strip() for line in lines 
                        if query_lower in line.lower()
                    ][:3]  # Max 3 matching lines
                    
                    relative_path = str(md_file.relative_to(vault))
                    results.append({
                        "path": relative_path,
                        "matches": matching_lines
                    })
                    
            except Exception:
                continue  # Skip unreadable files
        
        # Sort by path and limit results
        results = sorted(results, key=lambda x: x["path"])[:20]
        
        return {
            "success": True,
            "query": query,
            "folder": folder or "(all)",
            "result_count": len(results),
            "results": results
        }
        
    except Exception as e:
        return {"success": False, "error": f"Search error: {str(e)}"}


def execute_list_directory(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """List contents of a directory."""
    path = arguments.get("path", "")
    
    try:
        vault = _get_vault_path()
        
        if not path or path == "/":
            target = vault
            display_path = "(vault root)"
        else:
            target = _safe_path(path)
            display_path = path
        
        if not target.exists():
            return {"success": False, "error": f"Directory not found: {path}"}
        
        if not target.is_dir():
            return {"success": False, "error": f"Path is a file, not a directory: {path}"}
        
        folders = []
        files = []
        
        for item in sorted(target.iterdir()):
            # Skip hidden items
            if item.name.startswith('.'):
                continue
            
            if item.is_dir():
                folders.append(item.name + "/")
            else:
                files.append(item.name)
        
        return {
            "success": True,
            "path": display_path,
            "folders": folders,
            "files": files[:50],  # Limit file list
            "total_files": len(files),
            "total_folders": len(folders)
        }
        
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Error listing directory: {str(e)}"}


def _fix_ownership(file_path: Path) -> None:
    """Fix file ownership to match vault ownership."""
    try:
        vault = _get_vault_path()
        vault_stat = vault.stat()
        os.chown(file_path, vault_stat.st_uid, vault_stat.st_gid)
        os.chmod(file_path, 0o664)
    except Exception:
        pass  # Non-fatal


# =============================================================================
# Main Dispatcher
# =============================================================================

GENERAL_FUNCTION_HANDLERS = {
    "read_file": execute_read_file,
    "write_file": execute_write_file,
    "append_file": execute_append_file,
    "search": execute_search,
    "list_directory": execute_list_directory,
}

GENERAL_FUNCTION_NAMES = set(GENERAL_FUNCTION_HANDLERS.keys())


def execute_general_function(function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a general tool function.
    
    Args:
        function_name: Name of the function to execute
        arguments: Dictionary of function arguments
        
    Returns:
        Result dictionary with success status and data/error
    """
    handler = GENERAL_FUNCTION_HANDLERS.get(function_name)
    
    if not handler:
        return {
            "success": False,
            "error": f"Unknown function: {function_name}. Available: {', '.join(GENERAL_FUNCTION_NAMES)}"
        }
    
    return handler(arguments)


# For OpenAI-style tool format conversion
def get_general_tools_openai_format() -> list:
    """Get tools in OpenAI function calling format."""
    return [{"type": "function", "function": tool} for tool in GENERAL_TOOLS]


# For Anthropic-style tool format conversion  
def get_general_tools_anthropic_format() -> list:
    """Get tools in Anthropic tool use format."""
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"]
        }
        for tool in GENERAL_TOOLS
    ]
