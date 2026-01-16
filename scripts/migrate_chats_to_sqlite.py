#!/usr/bin/env python3
"""
Migration script: JSON chats → SQLite database

This script migrates chat history from JSON files to SQLite database.
It's safe to run multiple times (idempotent) - existing chats in SQLite won't be duplicated.

Usage:
    python scripts/migrate_chats_to_sqlite.py [--dry-run] [--force]

Options:
    --dry-run    Show what would be migrated without actually doing it
    --force      Overwrite existing chats in SQLite (default: skip existing)
    --chats-dir  Path to chats directory (default: chats)
    --db-path    Path to SQLite database (default: chats.sqlite3)
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_db import ChatDatabase
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)
logger = structlog.get_logger()


def load_json_chat(file_path: Path) -> Dict[str, Any] | None:
    """Load a chat from JSON file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("failed_to_load_json", file=str(file_path), error=str(e))
        return None


def migrate_chat(chat: Dict[str, Any], db: ChatDatabase, force: bool = False) -> bool:
    """
    Migrate a single chat to SQLite.

    Args:
        chat: Chat dictionary from JSON
        db: ChatDatabase instance
        force: If True, overwrite existing chat

    Returns:
        True if migrated, False if skipped or failed
    """
    chat_id = chat["id"]

    # Check if chat already exists
    existing = db.get_chat(chat_id)
    if existing and not force:
        logger.info("chat_already_exists_skipping", chat_id=chat_id, title=chat.get("title"))
        return False

    # Delete existing if force is enabled
    if existing and force:
        db.delete_chat(chat_id)
        logger.info("overwriting_existing_chat", chat_id=chat_id)

    # Extract chat metadata
    title = chat.get("title", "New chat")
    model = chat.get("model")
    created_at = chat.get("created_at")
    updated_at = chat.get("updated_at")
    messages = chat.get("messages", [])
    meta = chat.get("meta", {})
    budget_usd = meta.get("budget_usd")
    spent_usd = meta.get("spent_usd", 0.0)
    tags = meta.get("tags", [])

    try:
        # Create chat
        db.create_chat(
            chat_id=chat_id,
            title=title,
            model=model,
            budget_usd=budget_usd,
            tags=tags
        )

        # Override timestamps to preserve original
        if created_at or updated_at:
            conn = db.get_conn()
            if created_at and updated_at:
                conn.execute(
                    "UPDATE chats SET created_at = ?, updated_at = ? WHERE id = ?",
                    (created_at, updated_at, chat_id)
                )
            elif created_at:
                conn.execute(
                    "UPDATE chats SET created_at = ? WHERE id = ?",
                    (created_at, chat_id)
                )
            elif updated_at:
                conn.execute(
                    "UPDATE chats SET updated_at = ? WHERE id = ?",
                    (updated_at, chat_id)
                )
            conn.commit()
            conn.close()

        # Update spent_usd if present
        if spent_usd:
            db.update_chat(chat_id, spent_usd=spent_usd)

        # Add messages
        if messages:
            conn = db.get_conn()
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                ts = msg.get("ts")
                msg_model = msg.get("model")

                if not role or not content:
                    logger.warning("skipping_invalid_message", chat_id=chat_id, msg=msg)
                    continue

                # Insert message with original timestamp
                conn.execute(
                    "INSERT INTO messages (chat_id, role, content, timestamp, model) VALUES (?, ?, ?, ?, ?)",
                    (chat_id, role, content, ts, msg_model)
                )

            conn.commit()
            conn.close()

        logger.info(
            "chat_migrated",
            chat_id=chat_id,
            title=title,
            messages=len(messages),
            tags=len(tags)
        )
        return True

    except Exception as e:
        logger.error("migration_failed", chat_id=chat_id, error=str(e), exc_info=True)
        return False


def migrate_all_chats(
    chats_dir: Path,
    db_path: Path,
    dry_run: bool = False,
    force: bool = False
) -> Dict[str, int]:
    """
    Migrate all chats from JSON to SQLite.

    Args:
        chats_dir: Directory containing JSON chat files
        db_path: Path to SQLite database
        dry_run: If True, don't actually migrate
        force: If True, overwrite existing chats

    Returns:
        Dictionary with migration statistics
    """
    if not chats_dir.exists():
        logger.error("chats_directory_not_found", path=str(chats_dir))
        return {"error": 1}

    # Find all JSON files
    json_files = list(chats_dir.glob("*.json"))
    logger.info("found_chat_files", count=len(json_files), directory=str(chats_dir))

    if dry_run:
        logger.info("dry_run_mode_enabled", message="No changes will be made")

    # Initialize database
    if not dry_run:
        db = ChatDatabase(db_path)
    else:
        db = None

    # Migration statistics
    stats = {
        "total": len(json_files),
        "migrated": 0,
        "skipped": 0,
        "failed": 0
    }

    # Migrate each chat
    for json_file in json_files:
        chat = load_json_chat(json_file)

        if not chat:
            stats["failed"] += 1
            continue

        if dry_run:
            logger.info(
                "would_migrate",
                chat_id=chat.get("id"),
                title=chat.get("title"),
                messages=len(chat.get("messages", []))
            )
            stats["migrated"] += 1
        else:
            success = migrate_chat(chat, db, force=force)
            if success:
                stats["migrated"] += 1
            else:
                stats["skipped"] += 1

    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate chat history from JSON files to SQLite database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually doing it"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing chats in SQLite"
    )
    parser.add_argument(
        "--chats-dir",
        type=Path,
        default=Path("chats"),
        help="Path to chats directory (default: chats)"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("chats.sqlite3"),
        help="Path to SQLite database (default: chats.sqlite3)"
    )

    args = parser.parse_args()

    logger.info(
        "migration_starting",
        chats_dir=str(args.chats_dir),
        db_path=str(args.db_path),
        dry_run=args.dry_run,
        force=args.force
    )

    # Run migration
    stats = migrate_all_chats(
        chats_dir=args.chats_dir,
        db_path=args.db_path,
        dry_run=args.dry_run,
        force=args.force
    )

    # Print summary
    logger.info("migration_complete", **stats)

    if "error" in stats:
        return 1

    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total chats found:    {stats['total']}")
    print(f"Successfully migrated: {stats['migrated']}")
    print(f"Skipped (existing):    {stats['skipped']}")
    print(f"Failed:                {stats['failed']}")
    print("=" * 60)

    if args.dry_run:
        print("\nThis was a DRY RUN - no changes were made.")
        print("Run without --dry-run to actually migrate the data.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
