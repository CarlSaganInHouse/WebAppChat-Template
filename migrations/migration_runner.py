#!/usr/bin/env python3
"""
Database migration runner.
Executes SQL migrations in order and tracks applied migrations.

Usage:
    python migrations/migration_runner.py <db_path>

Example:
    python migrations/migration_runner.py chats.sqlite3
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime


def init_migrations_table(conn):
    """Create migrations tracking table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def get_applied_migrations(conn):
    """Get list of already-applied migrations."""
    cursor = conn.execute("SELECT migration_name FROM schema_migrations ORDER BY id")
    return {row[0] for row in cursor.fetchall()}


def apply_migration(conn, migration_path: Path):
    """
    Apply a single migration file.

    Args:
        conn: SQLite connection
        migration_path: Path to migration SQL file
    """
    print(f"Applying migration: {migration_path.name}")

    with open(migration_path, 'r') as f:
        sql = f.read()

    try:
        # Execute migration SQL
        conn.executescript(sql)

        # Record migration as applied
        conn.execute(
            "INSERT INTO schema_migrations (migration_name) VALUES (?)",
            (migration_path.name,)
        )
        conn.commit()
        print(f"✅ Migration {migration_path.name} applied successfully")
    except sqlite3.Error as e:
        # Check if the error is due to missing table (for RAG migrations)
        error_msg = str(e).lower()
        if 'no such table' in error_msg and '003_add_rag_collections' in migration_path.name:
            print(f"⚠️  Migration {migration_path.name} skipped (RAG tables not initialized yet)")
            # Still record as applied since we want to skip it in the future
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (migration_name) VALUES (?)",
                (migration_path.name,)
            )
            conn.commit()
        else:
            raise


def run_migrations(db_path: str):
    """
    Run all pending migrations.

    Args:
        db_path: Path to SQLite database
    """
    conn = sqlite3.connect(db_path)

    try:
        print(f"Running migrations on database: {db_path}")
        print(f"Database file exists: {Path(db_path).exists()}")
        print()

        init_migrations_table(conn)
        applied = get_applied_migrations(conn)

        # Get all migration files
        migrations_dir = Path(__file__).parent
        migration_files = sorted(migrations_dir.glob("*.sql"))

        if not migration_files:
            print("No migrations found")
            return

        pending = [m for m in migration_files if m.name not in applied]

        if not pending:
            print("✅ All migrations already applied")
            print()
            print("Applied migrations:")
            for name in sorted(applied):
                print(f"  - {name}")
            return

        print(f"Found {len(pending)} pending migration(s):")
        for m in pending:
            print(f"  - {m.name}")
        print()

        for migration in pending:
            apply_migration(conn, migration)

        print()
        print(f"✅ All migrations complete!")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migration_runner.py <db_path>")
        print()
        print("Example:")
        print("  python migrations/migration_runner.py chats.sqlite3")
        sys.exit(1)

    db_path = sys.argv[1]

    if not Path(db_path).exists():
        print(f"❌ Database file not found: {db_path}")
        print()
        print("Please ensure the database file exists before running migrations.")
        sys.exit(1)

    run_migrations(db_path)
