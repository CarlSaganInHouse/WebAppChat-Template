"""
Obsidian function definitions for OpenAI function calling
"""

def get_obsidian_functions():
    """
    Generate OBSIDIAN_FUNCTIONS with dynamic folder lists.
    This ensures the LLM always knows current vault structure.
    """
    from obsidian import get_vault_folders

    # Get current vault folders dynamically - no hardcoded fallback
    try:
        vault_folders = get_vault_folders()
        folders_str = "', '".join(vault_folders) if vault_folders else "your vault folders"
    except Exception:
        folders_str = "your vault folders"
    return [
        {
        "name": "update_note",
        "description": "Edit or replace content in an existing note.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to note"},
                "new_content": {"type": "string", "description": "New content"},
                "mode": {"type": "string", "enum": ["replace", "append", "overwrite"]}
            },
            "required": ["file_path", "new_content"]
        }
    },
    {
        "name": "rename_note",
        "description": "Rename a note without moving it.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "new_title": {"type": "string"}
            },
            "required": ["file_path", "new_title"]
        }
    },
    {
        "name": "move_note",
        "description": "Move a note to a different folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "destination_folder": {"type": "string"}
            },
            "required": ["file_path", "destination_folder"]
        }
    },
    {
        "name": "list_folder",
        "description": "List all notes in a folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "folder_name": {"type": "string", "description": "Folder to list"}
            },
            "required": ["folder_name"]
        }
    },
    {
        "name": "add_tags",
        "description": "Add or modify tags on a note.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "mode": {"type": "string", "enum": ["add", "replace"]}
            },
            "required": ["file_path", "tags"]
        }
    },
    {
        "name": "get_today_tasks",
        "description": "Get all tasks from today's daily note in structured format.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Optional date YYYY-MM-DD"}
            }
        }
    },
    {
        "name": "find_related_notes",
        "description": "Find other notes that are related or connected to a note.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "create_link",
        "description": "Create wiki-style links from one note to another.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_file": {"type": "string"},
                "target_file": {"type": "string"},
                "link_text": {"type": "string"}
            },
            "required": ["source_file", "target_file"]
        }
    },
    {
        "name": "append_to_daily_note",
        "description": "Add content to today's daily note. Sections: Quick Captures, Work Notes, Personal Notes, Tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to add to the daily note"
                },
                "section": {
                    "type": "string",
                    "enum": ["Quick Captures", "Work Notes", "Personal Notes", "Tasks"],
                    "description": "Which section of the daily note to add to. Default: Quick Captures"
                },
                "date": {
                    "type": "string",
                    "description": "Optional date in YYYY-MM-DD format. Defaults to today."
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "create_simple_note",
        "description": "Create a new markdown note in any vault folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the note (will become filename)"
                },
                "content": {
                    "type": "string",
                    "description": "Content of the note"
                },
                "folder": {
                    "type": "string",
                    "description": "Folder to create the note in (e.g., 'Reference', 'Homelab')"
                }
            },
            "required": ["title", "content", "folder"]
        }
    },
    # create_job_note removed - deprecated in vault migration
    # Use create_from_template with a project template instead
    {
        "name": "read_note",
        "description": "Read the full content of a note by its file path. Use when user specifies an exact path.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the note (e.g., 'Homelab/Commands.md')"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "find_and_read_note",
        "description": "Search for a note by topic and read its contents. Use when path is unknown.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic, name, or keywords to search for (e.g., 'Dezzie', 'docker setup', 'meeting notes')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "delete_note",
        "description": "Delete a note from the vault. Use dry_run=true to preview.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the note to delete (e.g., 'Reference/Old Note.md')"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, preview deletion without removing the file"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "read_daily_note",
        "description": "Read a daily note for a specific date. Defaults to today if no date given.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format (optional, defaults to today)"
                }
            }
        }
    },
    {
        "name": "get_vault_structure",
        "description": "Get an overview of the entire vault structure including folders, file counts, and recent notes. Use for general vault exploration.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "list_folder_contents",
        "description": "List all files and subfolders in a specific vault folder. Use when user asks 'what's in [folder]' or 'show me [folder] contents'.",
        "parameters": {
            "type": "object",
            "properties": {
                "folder_name": {
                    "type": "string",
                    "description": "Name of the folder to list (use get_vault_structure to see available folders)"
                }
            },
            "required": ["folder_name"]
        }
    },
    {
        "name": "search_vault",
        "description": "Search across all vault files for a keyword or phrase. Returns matching files with context snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keyword or phrase)"
                },
                "folders": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: limit search to specific folders"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "update_note_section",
        "description": "Replace content in a specific section of a note.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the note (e.g., 'Daily Notes/2025-10-26.md' or 'Jobs/1234-Project/1234-Project.md')"
                },
                "section_name": {
                    "type": "string",
                    "description": "The section header to update (without ## prefix, e.g., 'Work Notes', 'Overview', 'Tasks')"
                },
                "new_content": {
                    "type": "string",
                    "description": "The new content for this section"
                }
            },
            "required": ["file_path", "section_name", "new_content"]
        }
    },
    {
        "name": "replace_text_in_note",
        "description": "Find and replace specific text in a note. Use for updating status, fixing errors, or making specific text changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the note"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace it with"
                }
            },
            "required": ["file_path", "old_text", "new_text"]
        }
    },
    {
        "name": "research_and_save",
        "description": f"Search the web for information about a topic, summarize findings, and save to the vault. Use when the user asks to research or look up information. Available vault folders: '{folders_str}'",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic or question to research"
                },
                "save_location": {
                    "type": "string",
                    "description": f"Where to save. Use one of these folder names: '{folders_str}'. OR provide a specific file path ending in .md to append to an existing note (e.g., 'Daily Notes/2025-10-29.md')."
                },
                "depth": {
                    "type": "string",
                    "enum": ["quick", "detailed"],
                    "description": "How thorough the research should be. Default: quick"
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "create_from_template",
        "description": f"Create a new note from a template with variable substitution. Use for meeting notes, weekly reviews, client briefs, etc. Available vault folders: '{folders_str}'",
        "parameters": {
            "type": "object",
            "properties": {
                "template_name": {
                    "type": "string",
                    "description": "Name of the template to use (e.g., 'Meeting Notes', 'Weekly Review', 'Client Brief')"
                },
                "destination": {
                    "type": "string",
                    "description": f"Where to save. Use one of these folder names: '{folders_str}', OR provide a full path ending in .md (e.g., 'Jobs/1234/meeting.md')"
                },
                "variables": {
                    "type": "object",
                    "description": "Variables to substitute in template (e.g., {title: 'Project Kickoff', client: 'Acme Corp'}). Template uses {{variable}} syntax."
                }
            },
            "required": ["template_name", "destination"]
        }
    },
    {
        "name": "list_templates",
        "description": "Show all available templates in the vault. Use when user asks what templates exist.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "save_custom_template",
        "description": "Save a new custom template for future use. Use when user wants to create a reusable template.",
        "parameters": {
            "type": "object",
            "properties": {
                "template_name": {
                    "type": "string",
                    "description": "Name for the new template"
                },
                "content": {
                    "type": "string",
                    "description": "Template content. Can include {{variable}} placeholders for substitution."
                }
            },
            "required": ["template_name", "content"]
        }
    },
    {
        "name": "suggest_links",
        "description": "Analyze text and suggest [[wikilinks]] to existing notes. Use when user wants to connect related notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Text to analyze for potential links"
                },
                "auto_apply": {
                    "type": "boolean",
                    "description": "Whether to automatically add links (true) or just suggest them (false)"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "suggest_tags_for_note",
        "description": "Analyze note content and suggest relevant tags based on vault taxonomy. Use when user wants help organizing notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the note to analyze"
                },
                "auto_apply": {
                    "type": "boolean",
                    "description": "Whether to automatically apply tags (true) or just suggest them (false)"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "find_orphaned_notes",
        "description": "Find notes with no incoming or outgoing links (isolated notes). Use to identify disconnected knowledge.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "suggest_note_connections",
        "description": "Suggest potential connections between notes based on shared tags and content. Use to discover hidden relationships.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Optional: specific note to analyze (or analyze entire vault)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of suggestions (default: 5)"
                }
            }
        }
    },
    {
        "name": "analyze_vault_clusters",
        "description": "Identify clusters/groups of related notes by tags and connections. Use to understand vault organization.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_note_network",
        "description": "Get all notes connected to a specific note (network neighborhood). Use to explore note relationships.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Note to analyze"
                },
                "depth": {
                    "type": "integer",
                    "description": "How many hops out (1=direct connections, 2=friends-of-friends). Default: 1"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "create_scheduled_task",
        "description": "Schedule a recurring vault action (daily weekly reviews, auto-backups, etc). Use for automation.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Task name/description"
                },
                "schedule": {
                    "type": "string",
                    "description": "Schedule: 'daily', 'weekly', 'monthly', or 'every_N_days'"
                },
                "action": {
                    "type": "string",
                    "description": "Action to perform: 'create_from_template', 'append_to_daily', etc."
                },
                "parameters": {
                    "type": "object",
                    "description": "Parameters for the action (e.g., template_name, content, section)"
                }
            },
            "required": ["name", "schedule", "action"]
        }
    },
    {
        "name": "list_scheduled_tasks",
        "description": "Show all scheduled/recurring tasks. Use to see what's automated.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "save_image_to_vault",
        "description": "Save an attached image to the Obsidian vault. Use when the user asks to save, store, or organize an image they've attached to the chat. The image will be saved to Attachments/ folder and optionally embedded in a note.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Desired filename for the image (e.g., 'lawn_mower_manual.jpg'). Will be sanitized. If not provided, a timestamp-based name will be used."
                },
                "embed_in_note": {
                    "type": "string",
                    "description": "Optional: Path to the note to embed the image in (e.g., 'Equipment/Lawn Mower.md'). The image link will be appended to this note."
                },
                "section": {
                    "type": "string",
                    "description": "Optional: Section header to place the image under (e.g., 'Attachments' or 'Images'). Only used if embed_in_note is provided."
                }
            }
        }
    }
    ]

# Generate the functions list with dynamic content
OBSIDIAN_FUNCTIONS = get_obsidian_functions()

def execute_obsidian_function(function_name, arguments):
    """
    Execute an Obsidian vault function based on AI function call

    Args:
        function_name: Name of the function to execute
        arguments: Dictionary of function arguments

    Returns:
        dict: Result of the function execution
    """
    from obsidian import (append_to_daily, read_note, read_daily_note,
                          list_vault_structure, list_folder_contents, search_vault, update_note_section,
                          replace_note_content, research_and_save, list_templates,
                          create_note_from_template, create_custom_template,
                          find_linkable_notes, auto_link_content, suggest_tags,
                          apply_tags_to_note, find_orphaned_notes, suggest_connections,
                          analyze_clusters, get_note_neighbors, create_scheduled_task,
                          list_scheduled_tasks, validate_obsidian_function_args,
                          delete_note)
    from obsidian_tool_models import (
        AppendToDailyNoteParams,
        CreateSimpleNoteParams,
        UpdateNoteSectionParams,
        CreateFromTemplateParams,
        DeleteNoteParams
    )
    from pydantic import ValidationError

    # Pydantic validation for top tools (Phase 1A)
    try:
        if function_name == "append_to_daily_note":
            AppendToDailyNoteParams(**arguments)
        elif function_name == "create_simple_note":
            CreateSimpleNoteParams(**arguments)
        elif function_name == "create_job_note":
            # Deprecated - return error immediately
            return {
                "success": False,
                "message": "❌ create_job_note is deprecated. Use create_from_template with a project template instead.",
                "deprecated": True
            }
        elif function_name == "update_note_section":
            UpdateNoteSectionParams(**arguments)
        elif function_name == "create_from_template":
            CreateFromTemplateParams(**arguments)
        elif function_name == "delete_note":
            DeleteNoteParams(**arguments)
    except ValidationError as e:
        # Format Pydantic errors nicely
        errors = []
        for error in e.errors():
            field = " -> ".join(str(x) for x in error['loc'])
            msg = error['msg']
            errors.append(f"{field}: {msg}")
        return {
            "success": False,
            "message": f"⚠️ Invalid parameters:\n" + "\n".join(f"  • {err}" for err in errors),
            "validation_failed": True
        }

    # Legacy validation (for tools not yet Pydantic-validated)
    is_valid, error_message = validate_obsidian_function_args(function_name, arguments)
    if not is_valid:
        return {
            "success": False,
            "message": f"⚠️ Validation Error: {error_message}",
            "validation_failed": True
        }
    
    if function_name == "append_to_daily_note":
        content = arguments.get("content", "")
        section = arguments.get("section", "Quick Captures")
        date = arguments.get("date")
        result = append_to_daily(content, section, date=date)
        if result['success']:
            meta = result.get("data", {})
            target_date = meta.get("date", "today")
            return {
                "success": True,
                "message": f"? Added to daily note ({target_date}) under '{section}': {content}",
                "details": meta
            }
        else:
            return {"success": False, "message": f"? Error: {result.get('error')}"}
    elif function_name == "create_simple_note":
        from obsidian import create_note
        title = arguments.get("title", "")
        content = arguments.get("content", "")
        folder = arguments.get("folder", "")
        
        # Create the note
        filename = f"{title}.md"
        result = create_note(content, folder, filename, mode="create")
        
        if result.get('success'):
            relative_path = result.get('path', f"{folder}/{filename}")
            absolute_path = result.get('absolute_path', '')
            return {
                "success": True,
                "message": f"✅ Created note: {title}\n📁 Location: `{relative_path}`",
                "path": relative_path,
                "file_path": absolute_path,  # For verification
            }
        else:
            return {"success": False, "message": f"❌ Error creating note: {result.get('error', 'Unknown error')}"} 
    
    # create_job_note is handled in validation above - returns deprecation error
    
    elif function_name == "read_note":
        file_path = arguments.get("file_path", "")
        result = read_note(file_path)
        if result['success']:
            return {
                "success": True,
                "message": f"📄 Contents of {file_path}:\n\n{result['content']}"
            }
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}

    elif function_name == "delete_note":
        file_path = arguments.get("file_path", "")
        dry_run = arguments.get("dry_run", False)
        result = delete_note(file_path, dry_run=dry_run)
        if result['success']:
            suffix = " (preview only)" if result.get("dry_run") else ""
            return {
                "success": True,
                "message": f"?? Deleted note: {file_path}{suffix}"
            }
        else:
            return {"success": False, "message": f"? Error deleting note: {result.get('error')}"}
    elif function_name == "read_daily_note":
        date_str = arguments.get("date")
        result = read_daily_note(date_str)
        if result['success']:
            return {
                "success": True,
                "message": f"Daily note for {result['date']}:\n\n{result['content']}"
            }
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "get_vault_structure":
        result = list_vault_structure()
        if result['success']:
            structure = result['structure']
            message = f"📁 Vault Structure:\n\n"
            message += f"**Recent Daily Notes:** {', '.join(structure.get('recent_daily_notes', []))}\n\n"
            message += f"**Folders:**\n"
            for folder, info in structure['folders'].items():
                if isinstance(info, dict):
                    count = info.get('count', 0)
                    message += f"  - {folder}: {count} file(s)\n"
                else:
                    message += f"  - {folder}: {len(info) if isinstance(info, list) else '?'} file(s)\n"
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}

    elif function_name == "list_folder_contents":
        folder_name = arguments.get("folder_name", "")
        result = list_folder_contents(folder_name)
        if result['success']:
            files = result['files']
            total = result['total_files']
            returned = result.get('returned_files', len(files))
            
            message = f"📁 Contents of '{folder_name}' folder ({total} file(s)):\n\n"

            for idx, file_info in enumerate(files, 1):
                name = file_info['name']
                path = file_info.get('path', name)
                # Build full vault path for clickable links
                full_vault_path = f"{folder_name}/{path}" if path != name and '/' in path else f"{folder_name}/{name}"

                # Format as numbered list with vault: prefix
                message += f"{idx}. vault:{full_vault_path}\n"

            # Add summary if there are more files than returned
            if total > returned:
                remaining = total - returned
                message += f"\n... and {remaining} more file(s) not shown (showing first {returned})\n"

            if total == 0:
                message = f"📁 The '{folder_name}' folder is empty."

            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}

    elif function_name == "search_vault":
        query = arguments.get("query", "")
        folders = arguments.get("folders")
        limit = arguments.get("limit", 10)
        result = search_vault(query, folders)
        if result['success']:
            if result['total_files'] == 0:
                return {
                    "success": True,
                    "message": f"🔍 No results found for '{query}'"
                }

            message = f"🔍 Found '{query}' in {result['total_files']} file(s):\n\n"
            for file_result in result['results'][:limit]:  # Respect limit parameter
                file_path = file_result['file']
                message += f"**vault:{file_path}**\n"
                for match in file_result['matches'][:2]:  # Show first 2 matches per file
                    message += f"  Line {match['line']}: {match['text'][:100]}\n"
                message += "\n"
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}

    elif function_name == "find_and_read_note":
        # Combined search + read for local models that can't chain tool calls
        from obsidian import search_vault, read_note
        query = arguments.get("query", "")

        # Step 1: Search for the note
        search_result = search_vault(query)
        if not search_result['success']:
            return {"success": False, "message": f"❌ Search error: {search_result.get('error')}"}

        if search_result['total_files'] == 0:
            return {"success": True, "message": f"🔍 No notes found matching '{query}'"}

        # Step 2: Rank results to find the best match
        # Prefer notes whose filename contains the query over notes with query only in content
        results = search_result['results']
        query_lower = query.lower()

        def score_result(r):
            """Score a result - higher is better match"""
            import re
            file_path = r.get('file', '').lower()
            filename = file_path.split('/')[-1].replace('.md', '')
            score = 0

            # Strong match: filename contains exact query
            if query_lower in filename:
                score += 100
                # Bonus: filename starts with query (exact name match)
                if filename.startswith(query_lower):
                    score += 50
            # Medium match: filename contains query word
            elif any(word in filename for word in query_lower.split()):
                score += 50
            # Weak match: just content match
            else:
                score += 10

            # Penalty: auto-generated notes with timestamps (e.g., _20251215_)
            if re.search(r'_\d{8}_', filename):
                score -= 80

            # Penalty: very long filenames (likely auto-generated)
            if len(filename) > 50:
                score -= 20

            # Bonus: shorter filenames (more focused notes)
            if len(filename) < 30:
                score += 10

            return score

        # Sort by score (descending)
        ranked_results = sorted(results, key=score_result, reverse=True)
        best_match = ranked_results[0]
        file_path = best_match['file']

        # Step 3: Read the note content
        read_result = read_note(file_path)
        if not read_result['success']:
            return {"success": False, "message": f"❌ Found note at '{file_path}' but couldn't read it: {read_result.get('error')}"}

        # Return the full note content with context
        content = read_result.get('content', '')
        title = read_result.get('title', file_path)

        message = f"📄 **{title}** (vault:{file_path})\n\n"
        message += f"---\n\n{content}"

        # If there were multiple matches, mention them
        if search_result['total_files'] > 1:
            message += f"\n\n---\n*Note: Found {search_result['total_files']} matching notes. Showing the best match.*"

        return {"success": True, "message": message}
    
    elif function_name == "update_note_section":
        file_path = arguments.get("file_path", "")
        section_name = arguments.get("section_name", "")
        new_content = arguments.get("new_content", "")
        result = update_note_section(file_path, section_name, new_content)
        if result['success']:
            return {
                "success": True,
                "message": f"✅ {result['message']}"
            }
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "replace_text_in_note":
        file_path = arguments.get("file_path", "")
        old_text = arguments.get("old_text", "")
        new_text = arguments.get("new_text", "")
        result = replace_note_content(file_path, old_text, new_text)
        if result['success']:
            return {
                "success": True,
                "message": f"✅ {result['message']}"
            }
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "research_and_save":
        topic = arguments.get("topic", "")
        save_location = arguments.get("save_location", "Reference")
        depth = arguments.get("depth", "quick")
        result = research_and_save(topic, save_location, depth)
        if result['success']:
            action = result.get('action', 'saved')
            return {
                "success": True,
                "message": f"{result['message']}\n📄 File: {result['path']}\n✨ Action: {action.replace('_', ' ').title()}\n\n📝 Preview:\n{result['summary']}"
            }
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "create_from_template":
        template_name = arguments.get("template_name", "")
        destination = arguments.get("destination", "")
        variables = arguments.get("variables", {})
        result = create_note_from_template(template_name, destination, variables)
        if result['success']:
            return {
                "success": True,
                "message": f"✅ Created note from template '{template_name}'\n📄 Location: {result['path']}\n🎯 Destination: {destination}",
                "path": result.get("path"),
                "file_path": result.get("absolute_path", ""),  # For verification
            }
        else:
            return {"success": False, "message": f"❌ Error creating from template: {result.get('error')}"}
    
    elif function_name == "list_templates":
        result = list_templates()
        if result['success']:
            if result['count'] == 0:
                return {
                    "success": True,
                    "message": "📋 No templates found. Create one with save_custom_template."
                }
            message = f"📋 Available templates ({result['count']}):\n\n"
            for template in result['templates']:
                message += f"  - **{template['name']}** ({template['size']} bytes)\n"
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "save_custom_template":
        template_name = arguments.get("template_name", "")
        content = arguments.get("content", "")
        result = create_custom_template(template_name, content)
        if result['success']:
            return {
                "success": True,
                "message": f"✅ {result['message']}"
            }
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "suggest_links":
        content = arguments.get("content", "")
        auto_apply = arguments.get("auto_apply", False)
        
        if auto_apply:
            result = auto_link_content(content)
            if result['success']:
                if result['count'] == 0:
                    return {
                        "success": True,
                        "message": "🔗 No linkable notes found in content."
                    }
                message = f"🔗 Added {result['count']} link(s):\n\n"
                for link in result['links_added']:
                    message += f"  - {link['text']} → {link['link']}\n"
                message += f"\n**Linked content:**\n{result['content']}"
                return {"success": True, "message": message}
        else:
            result = find_linkable_notes(content)
            if result['success']:
                if result['count'] == 0:
                    return {
                        "success": True,
                        "message": "🔗 No linkable notes found in content."
                    }
                message = f"🔗 Found {result['count']} potential link(s):\n\n"
                for suggestion in result['suggestions']:
                    message += f"  - '{suggestion['text']}' → {suggestion['link']} (links to {suggestion['target_path']})\n"
                return {"success": True, "message": message}
            else:
                return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "suggest_tags_for_note":
        file_path = arguments.get("file_path", "")
        auto_apply = arguments.get("auto_apply", False)
        
        # Read note content first
        from obsidian import read_daily_note, get_vault_path
        from pathlib import Path
        
        try:
            vault = get_vault_path()
            note_path = vault / file_path
            content = note_path.read_text(encoding='utf-8')
            
            # Extract existing tags from frontmatter
            existing_tags = []
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    for line in frontmatter.split('\n'):
                        if line.strip().startswith('tags:'):
                            tags_text = line.split('tags:', 1)[1].strip().strip('[]')
                            existing_tags = [t.strip().strip('"\'') for t in tags_text.split(',') if t.strip()]
            
            result = suggest_tags(content, existing_tags)
            
            if result['success']:
                if result['count'] == 0:
                    return {
                        "success": True,
                        "message": "🏷️ No new tags suggested (note already well-tagged)."
                    }
                
                suggested_tags = result['suggested_tags']
                
                if auto_apply:
                    apply_result = apply_tags_to_note(file_path, suggested_tags)
                    if apply_result['success']:
                        return {
                            "success": True,
                            "message": f"✅ {apply_result['message']}"
                        }
                else:
                    message = f"🏷️ Suggested tags for {file_path}:\n\n"
                    message += ", ".join(suggested_tags)
                    message += f"\n\nExisting tags: {', '.join(existing_tags) if existing_tags else 'None'}"
                    return {"success": True, "message": message}
            else:
                return {"success": False, "message": f"❌ Error: {result.get('error')}"}
        
        except Exception as e:
            return {"success": False, "message": f"❌ Error reading note: {str(e)}"}
    
    elif function_name == "find_orphaned_notes":
        result = find_orphaned_notes()
        if result['success']:
            if result['count'] == 0:
                return {
                    "success": True,
                    "message": "🎉 No orphaned notes! Your vault is well connected."
                }
            
            message = f"🔍 Found {result['count']} orphaned notes ({result['percentage']:.1f}% of vault):\n\n"
            for orphan in result['orphans'][:10]:  # Show first 10
                tags_str = f" [Tags: {', '.join(orphan['tags'])}]" if orphan['tags'] else ""
                message += f"  - **{orphan['title']}**{tags_str}\n    Path: {orphan['path']}\n"
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "suggest_note_connections":
        file_path = arguments.get("file_path")
        limit = arguments.get("limit", 5)
        result = suggest_connections(file_path, limit)
        if result['success']:
            vault_stats = result.get('vault_stats', {})
            
            if result['count'] == 0:
                # Provide helpful context about why no suggestions
                if vault_stats.get('total_notes', 0) < 3:
                    return {
                        "success": True,
                        "message": "💡 Your vault has very few notes yet. Create more content to discover connections!\n\nNo suggestions available (vault too small)."
                    }
                elif vault_stats.get('has_tags', 0) == 0:
                    return {
                        "success": True,
                        "message": "💡 No connections found. Try adding tags to your notes to help discover relationships!\n\nTip: Use the 'suggest_tags_for_note' function to auto-tag existing notes."
                    }
                else:
                    return {
                        "success": True,
                        "message": "💡 No obvious connections found. Your notes might already be well linked, or they cover different topics.\n\nConsider: Creating notes on similar topics, or adding more shared tags."
                    }
            
            message = f"💡 Found {result['count']} potential connection(s):\n\n"
            for suggestion in result['suggestions']:
                if file_path:
                    message += f"  → **{suggestion['target_title']}** (score: {suggestion['score']})\n"
                else:
                    message += f"  **{suggestion.get('source_title', 'Note')}** ↔ **{suggestion['target_title']}** (score: {suggestion['score']})\n"
                message += f"    Reasons: {', '.join(suggestion['reasons'])}\n\n"
            
            # Add vault context
            message += f"\n📊 Vault context: {vault_stats['total_notes']} notes, {vault_stats['has_tags']} with tags, {vault_stats['has_links']} with links"
            
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "analyze_vault_clusters":
        result = analyze_clusters()
        if result['success']:
            if result['total_clusters'] == 0:
                return {
                    "success": True,
                    "message": "📊 No clusters found (notes don't have tags yet)."
                }
            
            message = f"📊 Found {result['total_clusters']} knowledge clusters. Top 10:\n\n"
            for cluster in result['clusters']:
                message += f"  **#{cluster['tag']}** ({cluster['size']} notes)\n"
                for note in cluster['notes'][:3]:  # Show first 3 notes
                    message += f"    - {note['title']}\n"
                if cluster['size'] > 3:
                    message += f"    ... and {cluster['size'] - 3} more\n"
                message += "\n"
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "get_note_network":
        file_path = arguments.get("file_path", "")
        depth = arguments.get("depth", 1)
        result = get_note_neighbors(file_path, depth)
        if result['success']:
            if result['count'] == 0:
                return {
                    "success": True,
                    "message": f"🕸️ '{file_path}' has no connected notes (it's isolated)."
                }
            
            message = f"🕸️ Network for **{result['note']}** ({result['count']} connections):\n\n"
            
            # Group by relationship
            links_to = [n for n in result['neighbors'] if n['relationship'] == 'links_to']
            linked_from = [n for n in result['neighbors'] if n['relationship'] == 'linked_from']
            
            if links_to:
                message += "**Links to:**\n"
                for neighbor in links_to[:10]:
                    message += f"  → {neighbor['title']}\n"
            
            if linked_from:
                message += "\n**Linked from:**\n"
                for neighbor in linked_from[:10]:
                    message += f"  ← {neighbor['title']}\n"
            
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "create_scheduled_task":
        name = arguments.get("name", "")
        schedule = arguments.get("schedule", "")
        action = arguments.get("action", "")
        parameters = arguments.get("parameters", {})
        result = create_scheduled_task(name, schedule, action, parameters)
        if result['success']:
            return {
                "success": True,
                "message": f"✅ {result['message']} (ID: {result['task_id']})\nSchedule: {schedule}"
            }
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}
    
    elif function_name == "list_scheduled_tasks":
        result = list_scheduled_tasks()
        if result['success']:
            if result['count'] == 0:
                return {
                    "success": True,
                    "message": "📅 No scheduled tasks yet. Create one with create_scheduled_task."
                }
            
            message = f"📅 Scheduled tasks ({result['count']}):\n\n"
            for task in result['tasks']:
                status = "✅ Enabled" if task.get('enabled', True) else "⏸️ Disabled"
                last_run = task.get('last_run', 'Never')
                message += f"  **{task['name']}** (ID: {task['id']}) - {status}\n"
                message += f"    Schedule: {task['schedule']}\n"
                message += f"    Action: {task['action']}\n"
                message += f"    Last run: {last_run}\n\n"
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error', 'Unknown error')}"}

    elif function_name == "save_image_to_vault":
        # This function requires image data to be passed through the context
        # The image is typically attached to the conversation and stored temporarily
        from flask import g
        from services.obsidian_service import ObsidianService

        filename = arguments.get("filename", "")
        embed_in_note = arguments.get("embed_in_note")
        section = arguments.get("section")

        # Get image data from Flask g context (set by /ask-stream when image is attached)
        image_base64 = getattr(g, 'attached_image_base64', None)
        image_type = getattr(g, 'attached_image_type', 'image/png')

        if not image_base64:
            return {
                "success": False,
                "message": "❌ No image attached to this conversation. Please attach an image first and then ask me to save it."
            }

        # Decode base64 to bytes
        import base64
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as e:
            return {
                "success": False,
                "message": f"❌ Failed to decode image data: {str(e)}"
            }

        # Determine file extension from MIME type if filename doesn't have one
        if filename and '.' not in filename:
            ext_map = {
                'image/png': '.png',
                'image/jpeg': '.jpg',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'image/svg+xml': '.svg',
                'image/bmp': '.bmp'
            }
            filename += ext_map.get(image_type, '.png')

        obs = ObsidianService()
        result = obs.save_image(
            image_bytes=image_bytes,
            filename=filename,
            embed_in_note=embed_in_note,
            section=section
        )

        if result.get('success'):
            message_parts = [f"✅ Saved image: `{result.get('filename')}`"]
            message_parts.append(f"📁 Location: `{result.get('path')}`")
            message_parts.append(f"🔗 Embed with: `{result.get('markdown')}`")

            if result.get('embedded_in'):
                message_parts.append(f"📝 Embedded in: `{result.get('embedded_in')}`")
                if result.get('embedded_section'):
                    message_parts.append(f"   Under section: {result.get('embedded_section')}")
                if result.get('created_note'):
                    message_parts.append(f"   (Note was created)")
                if result.get('created_section'):
                    message_parts.append(f"   (Section was created)")

            return {
                "success": True,
                "message": "\n".join(message_parts),
                "path": result.get('path'),
                "filename": result.get('filename'),
                "markdown": result.get('markdown')
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to save image: {result.get('error', 'Unknown error')}"
            }

    elif function_name == "update_note":
        file_path = arguments.get("file_path", "")
        new_content = arguments.get("new_content", "")
        mode = arguments.get("mode", "overwrite")
        old_text = arguments.get("old_text")
        try:
            from pathlib import Path
            path_obj = Path(file_path)
            folder = str(path_obj.parent)
            if folder == ".":
                folder = ""
            filename = path_obj.name

            # Allow bare filenames by resolving uniquely within the vault
            if not folder:
                if not filename:
                    return {
                        "success": False,
                        "message": "❌ Error: file_path is required (e.g., 'Reference/Note.md' or 'Note.md')"
                    }
                from obsidian import get_vault_path
                vault = get_vault_path()
                matches = [p for p in Path(vault).rglob(filename) if p.is_file()]
                if not matches:
                    return {
                        "success": False,
                        "message": f"❌ Error: Note '{filename}' not found in vault"
                    }
                if len(matches) > 1:
                    options = [str(p.relative_to(vault)) for p in matches[:10]]
                    more = "" if len(matches) <= 10 else f" (+{len(matches)-10} more)"
                    return {
                        "success": False,
                        "message": "❌ Error: Multiple notes match that name; specify a folder.",
                        "options": options,
                        "note": filename,
                        "more": more
                    }
                # Exactly one match; use its folder/path
                match = matches[0]
                file_path = str(match.relative_to(vault))
                folder = str(match.parent.relative_to(vault))

            # Final safety: still no folder? bail
            if not folder or folder == ".":
                return {
                    "success": False,
                    "message": "❌ Error: Could not determine folder for note. Please specify the folder (e.g., 'Reference/Note.md')."
                }

            if mode == "replace":
                if not old_text:
                    return {
                        "success": False,
                        "message": "❌ Error: 'old_text' is required when mode='replace'"
                    }
                result = replace_note_content(file_path, old_text, new_content)
            elif mode in ("overwrite", "append"):
                # Use create_note to handle safe paths and return absolute_path for verification
                from obsidian import create_note
                result = create_note(new_content, folder, filename, mode=mode)
            else:
                return {
                    "success": False,
                    "message": f"❌ Error: Invalid mode '{mode}'. Use 'overwrite', 'append', or 'replace'."
                }

            if result.get('success'):
                return {
                    "success": True,
                    "message": f"✅ Updated {file_path}",
                    "path": result.get("path", file_path),
                    "file_path": result.get("absolute_path", ""),  # For verification
                    "mode": mode
                }
            else:
                return {"success": False, "message": f"❌ Error: {result.get('error')}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Error updating note: {str(e)}"}

    elif function_name == "rename_note":
        file_path = arguments.get("file_path", "")
        new_title = arguments.get("new_title", "")
        try:
            from pathlib import Path
            vault_path = get_vault_path()
            old_path = Path(vault_path) / file_path
            if not old_path.exists():
                return {"success": False, "message": f"❌ Note not found: {file_path}"}
            new_path = old_path.parent / f"{new_title}.md"
            old_path.rename(new_path)
            return {"success": True, "message": f"✅ Renamed to {new_title}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Error renaming note: {str(e)}"}

    elif function_name == "move_note":
        file_path = arguments.get("file_path", "")
        destination_folder = arguments.get("destination_folder", "")
        try:
            from pathlib import Path
            vault_path = get_vault_path()
            old_path = Path(vault_path) / file_path
            if not old_path.exists():
                return {"success": False, "message": f"❌ Note not found: {file_path}"}
            dest_path = Path(vault_path) / destination_folder
            if not dest_path.is_dir():
                return {"success": False, "message": f"❌ Destination folder not found: {destination_folder}"}
            new_path = dest_path / old_path.name
            old_path.rename(new_path)
            return {"success": True, "message": f"✅ Moved to {destination_folder}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Error moving note: {str(e)}"}

    elif function_name == "list_folder":
        folder_name = arguments.get("folder_name", "")
        result = list_folder_contents(folder_name)
        if result.get('success'):
            contents = result.get('contents', [])
            message = f"📁 Contents of {folder_name}:\n" + "\n".join(contents)
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": f"❌ Error: {result.get('error')}"}

    elif function_name == "add_tags":
        file_path = arguments.get("file_path", "")
        tags = arguments.get("tags", [])
        mode = arguments.get("mode", "add")
        try:
            result = apply_tags_to_note(file_path, tags)
            if result.get('success'):
                return {"success": True, "message": f"✅ Added tags: {', '.join(tags)}"}
            else:
                return {"success": False, "message": f"❌ Error: {result.get('error')}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Error adding tags: {str(e)}"}

    elif function_name == "get_today_tasks":
        date = arguments.get("date")
        try:
            result = read_daily_note(date)
            if result['success']:
                content = result['content']
                # Extract Tasks section
                lines = content.split('\n')
                tasks = []
                in_tasks = False
                for line in lines:
                    if '# Tasks' in line or '## Tasks' in line:
                        in_tasks = True
                        continue
                    if in_tasks and line.strip().startswith('#'):
                        break
                    if in_tasks and line.strip().startswith('- '):
                        tasks.append(line.strip())
                task_text = "\n".join(tasks) if tasks else "No tasks found"
                return {"success": True, "message": f"📋 Tasks for {date or 'today'}:\n{task_text}", "tasks": tasks}
            else:
                return {"success": False, "message": f"❌ Error: {result.get('error')}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Error reading tasks: {str(e)}"}

    elif function_name == "find_related_notes":
        file_path = arguments.get("file_path", "")
        limit = arguments.get("limit", 5)
        try:
            result = suggest_connections(file_path, limit=limit)
            if result.get('success'):
                connections = result.get('connections', [])
                message = f"🔗 Related notes to {file_path}:\n" + "\n".join(f"- {c}" for c in connections)
                return {"success": True, "message": message}
            else:
                return {"success": False, "message": f"❌ Error: {result.get('error')}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Error finding related notes: {str(e)}"}

    elif function_name == "create_link":
        source_file = arguments.get("source_file", "")
        target_file = arguments.get("target_file", "")
        link_text = arguments.get("link_text") or target_file
        try:
            # Read source file
            source_result = read_note(source_file)
            if not source_result.get('success'):
                return {"success": False, "message": f"❌ Source file not found: {source_file}"}
            
            source_content = source_result.get('content', '')
            # Create markdown link
            link = f"[[{target_file}|{link_text}]]"
            new_content = source_content + f"\n\nRelated: {link}"
            
            # Update source file
            update_result = replace_note_content(source_file, "append", link)
            if update_result.get('success'):
                return {"success": True, "message": f"✅ Created link: {link}"}
            else:
                return {"success": False, "message": f"❌ Error creating link: {update_result.get('error')}"}
        except Exception as e:
            return {"success": False, "message": f"❌ Error: {str(e)}"}
    else:
        return {"success": False, "message": f"❌ Unknown function: {function_name}"}

