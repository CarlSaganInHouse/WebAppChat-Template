"""
Obsidian Service - Vault operations abstraction

This service handles:
- Vault path validation and security
- Note CRUD operations (create, read, update, delete)
- Daily note management
- Job note creation
- Template system
- Search and discovery
- Smart linking and tagging

Used by: routes/obsidian_routes.py, obsidian.py (backward compatibility wrapper)

This service extracts the 2,274-line obsidian.py module into a clean, testable service layer.
"""

import os
import pytz
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field

from config import get_settings
from utils.vault_security import safe_vault_path, VaultPathError, validate_filename
from utils.obsidian_response import success_response, error_response, dry_run_response

logger = None  # Will use structlog if needed


@dataclass
class VaultOperationResult:
    """Standard result type for vault operations."""
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ObsidianService:
    """
    Centralized service for all Obsidian vault operations.

    Provides a clean, testable interface for:
    - Vault path management
    - CRUD operations on notes
    - Daily note handling
    - Job note creation
    - Template operations
    - Search and linking
    """

    def __init__(self, vault_path: Optional[Path] = None):
        """
        Initialize the Obsidian service.

        Args:
            vault_path: Optional vault path override. If None, uses config settings.
        """
        self.settings = get_settings()
        self._vault_path = vault_path or self.settings.vault_path

    def get_vault_path(self) -> Path:
        """
        Get the vault path and ensure it exists.

        Returns:
            Path to the vault

        Raises:
            FileNotFoundError: If vault doesn't exist
        """
        if not self._vault_path.exists():
            raise FileNotFoundError(f"Vault not found at {self._vault_path}")
        return self._vault_path

    def fix_file_ownership(self, file_path: Path) -> None:
        """
        Fix ownership of files created by the app to match vault ownership.

        This prevents permission issues when editing files in Obsidian.

        Args:
            file_path: Path to the file to fix
        """
        try:
            if file_path.exists():
                vault = self.get_vault_path()
                vault_stat = vault.stat()
                os.chown(file_path, vault_stat.st_uid, vault_stat.st_gid)
                os.chmod(file_path, 0o664)
        except Exception as e:
            # Don't fail the operation if ownership fix fails
            print(f"Warning: Could not fix ownership for {file_path}: {e}")

    def get_vault_folders(self) -> List[str]:
        """
        Get list of all folders in the vault.

        Returns:
            List of folder names (excluding hidden folders)
        """
        try:
            vault = self.get_vault_path()
            folders = [
                f.name for f in vault.iterdir()
                if f.is_dir() and not f.name.startswith('.')
            ]
            return sorted(folders)
        except Exception:
            # Fallback if vault not accessible - return empty list, let caller handle
            return []

    def validate_function_args(
        self,
        function_name: str,
        arguments: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate function arguments before execution.

        Args:
            function_name: Name of the function to validate
            arguments: Dictionary of function arguments

        Returns:
            (is_valid, error_message) tuple
        """
        try:
            vault = self.get_vault_path()
            vault_folders = self.get_vault_folders()

            # Validate research_and_save
            if function_name == "research_and_save":
                save_loc = arguments.get("save_location", "Reference")
                if not save_loc.endswith('.md'):
                    if save_loc not in vault_folders:
                        return False, f"Folder '{save_loc}' doesn't exist. Available: {', '.join(vault_folders)}"

            # Validate create_from_template
            elif function_name == "create_from_template":
                template_name = arguments.get("template_name", "")
                destination = arguments.get("destination", "")

                templates_dir = vault / self.settings.templates_folder
                template_path = templates_dir / f"{template_name}.md"
                if not template_path.exists():
                    available = [f.stem for f in templates_dir.glob("*.md")] if templates_dir.exists() else []
                    return False, f"Template '{template_name}' not found. Available: {', '.join(available) or 'None'}"

                if not destination.endswith('.md'):
                    dest_folder = vault / destination
                    if not dest_folder.exists():
                        return False, f"Destination folder '{destination}' doesn't exist. Available: {', '.join(vault_folders)}"

            # Validate file-specific functions
            elif function_name in ["update_note_section", "replace_text_in_note"]:
                file_path = arguments.get("file_path", "")
                if file_path:
                    try:
                        safe_vault_path(vault, file_path, must_exist=True)
                    except VaultPathError as e:
                        return False, str(e)

            # create_job_note is deprecated - return validation failure
            elif function_name == "create_job_note":
                return False, "create_job_note is deprecated. Use create_note_from_template() instead."

            return True, None

        except Exception:
            # Fail-safe: allow execution if validation itself fails
            return True, None

    # Daily Note Operations

    def get_daily_note_path(
        self,
        date_str: Optional[str] = None
    ) -> Tuple[Path, str]:
        """
        Resolve the path to a daily note.

        Args:
            date_str: Optional YYYY-MM-DD string. Defaults to today.

        Returns:
            (note_path, normalized_date_string) tuple
        """
        vault = self.get_vault_path()

        try:
            user_tz = pytz.timezone(self.settings.timezone)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.timezone("America/New_York")

        if date_str:
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError as exc:
                raise ValueError("Date must be in YYYY-MM-DD format") from exc
            target_date = date_str
        else:
            target_date = datetime.now(user_tz).strftime('%Y-%m-%d')

        daily_notes_dir = vault / self.settings.daily_notes_folder
        daily_notes_dir.mkdir(parents=True, exist_ok=True)
        return daily_notes_dir / f"{target_date}.md", target_date

    def ensure_daily_note(self, date_str: Optional[str] = None) -> Path:
        """
        Ensure a daily note exists (creates if missing).

        Args:
            date_str: Optional YYYY-MM-DD string. Defaults to today.

        Returns:
            Path to the daily note
        """
        note_path, normalized_date = self.get_daily_note_path(date_str)

        if not note_path.exists():
            try:
                user_tz = pytz.timezone(self.settings.timezone)
            except pytz.UnknownTimeZoneError:
                user_tz = pytz.timezone("America/New_York")

            today = normalized_date if date_str else datetime.now(user_tz).strftime('%Y-%m-%d')

            template = f"""---
date: {today}
tags: [daily-note]
---

## Quick Captures

---
## Work Notes

---
## Personal Notes

---
## Tasks

"""
            note_path.write_text(template, encoding='utf-8')
            self.fix_file_ownership(note_path)

        return note_path

    def append_to_daily(
        self,
        content: str,
        section: str = "Quick Captures",
        date: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Append content to a daily note.

        Args:
            content: Text to append
            section: Section header to append under
            date: Optional YYYY-MM-DD string
            dry_run: If True, preview without executing

        Returns:
            Standardized response dict
        """
        try:
            note_path = self.ensure_daily_note(date)
            _, target_date = self.get_daily_note_path(date)
            vault = self.get_vault_path()
            relative_path = str(note_path.relative_to(vault))

            if dry_run:
                return dry_run_response(
                    f"Would append to '{section}' section in {target_date}",
                    data={
                        "path": relative_path,
                        "section": section,
                        "content_length": len(content),
                        "action": "append"
                    },
                    path=relative_path
                )

            current_content = note_path.read_text(encoding='utf-8')

            # Format bullet
            bullet = f"- {content}"
            if section == 'Tasks' and not content.strip().startswith('['):
                bullet = f"- [ ] {content}"

            section_header = f"## {section}"
            created_section = False

            if section_header in current_content:
                lines = current_content.splitlines()
                section_index = None

                for i, line in enumerate(lines):
                    if line.strip() == section_header:
                        section_index = i
                        break

                if section_index is not None:
                    insertion_index = section_index + 1
                    while insertion_index < len(lines) and lines[insertion_index].strip() == '':
                        insertion_index += 1

                    lines.insert(insertion_index, bullet)
                    note_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            else:
                created_section = True
                with note_path.open('a', encoding='utf-8') as f:
                    if not current_content.endswith('\n'):
                        f.write('\n')
                    f.write(f"---\n\n## {section}\n{bullet}\n")

            return success_response(
                f"Added to {target_date} under {section}",
                data={
                    "path": relative_path,
                    "section": section,
                    "date": target_date,
                    "created_section": created_section,
                    "action": "appended"
                },
                path=relative_path
            )

        except Exception as e:
            return error_response(str(e))

    # Note CRUD Operations

    def read_note(
        self,
        file_path: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Read a note from the vault.

        Args:
            file_path: Relative path to note
            dry_run: If True, preview without executing

        Returns:
            Standardized response with content or error
        """
        try:
            vault = self.get_vault_path()
            note_path = safe_vault_path(vault, file_path, must_exist=True)
            relative_path = str(note_path.relative_to(vault))

            if dry_run:
                return dry_run_response(
                    f"Would read note: {file_path}",
                    data={
                        "path": relative_path,
                        "exists": True,
                        "action": "read"
                    },
                    path=relative_path
                )

            content = note_path.read_text(encoding='utf-8')

            return success_response(
                f"Read note: {file_path}",
                data={
                    "path": relative_path,
                    "content": content,
                    "content_length": len(content),
                    "action": "read"
                },
                content=content,
                path=relative_path
            )

        except VaultPathError as e:
            return error_response(str(e), data={"path": file_path})
        except Exception as e:
            return error_response(str(e), data={"path": file_path})

    def create_note(
        self,
        content: str,
        destination: str,
        filename: Optional[str] = None,
        mode: str = "create"
    ) -> Dict[str, Any]:
        """
        Create a new note in the vault.

        Args:
            content: Note content (markdown)
            destination: Folder name OR full path ending in .md
            filename: Optional filename (auto-generated if None)
            mode: "create" (fail if exists), "append", or "overwrite"

        Returns:
            Detailed result with path and action taken
        """
        try:
            vault = self.get_vault_path()

            # Determine note path
            if destination.endswith('.md'):
                try:
                    note_path = safe_vault_path(vault, destination, must_exist=False)
                except VaultPathError as e:
                    return {
                        "success": False,
                        "error": f"Invalid destination path: {e}"
                    }
                destination_folder = note_path.parent.name
            else:
                try:
                    folder = safe_vault_path(vault, destination, must_exist=False)
                except VaultPathError as e:
                    return {
                        "success": False,
                        "error": f"Invalid folder path: {e}"
                    }

                if not folder.exists():
                    folder.mkdir(parents=True, exist_ok=True)

                if filename is None:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"note_{timestamp}.md"

                if not filename.endswith('.md'):
                    filename += '.md'

                try:
                    validate_filename(filename)
                except VaultPathError as e:
                    return {
                        "success": False,
                        "error": f"Invalid filename: {e}"
                    }

                note_path = folder / filename
                destination_folder = destination

            # Handle different modes
            action_taken = None

            if mode == "create":
                if note_path.exists():
                    return {
                        "success": False,
                        "error": f"File already exists: {note_path.name}. Use mode='overwrite' or 'append'"
                    }
                note_path.parent.mkdir(parents=True, exist_ok=True)
                note_path.write_text(content, encoding='utf-8')
                self.fix_file_ownership(note_path)
                action_taken = "created"

            elif mode == "append":
                if note_path.exists():
                    with note_path.open('a', encoding='utf-8') as f:
                        f.write(f"\n\n{content}")
                    self.fix_file_ownership(note_path)
                    action_taken = "appended"
                else:
                    note_path.parent.mkdir(parents=True, exist_ok=True)
                    note_path.write_text(content, encoding='utf-8')
                    self.fix_file_ownership(note_path)
                    action_taken = "created"

            elif mode == "overwrite":
                note_path.parent.mkdir(parents=True, exist_ok=True)
                note_path.write_text(content, encoding='utf-8')
                self.fix_file_ownership(note_path)
                action_taken = "overwritten"

            else:
                return {
                    "success": False,
                    "error": f"Invalid mode: {mode}. Use 'create', 'append', or 'overwrite'"
                }

            return {
                "success": True,
                "message": f"{action_taken.capitalize()} note: {note_path.name}",
                "path": str(note_path.relative_to(vault)),
                "absolute_path": str(note_path),
                "action": action_taken,
                "folder": destination_folder,
                "filename": note_path.name
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def update_note_section(
        self,
        file_path: str,
        section_name: str,
        new_content: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Update a specific section in a note.

        Args:
            file_path: Relative path to note
            section_name: Section header to update
            new_content: New content for the section
            dry_run: If True, preview without executing

        Returns:
            Standardized response dict
        """
        try:
            vault = self.get_vault_path()
            note_path = safe_vault_path(vault, file_path, must_exist=True)

            content = note_path.read_text(encoding='utf-8')
            lines = content.split('\n')

            # Find section
            section_header = f"## {section_name}"
            section_start = None
            section_end = None

            for i, line in enumerate(lines):
                if line.strip() == section_header:
                    section_start = i
                elif section_start is not None and line.strip().startswith("## "):
                    section_end = i
                    break

            if section_start is None:
                available_sections = [
                    line.strip()[3:] for line in lines
                    if line.strip().startswith("## ")
                ]
                return error_response(
                    f"Section '{section_name}' not found in note",
                    data={
                        "path": file_path,
                        "section": section_name,
                        "available_sections": available_sections
                    }
                )

            if section_end is None:
                section_end = len(lines)

            old_content = '\n'.join(lines[section_start + 1:section_end]).strip()

            if dry_run:
                return dry_run_response(
                    f"Would update section '{section_name}' in {file_path}",
                    data={
                        "path": file_path,
                        "section": section_name,
                        "old_content_preview": old_content[:100] + "..." if len(old_content) > 100 else old_content,
                        "new_content_preview": new_content[:100] + "..." if len(new_content) > 100 else new_content,
                        "old_length": len(old_content),
                        "new_length": len(new_content),
                        "action": "update"
                    }
                )

            # Replace section content
            new_lines = (
                lines[:section_start + 1] +
                [''] +
                [new_content] +
                [''] +
                lines[section_end:]
            )

            note_path.write_text('\n'.join(new_lines), encoding='utf-8')

            return success_response(
                f"Updated section '{section_name}' in {file_path}",
                data={
                    "path": file_path,
                    "section": section_name,
                    "old_length": len(old_content),
                    "new_length": len(new_content),
                    "action": "updated"
                }
            )

        except VaultPathError as e:
            return error_response(str(e), data={"path": file_path})
        except Exception as e:
            return error_response(str(e), data={"path": file_path})

    def save_image(
        self,
        image_bytes: bytes,
        filename: str,
        embed_in_note: Optional[str] = None,
        section: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save an image to the vault's Attachments folder.

        Args:
            image_bytes: Raw image data as bytes
            filename: Desired filename (will be sanitized, timestamped if empty)
            embed_in_note: Optional note path to embed the image link in
            section: Optional section header to place the image under

        Returns:
            Dict with success status, path, and markdown embed syntax
        """
        try:
            vault = self.get_vault_path()
            attachments_dir = vault / self.settings.attachments_folder
            attachments_dir.mkdir(parents=True, exist_ok=True)

            # Validate and sanitize filename
            if not filename or filename.strip() == "":
                # Generate timestamp-based filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"image_{timestamp}.png"
            else:
                # Sanitize the provided filename
                # Extract extension
                if '.' in filename:
                    name_part, ext = filename.rsplit('.', 1)
                    ext = ext.lower()
                    if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'):
                        ext = 'png'  # Default to png for unknown extensions
                else:
                    name_part = filename
                    ext = 'png'

                # Sanitize name part
                safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in name_part)
                safe_name = safe_name.strip().replace(" ", "_")

                if not safe_name:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    safe_name = f"image_{timestamp}"

                filename = f"{safe_name}.{ext}"

            # Check for collision and add timestamp if needed
            image_path = attachments_dir / filename
            if image_path.exists():
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                name_part, ext = filename.rsplit('.', 1)
                filename = f"{name_part}_{timestamp}.{ext}"
                image_path = attachments_dir / filename

            # Write the image
            image_path.write_bytes(image_bytes)
            self.fix_file_ownership(image_path)

            relative_path = f"{self.settings.attachments_folder}/{filename}"
            # Use full path in embed to avoid ambiguity with duplicate filenames
            markdown_embed = f"![[{relative_path}]]"
            markdown_link = f"![{filename}]({relative_path})"

            result = {
                "success": True,
                "message": f"Saved image: {filename}",
                "path": relative_path,
                "absolute_path": str(image_path),
                "filename": filename,
                "markdown": markdown_embed,
                "markdown_link": markdown_link,
                "size_bytes": len(image_bytes)
            }

            # Optionally embed in a note
            if embed_in_note:
                try:
                    note_path = safe_vault_path(vault, embed_in_note, must_exist=False)

                    if note_path.exists():
                        content = note_path.read_text(encoding='utf-8')

                        if section:
                            # Try to insert under specified section
                            section_header = f"## {section}"
                            if section_header in content:
                                lines = content.split('\n')
                                section_index = None
                                for i, line in enumerate(lines):
                                    if line.strip() == section_header:
                                        section_index = i
                                        break

                                if section_index is not None:
                                    # Find insertion point (after section header and any blank lines)
                                    insertion_index = section_index + 1
                                    while insertion_index < len(lines) and lines[insertion_index].strip() == '':
                                        insertion_index += 1

                                    lines.insert(insertion_index, f"\n{markdown_embed}\n")
                                    note_path.write_text('\n'.join(lines), encoding='utf-8')
                                    result["embedded_in"] = embed_in_note
                                    result["embedded_section"] = section
                            else:
                                # Section not found, append to end
                                with note_path.open('a', encoding='utf-8') as f:
                                    f.write(f"\n\n## {section}\n\n{markdown_embed}\n")
                                result["embedded_in"] = embed_in_note
                                result["created_section"] = section
                        else:
                            # No section specified, append to end
                            with note_path.open('a', encoding='utf-8') as f:
                                f.write(f"\n\n{markdown_embed}\n")
                            result["embedded_in"] = embed_in_note
                    else:
                        # Note doesn't exist, create it with the image
                        note_path.parent.mkdir(parents=True, exist_ok=True)
                        note_content = f"# {note_path.stem}\n\n{markdown_embed}\n"
                        note_path.write_text(note_content, encoding='utf-8')
                        self.fix_file_ownership(note_path)
                        result["embedded_in"] = embed_in_note
                        result["created_note"] = True

                except VaultPathError as e:
                    result["embed_error"] = str(e)
                except Exception as e:
                    result["embed_error"] = str(e)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def delete_note(
        self,
        file_path: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Delete a note from the vault.

        Args:
            file_path: Relative path to note
            dry_run: If True, preview without executing

        Returns:
            Standardized response dict
        """
        try:
            vault = self.get_vault_path()
            note_path = safe_vault_path(vault, file_path, must_exist=True)
            relative_path = str(note_path.relative_to(vault))

            if dry_run:
                return dry_run_response(
                    f"Would delete note: {file_path}",
                    data={
                        "path": relative_path,
                        "exists": True,
                        "action": "delete"
                    },
                    path=relative_path
                )

            note_path.unlink()

            return success_response(
                f"Deleted note: {file_path}",
                data={
                    "path": relative_path,
                    "action": "deleted"
                },
                path=relative_path
            )

        except VaultPathError as e:
            return error_response(str(e), data={"path": file_path})
        except Exception as e:
            return error_response(str(e), data={"path": file_path})

    # Job Note Operations (DEPRECATED)

    def create_job_note(
        self,
        job_number: str,
        job_name: str,
        client: str = "",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Create a job note from template.

        This function has been deprecated as part of the vault architecture migration.
        Use create_note_from_template() with an appropriate template instead.

        Args:
            job_number: Job number/ID
            job_name: Name of the job
            client: Client name (optional)
            dry_run: If True, preview without executing

        Returns:
            Error response indicating deprecation
        """
        return error_response(
            "create_job_note is deprecated. Use create_note_from_template() with a project template instead. "
            "The vault now uses dynamic folder organization - create notes in your preferred location.",
            data={
                "deprecated": True,
                "alternative": "create_note_from_template",
                "job_number": job_number,
                "job_name": job_name
            }
        )

    # Search & Discovery Operations

    def search_vault(
        self,
        query: str,
        folders: Optional[List[str]] = None,
        case_sensitive: bool = False
    ) -> Dict[str, Any]:
        """
        Search for text across vault files.

        Args:
            query: Text to search for
            folders: List of folder names to search (default: all)
            case_sensitive: Whether search is case sensitive

        Returns:
            Search results with matches
        """
        try:
            vault = self.get_vault_path()
            results = []

            # Use provided folders or search all top-level folders dynamically
            search_folders = folders if folders else self.get_vault_folders()
            search_query = query if case_sensitive else query.lower()

            for folder_name in search_folders:
                folder_path = vault / folder_name
                if not folder_path.exists():
                    continue

                for md_file in folder_path.rglob("*.md"):
                    try:
                        content = md_file.read_text(encoding='utf-8')
                        search_content = content if case_sensitive else content.lower()

                        if search_query in search_content:
                            lines = content.split('\n')
                            matches = []

                            for i, line in enumerate(lines, 1):
                                check_line = line if case_sensitive else line.lower()
                                if search_query in check_line:
                                    context_start = max(0, i - 2)
                                    context_end = min(len(lines), i + 1)
                                    context = '\n'.join(lines[context_start:context_end])

                                    matches.append({
                                        "line": i,
                                        "text": line.strip(),
                                        "context": context
                                    })

                            if matches:
                                results.append({
                                    "file": str(md_file.relative_to(vault)),
                                    "folder": folder_name,
                                    "matches": matches[:5]
                                })

                    except Exception:
                        continue

            return success_response(
                f"Found {len(results)} file(s) matching '{query}'",
                data={
                    "query": query,
                    "total_files": len(results),
                    "results": results[:20],
                    "folders_searched": search_folders,
                    "case_sensitive": case_sensitive,
                    "action": "searched"
                },
                query=query,
                total_files=len(results),
                results=results[:20]
            )

        except Exception as e:
            return error_response(str(e), data={"query": query})

    def list_vault_structure(self) -> Dict[str, Any]:
        """
        Get vault structure overview.

        Returns:
            Vault structure with folder counts and recent notes
        """
        try:
            vault = self.get_vault_path()

            structure = {
                "vault_path": str(vault),
                "folders": {},
                "recent_notes": []
            }

            for item in vault.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    folder_name = item.name
                    # Use rglob to find all .md files recursively (supports nested folders)
                    all_files = list(item.rglob("*.md"))
                    files = [str(f.relative_to(item)) for f in all_files][:20]
                    structure["folders"][folder_name] = {
                        "count": len(all_files),
                        "files": files
                    }

            daily_notes_dir = vault / self.settings.daily_notes_folder
            if daily_notes_dir.exists():
                notes = sorted([f.stem for f in daily_notes_dir.glob("*.md")], reverse=True)[:7]
                structure["recent_daily_notes"] = notes
                # Backward compatibility for callers expecting recent_notes
                structure["recent_notes"] = notes

            return {
                "success": True,
                "structure": structure
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def list_folder_contents(self, folder_name: str, limit: int = 50) -> Dict[str, Any]:
        """
        List all files in a specific vault folder.

        Args:
            folder_name: Name of folder to list
            limit: Maximum number of files to return (default 50 for performance)

        Returns:
            List of files in the folder (limited to first N files)
        """
        try:
            vault = self.get_vault_path()

            # Use safe_vault_path to handle nested folders securely
            try:
                folder_path = safe_vault_path(vault, folder_name, must_exist=True)
            except VaultPathError as e:
                return {
                    "success": False,
                    "error": str(e)
                }

            if not folder_path.is_dir():
                return {
                    "success": False,
                    "error": f"'{folder_name}' is not a folder"
                }

            files = []
            total_count = 0
            
            # Collect all files first to get accurate count and sort
            all_files = list(folder_path.rglob('*.md'))
            total_count = len(all_files)
            
            # Sort by name
            all_files.sort(key=lambda x: x.name)
            
            # Only process details for the limited set
            for item in all_files[:limit]:
                relative_path = item.relative_to(folder_path)
                files.append({
                    "name": item.name,
                    "path": str(relative_path),
                    "size_bytes": item.stat().st_size if item.exists() else 0
                })

            return {
                "success": True,
                "folder": folder_name,
                "total_files": total_count,
                "returned_files": len(files),
                "files": files
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # ========================================================================
    # TEMPLATE SYSTEM
    # ========================================================================

    def list_templates(self) -> Dict[str, Any]:
        """
        List all available templates.

        Returns:
            dict: Success status and list of templates
        """
        try:
            vault = self.get_vault_path()
            templates_dir = vault / self.settings.templates_folder
            templates_dir.mkdir(parents=True, exist_ok=True)

            templates = []
            for template_file in templates_dir.glob("*.md"):
                templates.append({
                    "name": template_file.stem,
                    "path": str(template_file.relative_to(vault)),
                    "size": template_file.stat().st_size
                })

            return success_response(
                f"Found {len(templates)} template(s)",
                data={
                    "templates": templates,
                    "count": len(templates),
                    "action": "listed"
                },
                # Legacy fields
                templates=templates,
                count=len(templates)
            )

        except Exception as e:
            return error_response(str(e))

    def create_note_from_template(
        self,
        template_name: str,
        destination: str,
        variables: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new note from a template with variable substitution.

        Args:
            template_name: Name of template (without .md extension)
            destination: Where to save (relative path like "Daily Notes/meeting.md" or folder name)
            variables: Dict of {placeholder: value} for template substitution

        Returns:
            dict: Success status and path to created note
        """
        try:
            vault = self.get_vault_path()
            templates_dir = vault / self.settings.templates_folder

            # Find template
            template_path = templates_dir / f"{template_name}.md"
            if not template_path.exists():
                return {
                    "success": False,
                    "error": f"Template '{template_name}' not found"
                }

            # Read template
            template_content = template_path.read_text(encoding='utf-8')

            # Substitute variables
            if variables:
                for key, value in variables.items():
                    placeholder = f"{{{{{key}}}}}"  # {{variable}} format
                    template_content = template_content.replace(placeholder, str(value))

            # Also substitute common auto-variables
            from datetime import timedelta
            now = datetime.now()
            next_week = now + timedelta(days=7)
            next_month = now + timedelta(days=30)
            next_year = now + timedelta(days=365)

            auto_vars = {
                "{{date}}": now.strftime('%Y-%m-%d'),
                "{{time}}": now.strftime('%H:%M'),
                "{{datetime}}": now.strftime('%Y-%m-%d %H:%M'),
                "{{year}}": now.strftime('%Y'),
                "{{month}}": now.strftime('%m'),
                "{{day}}": now.strftime('%d'),
                "{{week}}": now.strftime('%U'),
                "{{next_week_date}}": next_week.strftime('%Y-%m-%d'),
                "{{next_month_date}}": next_month.strftime('%Y-%m-%d'),
                "{{next_year_date}}": next_year.strftime('%Y-%m-%d'),
                "{{today}}": now.strftime('%A, %B %d, %Y'),
                "{{timestamp}}": now.strftime('%Y%m%d_%H%M%S')
            }
            for placeholder, value in auto_vars.items():
                template_content = template_content.replace(placeholder, value)

            # Determine save location
            if destination.endswith('.md'):
                # Full path provided - validate it
                try:
                    note_path = safe_vault_path(vault, destination, must_exist=False)
                except VaultPathError as e:
                    return {
                        "success": False,
                        "error": f"Invalid destination path: {e}"
                    }
            else:
                # Folder provided - validate folder path
                try:
                    folder = safe_vault_path(vault, destination, must_exist=False)
                except VaultPathError as e:
                    return {
                        "success": False,
                        "error": f"Invalid folder path: {e}"
                    }

                folder.mkdir(exist_ok=True, parents=True)

                # Create filename from template name + timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{template_name}_{timestamp}.md"

                # Validate filename
                try:
                    validate_filename(filename)
                except VaultPathError:
                    # Fallback to simple timestamp if validation fails
                    filename = f"note_{timestamp}.md"

                note_path = folder / filename

            # Create parent directories if needed
            note_path.parent.mkdir(parents=True, exist_ok=True)

            # Write note
            note_path.write_text(template_content, encoding='utf-8')
            self.fix_file_ownership(note_path)

            return {
                "success": True,
                "message": f"Created note from template '{template_name}'",
                "path": str(note_path.relative_to(vault)),
                "absolute_path": str(note_path)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def create_custom_template(self, template_name: str, content: str) -> Dict[str, Any]:
        """
        Save a new custom template.

        Args:
            template_name: Name for the template
            content: Template content (can include {{variables}})

        Returns:
            dict: Success status
        """
        try:
            vault = self.get_vault_path()
            templates_dir = vault / self.settings.templates_folder
            templates_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize template name
            safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in template_name)
            safe_name = safe_name.strip().replace(" ", "_")

            template_path = templates_dir / f"{safe_name}.md"

            if template_path.exists():
                return {
                    "success": False,
                    "error": f"Template '{safe_name}' already exists"
                }

            template_path.write_text(content, encoding='utf-8')
            self.fix_file_ownership(template_path)

            return {
                "success": True,
                "message": f"Created template '{safe_name}'",
                "path": str(template_path.relative_to(vault))
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # ========================================================================
    # SMART LINKING
    # ========================================================================

    def find_linkable_notes(
        self,
        content: str,
        current_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Find notes in vault that should be linked from content.

        Args:
            content: Text to analyze for potential links
            current_file: Current file path to exclude from results

        Returns:
            dict: Suggested links with context
        """
        try:
            vault = self.get_vault_path()
            suggestions = []

            # Get all note titles and job numbers
            linkable_items = []

            # Collect daily notes from configured location
            daily_notes_dir = vault / self.settings.daily_notes_folder
            if daily_notes_dir.exists():
                for note in daily_notes_dir.glob("*.md"):
                    linkable_items.append({
                        "title": note.stem,
                        "path": str(note.relative_to(vault)),
                        "type": "daily-note"
                    })

            # Collect notes from all user folders (excluding system folders)
            for folder in vault.iterdir():
                if folder.is_dir() and not folder.name.startswith('.'):
                    # Skip system folders
                    if folder.name in [self.settings.inbox_folder.split('/')[0],
                                       self.settings.daily_notes_folder.split('/')[0],
                                       self.settings.templates_folder.split('/')[0],
                                       self.settings.attachments_folder.split('/')[0]]:
                        continue
                    for note in folder.rglob("*.md"):
                        linkable_items.append({
                            "title": note.stem,
                            "path": str(note.relative_to(vault)),
                            "type": "note"
                        })

            # Check content for mentions
            content_lower = content.lower()

            for item in linkable_items:
                # Skip current file
                if current_file and item['path'] == current_file:
                    continue

                title_lower = item['title'].lower()

                # Check if title appears in content (not already linked)
                if title_lower in content_lower:
                    # Make sure it's not already a wikilink
                    if f"[[{item['title']}]]" not in content:
                        suggestions.append({
                            "text": item['title'],
                            "link": f"[[{item['title']}]]",
                            "target_path": item['path'],
                            "type": item['type']
                        })

            return {
                "success": True,
                "suggestions": suggestions[:10],  # Limit to top 10
                "count": len(suggestions)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def auto_link_content(
        self,
        content: str,
        current_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Automatically add wikilinks to content.

        Args:
            content: Text to add links to
            current_file: Current file path

        Returns:
            dict: Linked content and list of links added
        """
        try:
            suggestions = self.find_linkable_notes(content, current_file)

            if not suggestions.get('success') or not suggestions.get('suggestions'):
                return {
                    "success": True,
                    "content": content,
                    "links_added": []
                }

            linked_content = content
            links_added = []

            # Sort by length (longest first) to avoid partial replacements
            sorted_suggestions = sorted(suggestions['suggestions'],
                                       key=lambda x: len(x['text']),
                                       reverse=True)

            for suggestion in sorted_suggestions:
                text = suggestion['text']
                link = suggestion['link']

                # Replace first occurrence only (case-insensitive)
                import re
                pattern = re.compile(re.escape(text), re.IGNORECASE)
                match = pattern.search(linked_content)

                if match and f"[[{text}]]" not in linked_content:
                    linked_content = linked_content[:match.start()] + link + linked_content[match.end():]
                    links_added.append({
                        "text": text,
                        "link": link,
                        "target": suggestion['target_path']
                    })

            return {
                "success": True,
                "content": linked_content,
                "links_added": links_added,
                "count": len(links_added)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # ========================================================================
    # TAG MANAGEMENT
    # ========================================================================

    def suggest_tags(
        self,
        content: str,
        existing_tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze content and suggest relevant tags using GPT-4o-mini.

        Args:
            content: Note content to analyze
            existing_tags: List of tags already in the note

        Returns:
            dict: Suggested tags
        """
        try:
            import os
            from openai import OpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                return {
                    "success": False,
                    "error": "OpenAI API key not configured"
                }

            client = OpenAI(api_key=api_key)

            # Get vault-wide tag taxonomy
            vault_tags = self.get_all_tags()

            prompt = f"""Analyze this note content and suggest 3-4 highly relevant tags.

Existing vault tags (prefer these): {', '.join(vault_tags[:30]) if vault_tags else 'None yet'}

Note content:
{content[:1000]}

Rules:
1. Suggest EXACTLY 3-4 tags (no more, no less)
2. Use existing vault tags when applicable
3. Create new tags only if necessary
4. Use lowercase, hyphenated format (e.g., "machine-learning", "proxmox-setup")
5. Focus on the MOST IMPORTANT topics, projects, or categories
6. Avoid overly generic tags like "notes", "misc", or "general"
7. Prioritize actionable/searchable tags

Return ONLY a comma-separated list of 3-4 tags, nothing else."""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a knowledge management assistant that suggests relevant tags for notes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=100
            )

            suggested_tags_text = response.choices[0].message.content.strip()
            suggested_tags = [tag.strip() for tag in suggested_tags_text.split(',')]

            # Filter out existing tags
            if existing_tags:
                suggested_tags = [tag for tag in suggested_tags if tag not in existing_tags]

            return success_response(
                f"Suggested {len(suggested_tags)} tag(s)",
                data={
                    "suggested_tags": suggested_tags,
                    "count": len(suggested_tags),
                    "action": "suggested"
                },
                # Legacy fields
                suggested_tags=suggested_tags,
                count=len(suggested_tags)
            )

        except Exception as e:
            return error_response(str(e))

    def get_all_tags(self) -> List[str]:
        """
        Extract all tags currently used in the vault.

        Returns:
            list: All unique tags
        """
        try:
            vault = self.get_vault_path()
            all_tags = set()

            # Search all markdown files for tags in frontmatter
            for md_file in vault.rglob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')

                    # Extract frontmatter tags
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            frontmatter = parts[1]

                            # Look for tags line
                            for line in frontmatter.split('\n'):
                                if line.strip().startswith('tags:'):
                                    # Extract tags from [tag1, tag2] or tags: tag1, tag2 format
                                    tags_text = line.split('tags:', 1)[1].strip()
                                    tags_text = tags_text.strip('[]')
                                    tags = [t.strip().strip('"\'') for t in tags_text.split(',')]
                                    all_tags.update(tags)
                except:
                    continue

            return sorted(list(all_tags))

        except Exception as e:
            return []

    def apply_tags_to_note(
        self,
        file_path: str,
        tags: List[str]
    ) -> Dict[str, Any]:
        """
        Add tags to a note's frontmatter.

        Args:
            file_path: Relative path to note
            tags: List of tags to add

        Returns:
            dict: Success status
        """
        try:
            vault = self.get_vault_path()

            # Validate and resolve path
            try:
                note_path = safe_vault_path(vault, file_path, must_exist=True)
            except VaultPathError as e:
                return {
                    "success": False,
                    "error": str(e)
                }

            content = note_path.read_text(encoding='utf-8')

            # Parse frontmatter
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    body = parts[2]

                    # Check if tags exist
                    if 'tags:' in frontmatter:
                        # Update existing tags
                        lines = frontmatter.split('\n')
                        new_lines = []
                        for line in lines:
                            if line.strip().startswith('tags:'):
                                # Extract existing tags
                                existing_tags_text = line.split('tags:', 1)[1].strip()
                                existing_tags_text = existing_tags_text.strip('[]')
                                existing_tags = [t.strip().strip('"\'') for t in existing_tags_text.split(',') if t.strip()]

                                # Merge with new tags
                                all_tags = list(set(existing_tags + tags))
                                new_lines.append(f"tags: [{', '.join(all_tags)}]")
                            else:
                                new_lines.append(line)
                        frontmatter = '\n'.join(new_lines)
                    else:
                        # Add tags to frontmatter
                        frontmatter += f"\ntags: [{', '.join(tags)}]"

                    # Reconstruct note
                    new_content = f"---{frontmatter}---{body}"
                else:
                    # Malformed frontmatter, add new one
                    new_content = f"---\ntags: [{', '.join(tags)}]\n---\n\n{content}"
            else:
                # No frontmatter, add it
                new_content = f"---\ntags: [{', '.join(tags)}]\n---\n\n{content}"

            note_path.write_text(new_content, encoding='utf-8')

            return success_response(
                f"Added {len(tags)} tag(s) to {file_path}",
                data={
                    "path": file_path,
                    "tags_added": tags,
                    "count": len(tags),
                    "action": "tagged"
                }
            )

        except Exception as e:
            return error_response(str(e), data={"path": file_path})

    # ========================================================================
    # GRAPH ANALYSIS
    # ========================================================================

    def build_vault_graph(self) -> Dict[str, Any]:
        """
        Build a network graph of all notes and their [[wikilink]] connections.

        Returns:
            dict: Graph data with nodes and edges
        """
        try:
            vault = self.get_vault_path()

            # Store graph as nodes and edges
            nodes = {}  # {file_path: {title, tags, links_out, links_in}}
            edges = []  # [(source, target)]

            # First pass: collect all notes
            for md_file in vault.rglob("*.md"):
                file_path = str(md_file.relative_to(vault))

                # Skip templates
                if file_path.startswith("Templates/"):
                    continue

                try:
                    content = md_file.read_text(encoding='utf-8')

                    # Extract title (first # heading or filename)
                    title = md_file.stem
                    for line in content.split('\n'):
                        if line.startswith('# '):
                            title = line[2:].strip()
                            break

                    # Extract tags
                    tags = []
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            frontmatter = parts[1]
                            for line in frontmatter.split('\n'):
                                if line.strip().startswith('tags:'):
                                    tags_text = line.split('tags:', 1)[1].strip().strip('[]')
                                    tags = [t.strip().strip('"\'') for t in tags_text.split(',') if t.strip()]

                    # Extract [[wikilinks]]
                    import re
                    wikilinks = re.findall(r'\[\[([^\]]+)\]\]', content)

                    nodes[file_path] = {
                        "title": title,
                        "tags": tags,
                        "links_out": wikilinks,
                        "links_in": [],
                        "path": file_path
                    }

                except Exception:
                    continue

            # Second pass: build edges and backlinks
            for source_path, node_data in nodes.items():
                for link_text in node_data["links_out"]:
                    # Find target note (could be title, filename, or date)
                    target_path = None

                    # Try exact match on titles
                    for path, data in nodes.items():
                        if data["title"] == link_text or path.endswith(f"{link_text}.md"):
                            target_path = path
                            break

                    if target_path and target_path != source_path:
                        edges.append((source_path, target_path))
                        nodes[target_path]["links_in"].append(source_path)

            return {
                "success": True,
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "total_notes": len(nodes),
                    "total_links": len(edges),
                    "avg_links_per_note": len(edges) / len(nodes) if len(nodes) > 0 else 0
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def find_orphaned_notes(self) -> Dict[str, Any]:
        """
        Find notes with no incoming or outgoing links.

        Returns:
            dict: List of orphaned notes
        """
        try:
            graph = self.build_vault_graph()

            if not graph.get('success'):
                return graph

            nodes = graph['nodes']
            orphans = []

            for path, data in nodes.items():
                if len(data['links_in']) == 0 and len(data['links_out']) == 0:
                    orphans.append({
                        "path": path,
                        "title": data['title'],
                        "tags": data['tags']
                    })

            return {
                "success": True,
                "orphans": orphans,
                "count": len(orphans),
                "percentage": (len(orphans) / len(nodes) * 100) if len(nodes) > 0 else 0
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def suggest_connections(
        self,
        file_path: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Suggest potential connections based on shared tags, similar titles, or content.

        Args:
            file_path: Optional specific note to analyze (or analyze all)
            limit: Max suggestions to return

        Returns:
            dict: Suggested connections
        """
        try:
            graph = self.build_vault_graph()

            if not graph.get('success'):
                return graph

            nodes = graph['nodes']
            suggestions = []

            # If specific file, find connections for it
            if file_path:
                if file_path not in nodes:
                    return {
                        "success": False,
                        "error": f"Note not found: {file_path}"
                    }

                source_node = nodes[file_path]
                source_tags = set(source_node['tags'])
                already_linked = set(source_node['links_out'])

                for target_path, target_node in nodes.items():
                    if target_path == file_path or target_path in already_linked:
                        continue

                    # Calculate similarity score
                    score = 0
                    reasons = []

                    # Shared tags (high weight)
                    target_tags = set(target_node['tags'])
                    shared_tags = source_tags & target_tags
                    if shared_tags:
                        score += len(shared_tags) * 3
                        reasons.append(f"Shared tags: {', '.join(shared_tags)}")

                    # Similar titles (medium weight)
                    source_words = set(source_node['title'].lower().split())
                    target_words = set(target_node['title'].lower().split())
                    shared_words = source_words & target_words
                    if len(shared_words) > 0:
                        score += len(shared_words) * 2
                        reasons.append(f"Similar titles: {', '.join(shared_words)}")

                    # If any score, add suggestion
                    if score > 0:
                        suggestions.append({
                            "source": file_path,
                            "target": target_path,
                            "target_title": target_node['title'],
                            "score": score,
                            "reasons": reasons
                        })
            else:
                # Find top unconnected pairs across entire vault
                for source_path, source_node in nodes.items():
                    source_tags = set(source_node['tags'])
                    already_linked = set(source_node['links_out'])

                    for target_path, target_node in nodes.items():
                        if target_path <= source_path or target_path in already_linked:
                            continue

                        target_tags = set(target_node['tags'])
                        shared_tags = source_tags & target_tags

                        if len(shared_tags) >= 2:  # At least 2 shared tags
                            suggestions.append({
                                "source": source_path,
                                "target": target_path,
                                "source_title": source_node['title'],
                                "target_title": target_node['title'],
                                "score": len(shared_tags) * 3,
                                "reasons": [f"Shared tags: {', '.join(shared_tags)}"]
                            })

            # Sort by score and limit
            suggestions.sort(key=lambda x: x['score'], reverse=True)
            suggestions = suggestions[:limit]

            # Add metadata about vault state
            vault_stats = {
                "total_notes": len(nodes),
                "has_tags": sum(1 for n in nodes.values() if n['tags']),
                "has_links": sum(1 for n in nodes.values() if n['links_out'] or n['links_in'])
            }

            return {
                "success": True,
                "suggestions": suggestions,
                "count": len(suggestions),
                "vault_stats": vault_stats
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def analyze_clusters(self) -> Dict[str, Any]:
        """
        Identify clusters/communities of related notes based on tags.

        Returns:
            dict: Clusters of related notes with tag-based groupings
        """
        try:
            graph = self.build_vault_graph()

            if not graph.get('success'):
                return graph

            nodes = graph['nodes']

            # Simple clustering by tags
            tag_clusters = {}

            for path, data in nodes.items():
                for tag in data['tags']:
                    if tag not in tag_clusters:
                        tag_clusters[tag] = []
                    tag_clusters[tag].append({
                        "path": path,
                        "title": data['title']
                    })

            # Sort by cluster size
            clusters = [
                {
                    "tag": tag,
                    "notes": notes,
                    "size": len(notes)
                }
                for tag, notes in tag_clusters.items()
            ]
            clusters.sort(key=lambda x: x['size'], reverse=True)

            return {
                "success": True,
                "clusters": clusters[:10],  # Top 10 clusters
                "total_clusters": len(clusters)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # ========================================================================
    # RESEARCH
    # ========================================================================

    def research_and_save(
        self,
        topic: str,
        save_location: Optional[str] = None,
        depth: str = "quick"
    ) -> Dict[str, Any]:
        """
        Research a topic on the web and save to vault.

        Args:
            topic: What to research
            save_location: Where to save (folder name or specific file path).
                          Defaults to inbox folder if not specified.
            depth: "quick" (1-2 sources) or "detailed" (5+ sources)

        Returns:
            dict: Success status with summary
        """
        # Default to inbox folder if not specified
        if save_location is None:
            save_location = self.settings.inbox_folder
        try:
            import os
            import requests
            from openai import OpenAI

            # Use DuckDuckGo Instant Answer API (free, no key needed)
            ddg_url = "https://api.duckduckgo.com/"
            params = {
                "q": topic,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1
            }

            response = requests.get(ddg_url, params=params, timeout=10)
            ddg_data = response.json()

            # Extract useful information
            summary = ddg_data.get("Abstract", "")
            source = ddg_data.get("AbstractSource", "")
            url = ddg_data.get("AbstractURL", "")

            # Get related topics
            related = [r.get("Text", "") for r in ddg_data.get("RelatedTopics", [])[:5] if isinstance(r, dict) and "Text" in r]

            # If no abstract, try to get from related topics
            if not summary and related:
                summary = "\n- ".join(related[:3])

            if not summary:
                summary = f"No detailed summary found. Try searching for '{topic}' manually."

            # Use GPT-4o-mini to format and enhance the summary
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key and summary != f"No detailed summary found. Try searching for '{topic}' manually.":
                client = OpenAI(api_key=api_key)

                prompt = f"""Summarize this information about '{topic}' in a clear, structured format suitable for note-taking:

Source: {source}
URL: {url}

Summary:
{summary}

Related topics:
{chr(10).join(f'- {r}' for r in related)}

Create a concise, well-organized summary with key points. Include the source URL."""

                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a research assistant that creates concise, well-structured summaries for knowledge management."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=500 if depth == "quick" else 1000
                )

                formatted_summary = completion.choices[0].message.content
            else:
                formatted_summary = f"# {topic}\n\n{summary}\n\n**Source:** {source}\n**URL:** {url}"

            # Determine where to save
            vault = self.get_vault_path()

            # Check if save_location is an existing folder (dynamic detection)
            try:
                potential_folder = safe_vault_path(vault, save_location, must_exist=False)
            except VaultPathError as e:
                return {
                    "success": False,
                    "error": f"Invalid save location: {e}"
                }

            if potential_folder.exists() and potential_folder.is_dir():
                # Save to folder as new note
                folder = potential_folder

                # Create filename from topic
                safe_filename = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)
                safe_filename = safe_filename.strip().replace(" ", "_")[:50]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                filename = f"{safe_filename}_{timestamp}.md"
                try:
                    validate_filename(filename)
                except VaultPathError:
                    # Fallback to simple timestamp if validation fails
                    filename = f"research_{timestamp}.md"

                note_path = folder / filename
                note_path.write_text(formatted_summary, encoding='utf-8')

                save_path = str(note_path.relative_to(vault))
                action_taken = "created_new_file"

            elif save_location.endswith('.md'):
                # Explicit file path - append to existing or create new
                try:
                    note_path = safe_vault_path(vault, save_location, must_exist=False)
                except VaultPathError as e:
                    return {
                        "success": False,
                        "error": f"Invalid file path: {e}"
                    }

                if not note_path.exists():
                    # Create new note
                    note_path.parent.mkdir(parents=True, exist_ok=True)
                    note_path.write_text(f"# Research Notes\n\n{formatted_summary}", encoding='utf-8')
                    action_taken = "created_new_file"
                else:
                    # Append to existing
                    with note_path.open('a', encoding='utf-8') as f:
                        f.write(f"\n\n---\n\n{formatted_summary}")
                    action_taken = "appended_to_existing"

                save_path = save_location

            else:
                # Not a valid folder or .md file path
                available_folders = [f.name for f in vault.iterdir() if f.is_dir() and not f.name.startswith('.')]
                return {
                    "success": False,
                    "error": f"'{save_location}' is not a valid folder or file path. Available folders: {', '.join(available_folders)}. Or use a path ending in .md to append to a specific note."
                }

            return {
                "success": True,
                "message": f"✅ Researched '{topic}' and {action_taken.replace('_', ' ')} at: {save_path}",
                "summary": formatted_summary[:200] + "..." if len(formatted_summary) > 200 else formatted_summary,
                "path": save_path,
                "absolute_path": str(note_path),
                "action": action_taken
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Singleton instance
_obsidian_service_instance = None


def get_obsidian_service(vault_path=None):
    """
    Get the singleton ObsidianService instance.

    Args:
        vault_path: Optional vault path. If provided on first call, sets the vault path.
                   Subsequent calls ignore this parameter and return the existing instance.

    Returns:
        ObsidianService: The singleton instance
    """
    global _obsidian_service_instance
    if _obsidian_service_instance is None:
        _obsidian_service_instance = ObsidianService(vault_path)
    return _obsidian_service_instance
