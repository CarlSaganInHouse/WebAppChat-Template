#!/usr/bin/env python3
"""
Create Daily Note - Generates today's daily note from template

Creates a daily note for the current date (in America/New_York timezone)
using the template at 90-Meta/Templates/daily_note.md.

Usage:
    python3 /root/WebAppChat/scripts/create_daily_note.py
    python3 /root/WebAppChat/scripts/create_daily_note.py --tomorrow
    python3 /root/WebAppChat/scripts/create_daily_note.py --date 2026-01-15

Cron entry (add to LXC ${LXC_ID}):
    0 1 * * * /usr/bin/python3 /root/create_daily_note.py >> /var/log/daily_note.log 2>&1
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# Configuration - env override available
VAULT_PATH = Path(os.getenv("VAULT_PATH", "/root/obsidian-vault"))
TEMPLATE_PATH = VAULT_PATH / "90-Meta/Templates/daily_note.md"
DAILY_NOTES_PATH = VAULT_PATH / "60-Calendar/Daily"
TIMEZONE = ZoneInfo("America/New_York")

# File ownership (for Obsidian access)
VAULT_UID = 1002  # homelab user
VAULT_GID = 1002  # homelab group


def log(message: str, level: str = "INFO"):
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def get_target_date(tomorrow: bool = False, date_str: str = None) -> datetime:
    """
    Get the target date for the daily note.

    Args:
        tomorrow: If True, create for tomorrow instead of today
        date_str: Specific date in YYYY-MM-DD format

    Returns:
        datetime object in the configured timezone
    """
    if date_str:
        # Parse provided date
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=TIMEZONE)

    # Get current time in timezone
    now = datetime.now(TIMEZONE)

    if tomorrow:
        now = now + timedelta(days=1)

    return now


def replace_placeholders(template: str, target_date: datetime) -> str:
    """
    Replace template placeholders with actual values.

    Supported placeholders:
        {{date}} → YYYY-MM-DD
        {{weekday}} → Monday, Tuesday, etc.
        {{date_long}} → YYYY-MM-DD, Monday
    """
    date_str = target_date.strftime("%Y-%m-%d")
    weekday = target_date.strftime("%A")
    date_long = f"{date_str}, {weekday}"

    content = template
    content = content.replace("{{date}}", date_str)
    content = content.replace("{{weekday}}", weekday)
    content = content.replace("{{date_long}}", date_long)

    return content


def fix_ownership(path: Path):
    """Set file ownership to homelab:homelab for Obsidian access."""
    try:
        os.chown(path, VAULT_UID, VAULT_GID)
    except PermissionError:
        log(f"Could not chown {path} - running as non-root?", "WARN")
    except Exception as e:
        log(f"chown error for {path}: {e}", "WARN")


def main():
    parser = argparse.ArgumentParser(description="Create daily note from template")
    parser.add_argument('--tomorrow', action='store_true', help="Create note for tomorrow instead of today")
    parser.add_argument('--date', type=str, help="Create note for specific date (YYYY-MM-DD)")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be done without creating")
    args = parser.parse_args()

    log("=== Create Daily Note Started ===")

    # Verify template exists
    if not TEMPLATE_PATH.exists():
        log(f"Template not found: {TEMPLATE_PATH}", "ERROR")
        log("Create the template first at 90-Meta/Templates/daily_note.md", "ERROR")
        sys.exit(1)

    # Ensure daily notes directory exists
    DAILY_NOTES_PATH.mkdir(parents=True, exist_ok=True)

    # Get target date
    target_date = get_target_date(tomorrow=args.tomorrow, date_str=args.date)
    date_str = target_date.strftime("%Y-%m-%d")

    log(f"Target date: {date_str} ({target_date.strftime('%A')})")

    # Check if note already exists
    note_path = DAILY_NOTES_PATH / f"{date_str}.md"

    if note_path.exists():
        log(f"Daily note already exists: {note_path}")
        log("=== Create Daily Note Complete (no action needed) ===")
        return

    # Read template
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    log(f"Loaded template ({len(template)} chars)")

    # Replace placeholders
    content = replace_placeholders(template, target_date)

    if args.dry_run:
        log("DRY RUN - would create:", "INFO")
        print(f"Path: {note_path}")
        print("Content:")
        print("-" * 40)
        print(content)
        print("-" * 40)
        log("=== Create Daily Note Complete (dry run) ===")
        return

    # Write note
    note_path.write_text(content, encoding='utf-8')
    log(f"Created: {note_path}")

    # Fix ownership
    fix_ownership(note_path)
    log(f"Set ownership to {VAULT_UID}:{VAULT_GID}")

    log("=== Create Daily Note Complete ===")


if __name__ == "__main__":
    main()
