"""
Tests for vault path security utilities.

These tests ensure that path traversal attacks and other security
vulnerabilities are properly blocked.
"""

import pytest
from pathlib import Path
from utils.vault_security import (
    safe_vault_path,
    VaultPathError,
    validate_filename,
    is_markdown_file,
    get_vault_relative_path
)


@pytest.fixture
def tmp_vault(tmp_path):
    """Create a temporary vault directory for testing."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Create some test structure
    (vault / "Daily Notes").mkdir()
    (vault / "Jobs").mkdir()
    (vault / "Reference").mkdir()

    # Create a test note
    test_note = vault / "Daily Notes" / "2024-10-30.md"
    test_note.write_text("# Test Note\n\nContent here.")

    return vault


class TestSafeVaultPath:
    """Test the safe_vault_path function."""

    def test_valid_relative_path(self, tmp_vault):
        """Should allow valid relative paths."""
        result = safe_vault_path(tmp_vault, "Daily Notes/2024-10-30.md")
        assert result == tmp_vault / "Daily Notes" / "2024-10-30.md"
        assert result.exists()

    def test_directory_traversal_blocked(self, tmp_vault):
        """Should block directory traversal attempts."""
        with pytest.raises(VaultPathError, match="escapes vault"):
            safe_vault_path(tmp_vault, "../../../etc/passwd")

    def test_absolute_path_blocked(self, tmp_vault):
        """Should block absolute paths (user should provide relative paths only)."""
        with pytest.raises(VaultPathError, match="(must be relative|escapes vault)"):
            safe_vault_path(tmp_vault, "/etc/passwd")

    def test_null_byte_blocked(self, tmp_vault):
        """Should block null bytes (security vulnerability)."""
        with pytest.raises(VaultPathError, match="null bytes"):
            safe_vault_path(tmp_vault, "Daily Notes/test\x00.md")

    def test_empty_path_blocked(self, tmp_vault):
        """Should block empty paths."""
        with pytest.raises(VaultPathError, match="cannot be empty"):
            safe_vault_path(tmp_vault, "")

        with pytest.raises(VaultPathError, match="cannot be empty"):
            safe_vault_path(tmp_vault, "   ")

    def test_must_exist_enforced(self, tmp_vault):
        """Should raise error if path doesn't exist when must_exist=True."""
        with pytest.raises(VaultPathError, match="does not exist"):
            safe_vault_path(tmp_vault, "Daily Notes/nonexistent.md", must_exist=True)

    def test_must_exist_allows_new_files(self, tmp_vault):
        """Should allow non-existent paths when must_exist=False."""
        result = safe_vault_path(tmp_vault, "Daily Notes/new-note.md", must_exist=False)
        assert result == tmp_vault / "Daily Notes" / "new-note.md"
        assert not result.exists()  # Should not exist yet

    def test_nested_paths(self, tmp_vault):
        """Should handle deeply nested paths correctly."""
        result = safe_vault_path(tmp_vault, "Jobs/1234/docs/notes/meeting.md")
        expected = tmp_vault / "Jobs" / "1234" / "docs" / "notes" / "meeting.md"
        assert result == expected

    def test_dots_in_filename(self, tmp_vault):
        """Should allow dots in filenames (but not ../ traversal)."""
        result = safe_vault_path(tmp_vault, "Daily Notes/my.note.with.dots.md")
        assert result == tmp_vault / "Daily Notes" / "my.note.with.dots.md"


class TestValidateFilename:
    """Test the validate_filename function."""

    def test_valid_filename(self):
        """Should accept valid filenames."""
        assert validate_filename("my-note.md") == "my-note.md"
        assert validate_filename("Meeting Notes 2024.md") == "Meeting Notes 2024.md"

    def test_path_separators_blocked(self):
        """Should block path separators in filenames."""
        with pytest.raises(VaultPathError, match="path separators"):
            validate_filename("subdir/file.md")

        with pytest.raises(VaultPathError, match="path separators"):
            validate_filename("subdir\\file.md")

    def test_null_bytes_blocked(self):
        """Should block null bytes."""
        with pytest.raises(VaultPathError, match="null bytes"):
            validate_filename("test\x00.md")

    def test_dots_only_blocked(self):
        """Should block filenames that are just dots."""
        with pytest.raises(VaultPathError, match="Invalid filename"):
            validate_filename(".")

        with pytest.raises(VaultPathError, match="Invalid filename"):
            validate_filename("..")

    def test_empty_filename_blocked(self):
        """Should block empty filenames."""
        with pytest.raises(VaultPathError, match="cannot be empty"):
            validate_filename("")

        with pytest.raises(VaultPathError, match="cannot be empty"):
            validate_filename("   ")

    def test_long_filename_blocked(self):
        """Should block excessively long filenames."""
        long_name = "a" * 300 + ".md"
        with pytest.raises(VaultPathError, match="too long"):
            validate_filename(long_name, max_length=255)

    def test_windows_reserved_names_blocked(self):
        """Should block Windows reserved names."""
        reserved = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
        for name in reserved:
            with pytest.raises(VaultPathError, match="reserved name"):
                validate_filename(f"{name}.md")

            # Test case-insensitive
            with pytest.raises(VaultPathError, match="reserved name"):
                validate_filename(f"{name.lower()}.md")


class TestIsMarkdownFile:
    """Test the is_markdown_file function."""

    def test_markdown_files(self):
        """Should identify .md files."""
        assert is_markdown_file(Path("test.md"))
        assert is_markdown_file(Path("TEST.MD"))  # Case insensitive
        assert is_markdown_file(Path("/path/to/note.md"))

    def test_non_markdown_files(self):
        """Should reject non-.md files."""
        assert not is_markdown_file(Path("test.txt"))
        assert not is_markdown_file(Path("test.pdf"))
        assert not is_markdown_file(Path("test"))
        assert not is_markdown_file(Path("test.markdown"))  # Not .md


class TestGetVaultRelativePath:
    """Test the get_vault_relative_path function."""

    def test_relative_path_conversion(self, tmp_vault):
        """Should convert absolute to relative path."""
        absolute = tmp_vault / "Daily Notes" / "2024-10-30.md"
        relative = get_vault_relative_path(tmp_vault, absolute)

        assert relative == "Daily Notes/2024-10-30.md" or relative == "Daily Notes\\2024-10-30.md"

    def test_path_outside_vault_blocked(self, tmp_vault, tmp_path):
        """Should raise error if path is outside vault."""
        outside_path = tmp_path / "outside" / "file.md"

        with pytest.raises(VaultPathError, match="not within vault"):
            get_vault_relative_path(tmp_vault, outside_path)


class TestSecurityIntegration:
    """Integration tests for security scenarios."""

    def test_symlink_attack_blocked(self, tmp_vault, tmp_path):
        """Should block symlinks pointing outside vault."""
        # Create a file outside vault
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        secret_file = outside_dir / "secrets.txt"
        secret_file.write_text("SECRET DATA")

        # Try to create symlink inside vault (if supported)
        try:
            symlink_path = tmp_vault / "link_to_secrets"
            symlink_path.symlink_to(secret_file)

            # Trying to access via symlink should fail
            with pytest.raises(VaultPathError, match="escapes vault"):
                safe_vault_path(tmp_vault, "link_to_secrets", must_exist=True)
        except OSError:
            # Symlinks not supported (e.g., Windows without admin)
            pytest.skip("Symlinks not supported on this system")

    def test_multiple_traversal_attempts(self, tmp_vault):
        """Should block various traversal patterns."""
        attacks = [
            "../",
            "../../",
            "../../../etc/passwd",
            "./../../../etc/passwd",
            "Daily Notes/../../etc/passwd",
            "Daily Notes/../../../etc/passwd",
        ]

        for attack in attacks:
            with pytest.raises(VaultPathError):
                safe_vault_path(tmp_vault, attack)
