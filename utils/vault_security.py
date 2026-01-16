"""
Vault path security utilities.

Centralized path validation to prevent directory traversal attacks
and ensure all file operations stay within the Obsidian vault boundaries.
"""

from pathlib import Path
from typing import Optional


class VaultPathError(Exception):
    """Raised when a path operation violates vault security boundaries."""
    pass


def safe_vault_path(vault_root: Path, user_path: str, must_exist: bool = False) -> Path:
    """
    Resolve a user-provided path safely within the vault, preventing traversal attacks.

    Args:
        vault_root: Root directory of the vault (absolute path)
        user_path: User-provided relative path (e.g., "Daily Notes/2024-10-30.md")
        must_exist: If True, raise VaultPathError if path doesn't exist

    Returns:
        Resolved absolute path guaranteed to be within vault_root

    Raises:
        VaultPathError: If path escapes vault, contains invalid characters, or doesn't exist when required

    Examples:
        >>> vault = Path("/app/vault")
        >>> safe_vault_path(vault, "Daily Notes/today.md")
        Path("/app/vault/Daily Notes/today.md")

        >>> safe_vault_path(vault, "../../etc/passwd")
        VaultPathError: Path ../../etc/passwd escapes vault
    """
    # Validate inputs
    if not vault_root.is_absolute():
        raise ValueError(f"vault_root must be absolute: {vault_root}")

    if not isinstance(user_path, str):
        raise VaultPathError(f"user_path must be a string, got {type(user_path)}")

    if not user_path or not user_path.strip():
        raise VaultPathError("user_path cannot be empty")

    # Normalize the user path
    user_path = user_path.strip()

    # Reject absolute paths (user should only provide relative paths)
    if Path(user_path).is_absolute():
        raise VaultPathError(f"user_path must be relative, got absolute: {user_path}")

    # Reject null bytes (security: can bypass some path checks)
    if '\x00' in user_path:
        raise VaultPathError("user_path contains null bytes")

    # Construct the full path and resolve it (resolves .., symlinks, etc.)
    try:
        full_path = (vault_root / user_path).resolve()
    except (OSError, RuntimeError) as e:
        raise VaultPathError(f"Failed to resolve path {user_path}: {e}")

    # CRITICAL: Ensure resolved path is still under vault_root
    # This catches:
    # - Directory traversal: "../../../etc/passwd"
    # - Symlinks pointing outside vault
    # - Windows drive letter tricks
    try:
        full_path.relative_to(vault_root.resolve())
    except ValueError:
        raise VaultPathError(f"Path {user_path} escapes vault (resolves to {full_path})")

    # Check existence if required
    if must_exist and not full_path.exists():
        raise VaultPathError(f"Path does not exist: {user_path}")

    return full_path


def validate_filename(filename: str, max_length: int = 255) -> str:
    """
    Validate a filename is safe to use in the vault.

    Args:
        filename: Proposed filename
        max_length: Maximum allowed length (default: 255, typical filesystem limit)

    Returns:
        Validated filename

    Raises:
        VaultPathError: If filename is invalid

    Examples:
        >>> validate_filename("my-note.md")
        "my-note.md"

        >>> validate_filename("../etc/passwd.md")
        VaultPathError: Filename contains path separators
    """
    if not filename or not filename.strip():
        raise VaultPathError("Filename cannot be empty")

    filename = filename.strip()

    # Reject path separators (filename should not be a path)
    if '/' in filename or '\\' in filename:
        raise VaultPathError(f"Filename contains path separators: {filename}")

    # Reject null bytes
    if '\x00' in filename:
        raise VaultPathError("Filename contains null bytes")

    # Reject names that are just dots (., .., etc.)
    if set(filename) == {'.'}:
        raise VaultPathError(f"Invalid filename: {filename}")

    # Check length
    if len(filename) > max_length:
        raise VaultPathError(f"Filename too long: {len(filename)} > {max_length}")

    # Reject Windows reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    name_without_ext = filename.rsplit('.', 1)[0].upper()
    if name_without_ext in reserved_names:
        raise VaultPathError(f"Filename uses reserved name: {filename}")

    return filename


def is_markdown_file(path: Path) -> bool:
    """
    Check if a path points to a markdown file.

    Args:
        path: Path to check

    Returns:
        True if path has .md extension (case-insensitive)
    """
    return path.suffix.lower() == '.md'


def get_vault_relative_path(vault_root: Path, absolute_path: Path) -> str:
    """
    Get the vault-relative path for an absolute path.

    Args:
        vault_root: Root directory of the vault
        absolute_path: Absolute path within vault

    Returns:
        Relative path as string (e.g., "Daily Notes/2024-10-30.md")

    Raises:
        VaultPathError: If absolute_path is not within vault
    """
    try:
        relative = absolute_path.relative_to(vault_root)
        return str(relative)
    except ValueError:
        raise VaultPathError(f"Path {absolute_path} is not within vault {vault_root}")
