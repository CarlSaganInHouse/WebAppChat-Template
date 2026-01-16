#!/usr/bin/env python3
"""
WebDAV credential generator.

Generates secure bcrypt-hashed credentials for WebDAV authentication.
"""

import sys
import json
import getpass
from pathlib import Path

# Try to import dependencies
try:
    import bcrypt
except ImportError:
    print("ERROR: bcrypt module not found.")
    print("Install with: pip install bcrypt")
    sys.exit(1)

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from webdav_config import generate_token, WebDAVAuthConfig
except ImportError as e:
    print(f"ERROR: Failed to import webdav_config: {e}")
    print("Ensure webdav_config.py is in the same directory.")
    sys.exit(1)


def generate_credentials(device_name: str = None, password: str = None, auto_token: bool = True):
    """
    Generate WebDAV credentials.
    
    Args:
        device_name: Name/identifier for the device (e.g., "mobile", "laptop")
        password: Password/token to use (if None, will generate one)
        auto_token: If True and password is None, generate secure token automatically
    
    Returns:
        Tuple of (device_name, password, bcrypt_hash)
    """
    # Get device name
    if not device_name:
        print("\nWebDAV Credential Generator")
        print("=" * 60)
        device_name = input("Enter device name (e.g., 'mobile', 'laptop'): ").strip()
        
        if not device_name:
            print("ERROR: Device name cannot be empty")
            sys.exit(1)
    
    # Get or generate password
    if not password:
        if auto_token:
            # Auto-generate secure token
            password = generate_token(32)  # 64 hex characters (256 bits)
            print(f"\nGenerated secure token: {password}")
        else:
            # Manual password entry
            password = getpass.getpass("Enter password (or press Enter to auto-generate): ")
            if not password:
                password = generate_token(32)
                print(f"Generated token: {password}")
    
    # Generate bcrypt hash
    print("\nGenerating bcrypt hash (this may take a moment)...")
    salt = bcrypt.gensalt(rounds=12)
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    hash_str = password_hash.decode('utf-8')
    
    print("✓ Hash generated successfully")
    
    return device_name, password, hash_str


def update_env_file(device_name: str, hash_str: str, env_path: Path = None):
    """
    Help user update their .env file with new credentials.
    
    Args:
        device_name: Device name
        hash_str: Bcrypt hash string
        env_path: Path to .env file (default: .env in current directory)
    """
    if env_path is None:
        env_path = Path(__file__).parent / ".env"
    
    # Load existing .env if it exists
    existing_users = {}
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('WEBDAV_AUTH_USERS='):
                    # Extract JSON value
                    json_str = line.split('=', 1)[1].strip()
                    try:
                        existing_users = json.loads(json_str)
                    except json.JSONDecodeError:
                        print(f"WARNING: Could not parse existing WEBDAV_AUTH_USERS in {env_path}")
                    break
    
    # Add new user
    existing_users[device_name] = hash_str
    
    # Format for .env file
    json_str = json.dumps(existing_users, indent=0).replace('\n', '')
    
    return json_str


def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("WebDAV Credential Generator")
    print("=" * 60)
    
    # Check if running interactively or with arguments
    if len(sys.argv) > 1:
        # Command-line mode
        device_name = sys.argv[1] if len(sys.argv) > 1 else None
        password = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        # Interactive mode
        device_name = None
        password = None
    
    # Generate credentials
    device_name, password, hash_str = generate_credentials(device_name, password)
    
    # Update .env file helper
    env_json = update_env_file(device_name, hash_str)
    
    # Display results
    print("\n" + "=" * 60)
    print("✓ Credentials Generated Successfully")
    print("=" * 60)
    print(f"\nDevice Name: {device_name}")
    print(f"Token/Password: {password}")
    print(f"Bcrypt Hash: {hash_str}")
    
    print("\n" + "=" * 60)
    print("Add this to your .env file:")
    print("=" * 60)
    print(f"\nWEBDAV_AUTH_USERS={env_json}")
    
    print("\n" + "=" * 60)
    print("Configuration for Obsidian:")
    print("=" * 60)
    print(f"\nURL: https://your-domain.com/vault")
    print(f"Username: {device_name}")
    print(f"Password: {password}")
    
    print("\n" + "=" * 60)
    print("Security Reminders:")
    print("=" * 60)
    print("• Save the token in a secure password manager")
    print("• Never share tokens between devices")
    print("• Rotate tokens every 90 days")
    print("• Remove credentials immediately if device is lost/stolen")
    print("• Restart WebDAV container after updating .env:")
    print("  docker-compose restart webdav")
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Copy the WEBDAV_AUTH_USERS line to your .env file")
    print("2. Run: docker-compose restart webdav")
    print("3. Test: python test_webdav.py http://localhost:8080 " + device_name + " <token>")
    print("4. Configure Obsidian with the credentials above")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
