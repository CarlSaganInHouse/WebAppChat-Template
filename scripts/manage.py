#!/usr/bin/env python3
"""
Management CLI for WebAppChat.
Commands for creating users, API keys, and other administrative tasks.

Usage:
    python manage.py create-user <username>
    python manage.py change-password <username>
    python manage.py create-api-key <label>
    python manage.py list-api-keys
    python manage.py revoke-api-key <key_id>
    python manage.py list-users
"""

import sys
import getpass
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_db import init_auth_db, get_auth_db
from utils.auth_utils import hash_password, generate_api_key, hash_api_key
from config import get_settings

import structlog

logger = structlog.get_logger()


def create_user(username: str) -> None:
    """
    Create a new user account.

    Args:
        username: Username for the new account
    """
    settings = get_settings()
    auth_db = get_auth_db(settings.chat_db_path)

    # Check if user already exists
    if auth_db.user_exists(username):
        print(f"❌ Error: User '{username}' already exists")
        sys.exit(1)

    # Prompt for password
    password = getpass.getpass(f"Enter password for '{username}': ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        print("❌ Error: Passwords do not match")
        sys.exit(1)

    if len(password) < 8:
        print("❌ Error: Password must be at least 8 characters")
        sys.exit(1)

    # Hash and create
    try:
        password_hash = hash_password(password)
        user_id = auth_db.create_user(username, password_hash)
        print(f"✅ User '{username}' created successfully (ID: {user_id})")
        logger.info("cli_user_created", username=username, user_id=user_id)
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        logger.error("cli_user_creation_failed", username=username, error=str(e))
        sys.exit(1)


def change_password(username: str) -> None:
    """
    Change password for an existing user.

    Args:
        username: Username of the account to update
    """
    settings = get_settings()
    auth_db = get_auth_db(settings.chat_db_path)

    # Check if user exists
    if not auth_db.user_exists(username):
        print(f"❌ Error: User '{username}' does not exist")
        sys.exit(1)

    # Prompt for new password
    password = getpass.getpass(f"Enter new password for '{username}': ")
    password_confirm = getpass.getpass("Confirm new password: ")

    if password != password_confirm:
        print("❌ Error: Passwords do not match")
        sys.exit(1)

    if len(password) < 8:
        print("❌ Error: Password must be at least 8 characters")
        sys.exit(1)

    # Hash and update
    try:
        password_hash = hash_password(password)

        # Update password in database
        conn = auth_db.get_conn()
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?",
            (password_hash, username)
        )
        conn.commit()
        conn.close()

        print(f"✅ Password changed successfully for user '{username}'")
        logger.info("cli_password_changed", username=username)
    except Exception as e:
        print(f"❌ Error changing password: {e}")
        logger.error("cli_password_change_failed", username=username, error=str(e))
        sys.exit(1)


def create_api_key(label: str) -> None:
    """
    Create a new API key.

    Args:
        label: Human-readable label for the key (e.g., "Voice Assistant")
    """
    settings = get_settings()
    auth_db = get_auth_db(settings.chat_db_path)

    try:
        api_key = generate_api_key(32)
        key_hash = hash_api_key(api_key)
        key_id = auth_db.create_api_key(label, key_hash)

        print(f"\n✅ API Key Created Successfully")
        print(f"   ID: {key_id}")
        print(f"   Label: {label}")
        print(f"   Key: {api_key}")
        print(f"\n⚠️  Save this key securely! It will not be shown again.")
        print(f"   Use in requests: Authorization: Bearer {api_key}\n")
        logger.info("cli_api_key_created", label=label, key_id=key_id)
    except Exception as e:
        print(f"❌ Error creating API key: {e}")
        logger.error("cli_api_key_creation_failed", label=label, error=str(e))
        sys.exit(1)


def list_api_keys() -> None:
    """List all API keys."""
    settings = get_settings()
    auth_db = get_auth_db(settings.chat_db_path)

    keys = auth_db.list_api_keys()

    if not keys:
        print("No API keys found")
        return

    print("\n📋 API Keys:")
    print("-" * 80)
    print(f"{'ID':<5} {'Label':<30} {'Created':<20} {'Last Used':<20} {'Revoked':<8}")
    print("-" * 80)

    for key in keys:
        created = key['created_at'] or "Unknown"
        last_used = key['last_used_at'] or "Never"
        revoked = "Yes" if key['revoked'] else "No"
        print(f"{key['id']:<5} {key['label']:<30} {created:<20} {last_used:<20} {revoked:<8}")

    print("-" * 80)


def revoke_api_key(key_id: int) -> None:
    """
    Revoke an API key.

    Args:
        key_id: ID of the key to revoke
    """
    settings = get_settings()
    auth_db = get_auth_db(settings.chat_db_path)

    try:
        if auth_db.revoke_api_key(key_id):
            print(f"✅ API key {key_id} revoked successfully")
            logger.info("cli_api_key_revoked", key_id=key_id)
        else:
            print(f"❌ API key {key_id} not found")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error revoking API key: {e}")
        logger.error("cli_api_key_revocation_failed", key_id=key_id, error=str(e))
        sys.exit(1)


def list_users() -> None:
    """List all users."""
    settings = get_settings()
    auth_db = get_auth_db(settings.chat_db_path)

    conn = auth_db.get_conn()
    users = conn.execute(
        "SELECT id, username, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    if not users:
        print("No users found")
        return

    print("\n👥 Users:")
    print("-" * 60)
    print(f"{'ID':<5} {'Username':<30} {'Created':<20}")
    print("-" * 60)

    for user in users:
        print(f"{user[0]:<5} {user[1]:<30} {user[2]:<20}")

    print("-" * 60)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="WebAppChat Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage.py create-user admin
  python manage.py change-password admin
  python manage.py create-api-key "Voice Assistant"
  python manage.py list-api-keys
  python manage.py revoke-api-key 1
  python manage.py list-users
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # create-user command
    user_parser = subparsers.add_parser('create-user', help='Create a new user')
    user_parser.add_argument('username', help='Username for the new account')

    # change-password command
    password_parser = subparsers.add_parser('change-password', help='Change user password')
    password_parser.add_argument('username', help='Username to change password for')

    # create-api-key command
    key_parser = subparsers.add_parser('create-api-key', help='Create a new API key')
    key_parser.add_argument('label', help='Human-readable label for the key')

    # list-api-keys command
    subparsers.add_parser('list-api-keys', help='List all API keys')

    # revoke-api-key command
    revoke_parser = subparsers.add_parser('revoke-api-key', help='Revoke an API key')
    revoke_parser.add_argument('key_id', type=int, help='ID of the key to revoke')

    # list-users command
    subparsers.add_parser('list-users', help='List all users')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == 'create-user':
            create_user(args.username)
        elif args.command == 'change-password':
            change_password(args.username)
        elif args.command == 'create-api-key':
            create_api_key(args.label)
        elif args.command == 'list-api-keys':
            list_api_keys()
        elif args.command == 'list-users':
            list_users()
        elif args.command == 'revoke-api-key':
            revoke_api_key(args.key_id)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        logger.error("cli_fatal_error", error=str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
