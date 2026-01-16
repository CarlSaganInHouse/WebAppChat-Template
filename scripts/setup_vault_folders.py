#!/usr/bin/env python3
"""
Vault Folder Structure Setup Script

Creates the new folder structure for the vault migration:
- 00-Inbox/           (quick captures, voice memos)
- 60-Calendar/Daily/  (daily notes)
- 90-Meta/Templates/  (note templates)
- 90-Meta/Attachments/ (images and attachments)

Usage:
    python3 scripts/setup_vault_folders.py              # Create folders
    python3 scripts/setup_vault_folders.py --dry-run    # Preview only
"""

import sys
import os
from pathlib import Path

# Add WebAppChat to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def setup_vault_folders(dry_run=False):
    """Create the new vault folder structure."""
    from config import get_settings

    settings = get_settings()
    vault = settings.vault_path

    if not vault.exists():
        print(f"ERROR: Vault path does not exist: {vault}")
        return False

    # Folders to create (from config settings)
    folders_to_create = [
        settings.inbox_folder,           # e.g., "00-Inbox"
        settings.daily_notes_folder,     # e.g., "60-Calendar/Daily"
        settings.templates_folder,       # e.g., "90-Meta/Templates"
        settings.attachments_folder,     # e.g., "90-Meta/Attachments"
    ]

    created = []
    existed = []

    for folder in folders_to_create:
        folder_path = vault / folder

        if folder_path.exists():
            existed.append(folder)
            print(f"  EXISTS: {folder}")
        else:
            if dry_run:
                print(f"  WOULD CREATE: {folder}")
            else:
                folder_path.mkdir(parents=True, exist_ok=True)
                # Fix ownership if running as root
                try:
                    os.chown(folder_path, 1000, 1000)
                except OSError:
                    pass  # Ignore permission errors
                print(f"  CREATED: {folder}")
            created.append(folder)

    print()
    print(f"Summary:")
    print(f"  Vault: {vault}")
    print(f"  Already existed: {len(existed)}")
    print(f"  {'Would create' if dry_run else 'Created'}: {len(created)}")

    if dry_run:
        print()
        print("Run without --dry-run to create folders.")

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Set up vault folder structure for the new architecture'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without creating folders'
    )

    args = parser.parse_args()

    print("Vault Folder Structure Setup")
    print("=" * 40)
    print()

    success = setup_vault_folders(dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
