"""
Microsoft To Do function definitions for LLM function calling.

Provides LLM-callable functions for managing Microsoft To Do tasks.
Similar pattern to obsidian_functions.py but for To Do API.
"""

import structlog

logger = structlog.get_logger()


def get_todo_functions():
    """
    Generate TODO_FUNCTIONS for LLM function calling.
    """
    return [
        {
            "name": "create_todo_task",
            "description": "Add a task to the user's Microsoft To Do list. USE THIS when user says: 'add to my todo list', 'add to my task list', 'remind me to', 'I need to'. This creates tasks in Microsoft To Do, NOT in Obsidian notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Task title (required, e.g., 'Call the client', 'Review proposal')"
                    },
                    "body": {
                        "type": "string",
                        "description": "Task description/details (optional, e.g., 'Review quarterly report, focus on Q3 numbers')"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in YYYY-MM-DD format (optional, e.g., '2026-01-15')"
                    }
                },
                "required": ["title"]
            }
        },
        {
            "name": "get_todo_tasks",
            "description": "List tasks from the user's Microsoft To Do list. USE THIS when user says: 'what's on my todo list', 'show my tasks', 'my task list'. Returns tasks from Microsoft To Do, NOT from Obsidian.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_completed": {
                        "type": "boolean",
                        "description": "Include completed tasks (default: false, only shows incomplete)"
                    }
                }
            }
        },
        {
            "name": "mark_todo_complete",
            "description": "Mark a task as complete in your Microsoft To Do list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID of the task to mark complete (required)"
                    },
                    "task_title": {
                        "type": "string",
                        "description": "Title of the task (for confirmation/logging, optional)"
                    }
                },
                "required": ["task_id"]
            }
        },
        {
            "name": "update_todo_task",
            "description": "Update a task's title, description, or due date in your Microsoft To Do list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID of the task to update (required)"
                    },
                    "title": {
                        "type": "string",
                        "description": "New task title (optional)"
                    },
                    "body": {
                        "type": "string",
                        "description": "New task description (optional)"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "New due date in YYYY-MM-DD format (optional)"
                    }
                },
                "required": ["task_id"]
            }
        },
        {
            "name": "delete_todo_task",
            "description": "Delete a task from your Microsoft To Do list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID of the task to delete (required)"
                    },
                    "task_title": {
                        "type": "string",
                        "description": "Title of the task (for confirmation/logging, optional)"
                    }
                },
                "required": ["task_id"]
            }
        },
        {
            "name": "authorize_microsoft_account",
            "description": "Get authorization URL to connect your Microsoft account. Run this if you haven't authorized yet.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "sync_todo_to_obsidian",
            "description": "Sync your Microsoft To Do tasks to an Obsidian markdown file. Only syncs incomplete tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file to sync to (default: 'Task-List.md')"
                    }
                }
            }
        }
    ]


# Alias for consistency with other function modules
TODO_FUNCTIONS = get_todo_functions()


def execute_todo_function(function_name: str, arguments: dict) -> dict:
    """
    Execute a Microsoft To Do function based on LLM function call.

    Args:
        function_name: Name of the function to execute
        arguments: Dictionary of function arguments

    Returns:
        dict: Result of the function execution
    """
    print(f"[TODO] execute_todo_function called with: {function_name}", flush=True)

    from microsoft_todo_service import MicrosoftToDoService
    from user_settings_db import UserSettingsDB
    from config import get_settings
    from utils.auth_utils import get_current_user

    # Get current user and their OAuth token cache
    try:
        print(f"[TODO] Getting current user...", flush=True)
        user = get_current_user()
        print(f"[TODO] Current user: {user}", flush=True)
        if not user:
            return {
                "success": False,
                "message": "❌ Not authenticated. Please log in first."
            }

        # Extract user_id (could be dict with 'user_id' key or direct value)
        if isinstance(user, dict):
            user_id = user.get('user_id') or user.get('id')
        else:
            user_id = user
        print(f"[TODO] user_id extracted: {user_id}", flush=True)

        settings = get_settings()
        print(f"[TODO] Settings loaded", flush=True)

        user_db = UserSettingsDB(settings.chat_db_path)
        print(f"[TODO] UserSettingsDB initialized", flush=True)

        user_settings = user_db.get_user_settings(user_id)
        print(f"[TODO] User settings retrieved: {user_settings}", flush=True)

        preferences = user_settings.get('preferences', {})
        print(f"[TODO] Preferences: {preferences}", flush=True)

        token_cache = preferences.get('microsoft_todo_token_cache') if preferences else None
        print(f"[TODO] Token cache found: {bool(token_cache)}", flush=True)

        # Initialize service with user's token cache
        print(f"[TODO] Initializing service...", flush=True)
        service = MicrosoftToDoService(user_id=user_id, token_cache_data=token_cache)
        print(f"[TODO] Service initialized successfully", flush=True)

    except Exception as e:
        logger.error("todo_service_init_failed", error=str(e), exc_info=True)
        return {
            "success": False,
            "message": f"❌ Error initializing To Do service: {str(e)}"
        }

    # ========== Authorization ==========

    if function_name == "authorize_microsoft_account":
        try:
            if service.is_authenticated():
                # Check user profile to confirm auth
                success, profile, error = service.get_user_profile()
                if success:
                    email = profile.get('mail', profile.get('userPrincipalName', 'Unknown'))
                    return {
                        "success": True,
                        "message": f"✓ Already connected to Microsoft account: {email}"
                    }

            # Generate authorization URL
            auth_url = service.get_authorization_url()
            return {
                "success": False,  # Set to False so user knows they need to act
                "message": "🔐 Click this link to authorize Microsoft To Do: https://www.your-domain.com/auth/authorize-microsoft\n\nYou'll be directed to Microsoft's login page. Sign in with your personal Microsoft account and grant the requested permissions. You'll automatically be redirected back here after authorization.",
                "requires_action": True
            }
        except Exception as e:
            logger.error("authorization_url_failed", error=str(e))
            return {
                "success": False,
                "message": f"❌ Error generating authorization URL: {str(e)}"
            }

    # ========== Check Authentication for Other Functions ==========

    if not service.is_authenticated():
        return {
            "success": False,
            "message": "🔐 You need to authorize Microsoft To Do first. Click this link to authorize: https://www.your-domain.com/auth/authorize-microsoft\n\nAfter signing in with your personal Microsoft account and granting permissions, come back and try again.",
            "requires_action": True
        }

    # ========== Create Task ==========

    if function_name == "create_todo_task":
        title = arguments.get("title", "").strip()
        body = arguments.get("body", "").strip() or None
        due_date = arguments.get("due_date", "").strip() or None

        if not title:
            return {
                "success": False,
                "message": "❌ Task title is required"
            }

        try:
            success, task, error = service.create_task(
                title=title,
                body=body,
                due_date=due_date
            )

            if success:
                task_id = task.get('id')
                due_str = f" (due: {due_date})" if due_date else ""
                return {
                    "success": True,
                    "message": f"✅ Task created: {title}{due_str}",
                    "task_id": task_id
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to create task: {error}"
                }
        except Exception as e:
            logger.error("create_task_exception", error=str(e))
            return {
                "success": False,
                "message": f"❌ Error creating task: {str(e)}"
            }

    # ========== Get Tasks ==========

    if function_name == "get_todo_tasks":
        include_completed = arguments.get("include_completed", False)

        try:
            success, tasks, error = service.get_tasks(only_incomplete=not include_completed)

            if success:
                if not tasks:
                    return {
                        "success": True,
                        "message": "✓ No tasks to show. You're all caught up! 🎉"
                    }

                # Format tasks for display
                task_list = []
                for task in tasks:
                    task_title = task.get('title', 'Untitled')
                    task_id = task.get('id')
                    due = task.get('dueDateTime', {}).get('dateTime')
                    due_str = f" (due: {due[:10]})" if due else ""

                    task_list.append(f"• {task_title}{due_str} [ID: {task_id[:8]}...]")

                tasks_str = "\n".join(task_list)
                return {
                    "success": True,
                    "message": f"📋 Your tasks:\n{tasks_str}",
                    "tasks": tasks
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to get tasks: {error}"
                }
        except Exception as e:
            logger.error("get_tasks_exception", error=str(e))
            return {
                "success": False,
                "message": f"❌ Error getting tasks: {str(e)}"
            }

    # ========== Mark Complete ==========

    if function_name == "mark_todo_complete":
        task_id = arguments.get("task_id", "").strip()
        task_title = arguments.get("task_title", "Task")

        if not task_id:
            return {
                "success": False,
                "message": "❌ Task ID is required"
            }

        try:
            success, task, error = service.update_task(task_id=task_id, is_completed=True)

            if success:
                return {
                    "success": True,
                    "message": f"✅ Marked complete: {task_title}"
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to mark task complete: {error}"
                }
        except Exception as e:
            logger.error("mark_complete_exception", error=str(e))
            return {
                "success": False,
                "message": f"❌ Error marking task complete: {str(e)}"
            }

    # ========== Update Task ==========

    if function_name == "update_todo_task":
        task_id = arguments.get("task_id", "").strip()
        title = arguments.get("title", "").strip() or None
        body = arguments.get("body", "").strip() or None
        due_date = arguments.get("due_date", "").strip() or None

        if not task_id:
            return {
                "success": False,
                "message": "❌ Task ID is required"
            }

        if not any([title, body, due_date]):
            return {
                "success": False,
                "message": "❌ At least one field (title, body, or due_date) must be provided"
            }

        try:
            success, task, error = service.update_task(
                task_id=task_id,
                title=title,
                body=body
            )

            if success:
                return {
                    "success": True,
                    "message": f"✅ Task updated"
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to update task: {error}"
                }
        except Exception as e:
            logger.error("update_task_exception", error=str(e))
            return {
                "success": False,
                "message": f"❌ Error updating task: {str(e)}"
            }

    # ========== Delete Task ==========

    if function_name == "delete_todo_task":
        task_id = arguments.get("task_id", "").strip()
        task_title = arguments.get("task_title", "Task")

        if not task_id:
            return {
                "success": False,
                "message": "❌ Task ID is required"
            }

        try:
            success, error = service.delete_task(task_id=task_id)

            if success:
                return {
                    "success": True,
                    "message": f"🗑️ Deleted: {task_title}"
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to delete task: {error}"
                }
        except Exception as e:
            logger.error("delete_task_exception", error=str(e))
            return {
                "success": False,
                "message": f"❌ Error deleting task: {str(e)}"
            }

    # ========== Sync to Obsidian ==========

    if function_name == "sync_todo_to_obsidian":
        file_name = arguments.get("file_name", "Task-List.md")

        try:
            # Fetch incomplete tasks from Microsoft To Do
            success, tasks, error = service.get_tasks(only_incomplete=True)

            if not success:
                return {
                    "success": False,
                    "message": f"❌ Failed to fetch tasks from Microsoft To Do: {error}"
                }

            if not tasks:
                return {
                    "success": True,
                    "message": "✓ No incomplete tasks in Microsoft To Do"
                }

            # Format tasks as Obsidian Tasks plugin compatible markdown (kitchen display - minimal header)
            from datetime import datetime
            markdown_lines = []

            for task in tasks:
                title = task.get('title', 'Untitled')

                # Add due date if present (Obsidian Tasks plugin format)
                due_datetime = task.get('dueDateTime', {}).get('dateTime')
                due_str = ""
                if due_datetime:
                    # Extract date portion (YYYY-MM-DD)
                    due_date = due_datetime[:10]
                    due_str = f" 📅 {due_date}"

                # Format as unchecked task
                markdown_lines.append(f"- [ ] {title}{due_str}")

                # Add task notes/body as indented text if present
                body_content = task.get('body', {}).get('content', '').strip()
                if body_content:
                    # Indent body content
                    for line in body_content.split('\n'):
                        if line.strip():
                            markdown_lines.append(f"    {line}")

            # Add last synced timestamp at the bottom
            markdown_lines.append("")
            markdown_lines.append(f"*Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

            markdown_content = '\n'.join(markdown_lines)

            # Write to Obsidian vault
            from services.obsidian_service import ObsidianService
            from pathlib import Path
            import os

            obs_service = ObsidianService()

            # Use create_note with mode="overwrite" to replace file contents
            # Pass full file path (including .md extension) for vault root location
            result = obs_service.create_note(
                content=markdown_content,
                destination=file_name,  # Full path to file at vault root
                filename=None,  # filename ignored when destination ends in .md
                mode="overwrite"
            )

            if result.get('success'):
                file_path = result.get('path', file_name)

                # Set file permissions to allow Obsidian access
                try:
                    full_path = Path("/root/obsidian-vault") / file_name
                    if full_path.exists():
                        os.chmod(full_path, 0o666)
                except Exception as perm_error:
                    logger.warning("permission_set_failed", error=str(perm_error))

                return {
                    "success": True,
                    "message": f"✅ Synced {len(tasks)} tasks to {file_path}",
                    "task_count": len(tasks),
                    "file_path": file_path
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Failed to write to Obsidian: {result.get('error', 'Unknown error')}"
                }

        except Exception as e:
            logger.error("sync_to_obsidian_exception", error=str(e), exc_info=True)
            return {
                "success": False,
                "message": f"❌ Error syncing to Obsidian: {str(e)}"
            }

    # Unknown function
    return {
        "success": False,
        "message": f"❌ Unknown function: {function_name}"
    }
