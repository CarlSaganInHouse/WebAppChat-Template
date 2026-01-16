#!/usr/bin/env python3
"""
Microsoft To Do → Obsidian Sync Script
Runs via cron (e.g., every 15 minutes) to sync Microsoft To Do tasks to Obsidian vault.
Syncs only for the specified user (default: user 2).

Usage:
    python3 scripts/sync_todo_to_obsidian.py              # Sync for user 2 (default)
    python3 scripts/sync_todo_to_obsidian.py --user 1    # Sync for specific user
    python3 scripts/sync_todo_to_obsidian.py --dry-run   # Show what would be done
"""

import sys
import os
import argparse
import json
from datetime import datetime
from pathlib import Path

# Add WebAppChat root to path so we can import its modules
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

def sync_todo_to_obsidian(user_id=2, dry_run=False, filename=None):
    """
    Sync Microsoft To Do tasks for a specific user to Obsidian vault.

    Args:
        user_id: User ID to sync for (default: 2, usually the first/admin user)
        dry_run: If True, show what would be done without making changes
        filename: Output filename. Defaults to settings.todo_sync_path.
    """
    try:
        from config import get_settings
        from microsoft_todo_service import MicrosoftToDoService
        from services.obsidian_service import ObsidianService
        from user_settings_db import UserSettingsDB

        settings = get_settings()

        # Use configured path if not specified
        if filename is None:
            filename = settings.todo_sync_path

        # Get user settings and token cache
        user_db = UserSettingsDB(settings.chat_db_path)
        user_settings = user_db.get_user_settings(user_id)

        if not user_settings:
            print(f"User {user_id} not found in database")
            return False

        preferences = user_settings.get('preferences', {})
        token_cache = preferences.get('microsoft_todo_token_cache')

        if not token_cache:
            print(f"No Microsoft To Do authorization found for user {user_id}")
            print("User must authorize first via: https://www.your-domain.com/auth/authorize-microsoft")
            return False

        # Initialize Microsoft To Do service
        service = MicrosoftToDoService(user_id=user_id, token_cache_data=token_cache)

        # Fetch incomplete tasks
        success, tasks, error = service.get_tasks(only_incomplete=True)

        if not success:
            print(f"Failed to fetch tasks: {error}")
            return False

        if not tasks:
            print(f"No incomplete tasks for user {user_id}")
            if not dry_run:
                # Still update the file to show last sync time
                markdown_content = f"""(No incomplete tasks)

*Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
                obs_service = ObsidianService()
                result = obs_service.create_note(
                    content=markdown_content,
                    destination=filename,
                    filename=None,
                    mode="overwrite"
                )
                if result.get('success'):
                    print(f"✓ Updated {filename} (no tasks)")
            return True

        # Format tasks as Obsidian markdown (kitchen display - minimal header)
        markdown_lines = []

        for task in tasks:
            title = task.get('title', 'Untitled')

            # Add due date if present
            due_datetime = task.get('dueDateTime', {}).get('dateTime')
            due_str = ""
            if due_datetime:
                due_date = due_datetime[:10]
                due_str = f" 📅 {due_date}"

            # Format as unchecked task
            markdown_lines.append(f"- [ ] {title}{due_str}")

            # Add task notes/body as indented text
            body_content = task.get('body', {}).get('content', '').strip()
            if body_content:
                for line in body_content.split('\n'):
                    if line.strip():
                        markdown_lines.append(f"    {line}")

        # Add last synced timestamp at the bottom
        markdown_lines.append("")
        markdown_lines.append(f"*Last synced: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        markdown_content = '\n'.join(markdown_lines)

        if dry_run:
            print(f"Would write {len(tasks)} tasks to {filename}:")
            print(markdown_content)
            return True

        # Write to Obsidian vault
        obs_service = ObsidianService()
        # Pass full file path (including .md extension) for vault root location
        result = obs_service.create_note(
            content=markdown_content,
            destination=filename,  # Full path to file at vault root
            filename=None,  # filename ignored when destination ends in .md
            mode="overwrite"
        )

        if result.get('success'):
            file_path = result.get('path', filename)

            # Set file permissions
            try:
                full_path = settings.vault_path / filename
                if full_path.exists():
                    os.chmod(full_path, 0o666)
            except Exception as e:
                print(f"Warning: Could not set file permissions: {e}")

            print(f"✓ Synced {len(tasks)} tasks to {file_path}")
            return True
        else:
            print(f"✗ Failed to write to vault: {result.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description='Sync Microsoft To Do tasks to Obsidian vault')
    parser.add_argument('--user', type=int, default=2, help='User ID to sync for (default: 2)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--file', type=str, default=None, help='Output filename (default: from settings.todo_sync_path)')

    args = parser.parse_args()

    success = sync_todo_to_obsidian(
        user_id=args.user,
        dry_run=args.dry_run,
        filename=args.file
    )

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
