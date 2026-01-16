"""
Pydantic validation models for Obsidian vault tool parameters.

These models provide type safety, validation, and clear error messages
when the LLM provides incorrect parameters to vault functions.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class AppendToDailyNoteParams(BaseModel):
    """Parameters for append_to_daily_note function."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Content to add to daily note"
    )
    section: Literal[
        "Quick Captures",
        "Work Notes",
        "Personal Notes",
        "Tasks",
    ] = Field(
        default="Quick Captures",
        description="Section to append to"
    )
    date: Optional[str] = Field(
        default=None,
        description="Optional date (YYYY-MM-DD) for a specific daily note"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is not just whitespace."""
        if not v.strip():
            raise ValueError("Content cannot be empty or whitespace")
        return v

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        """Validate optional date string."""
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Date must be in YYYY-MM-DD format") from exc
        return v


class CreateSimpleNoteParams(BaseModel):
    """Parameters for create_simple_note function."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Note title (used as filename)"
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Note content in markdown"
    )
    folder: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Folder to create note in"
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Sanitize title for use as filename."""
        if not v.strip():
            raise ValueError("Title cannot be empty")
        if "/" in v or chr(92) in v:
            raise ValueError("Title cannot contain path separators")
        return v

    @field_validator("folder")
    @classmethod
    def validate_folder(cls, v: str) -> str:
        """Ensure folder is a valid name."""
        if not v.strip():
            raise ValueError("Folder cannot be empty")
        if ".." in v or v.startswith("/") or v.startswith(chr(92)):
            raise ValueError("Invalid folder path")
        return v


class UpdateNoteSectionParams(BaseModel):
    """Parameters for update_note_section function."""

    file_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Relative path to note"
    )
    section_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name of section to update"
    )
    new_content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="New content for the section"
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("File path cannot be empty")
        if not v.endswith(".md"):
            raise ValueError("File path must end with .md")
        if v.startswith("/") or v.startswith(chr(92)) or ":" in v or ".." in v:
            raise ValueError("File path must be relative")
        return v

    @field_validator("section_name")
    @classmethod
    def validate_section_name(cls, v: str) -> str:
        """Ensure section name is valid."""
        if not v.strip():
            raise ValueError("Section name cannot be empty")
        if v.startswith("#"):
            raise ValueError("Section name should not include '#' prefix")
        return v


class CreateFromTemplateParams(BaseModel):
    """Parameters for create_from_template function."""

    template_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Template name (without .md)"
    )
    destination: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Destination folder or full path"
    )
    variables: Optional[dict] = Field(
        default=None,
        description="Variables for template substitution"
    )

    @field_validator("template_name")
    @classmethod
    def validate_template_name(cls, v: str) -> str:
        """Ensure template name is valid."""
        if not v.strip():
            raise ValueError("Template name cannot be empty")
        if v.endswith(".md"):
            v = v[:-3]
        if "/" in v or chr(92) in v:
            raise ValueError("Template name cannot contain path separators")
        return v

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, v: str) -> str:
        """Basic destination validation."""
        if not v.strip():
            raise ValueError("Destination cannot be empty")
        if v.startswith("/") or v.startswith(chr(92)) or ":" in v:
            raise ValueError("Destination must be relative")
        return v


class DeleteNoteParams(BaseModel):
    """Parameters for delete_note function."""

    file_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Relative path to the note to delete"
    )
    dry_run: bool = Field(
        default=False,
        description="Preview deletion without executing"
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("File path cannot be empty")
        if not v.endswith(".md"):
            raise ValueError("File path must end with .md")
        if v.startswith("/") or v.startswith(chr(92)) or ":" in v or ".." in v:
            raise ValueError("File path must be relative to the vault")
        return v


# ============================================================================
# PHASE 2 MODELS - New tool parameters
# ============================================================================

class UpdateNoteParams(BaseModel):
    """Parameters for update_note function."""

    file_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Path to note"
    )
    new_content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="New content for the note"
    )
    mode: Literal["replace", "append", "prepend"] = Field(
        default="replace",
        description="How to apply changes"
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        if not v.endswith(".md"):
            raise ValueError("File path must end with .md")
        if v.startswith("/") or v.startswith(chr(92)) or ".." in v:
            raise ValueError("File path must be relative")
        return v


class RenameNoteParams(BaseModel):
    """Parameters for rename_note function."""

    file_path: str = Field(..., description="Current path")
    new_title: str = Field(..., min_length=1, max_length=200, description="New title")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        if not v.endswith(".md"):
            raise ValueError("Must end with .md")
        return v


class MoveNoteParams(BaseModel):
    """Parameters for move_note function."""

    file_path: str = Field(..., description="Current path")
    destination_folder: str = Field(..., description="Target folder")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        if not v.endswith(".md"):
            raise ValueError("Must end with .md")
        return v


class ListFolderParams(BaseModel):
    """Parameters for list_folder function."""

    folder_name: str = Field(..., description="Folder to list")


class AddTagsParams(BaseModel):
    """Parameters for add_tags function."""

    file_path: str = Field(..., description="Path to note")
    tags: list[str] = Field(..., min_items=1, description="Tags to add")
    mode: Literal["add", "replace"] = Field(default="add")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return [tag.lower() for tag in v]


class GetTodayTasksParams(BaseModel):
    """Parameters for get_today_tasks function."""

    date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be YYYY-MM-DD")
        return v


class FindRelatedNotesParams(BaseModel):
    """Parameters for find_related_notes function."""

    file_path: str = Field(..., description="Note to find connections for")
    limit: int = Field(default=5, ge=1, le=20)


class SearchVaultParams(BaseModel):
    """Parameters for search_vault function."""

    query: str = Field(..., min_length=1, description="Search query")
    limit: int = Field(default=5, ge=1, le=20)


class CreateLinkParams(BaseModel):
    """Parameters for create_link function."""

    source_file: str = Field(..., description="Note to add link from")
    target_file: str = Field(..., description="Note to link to")
    link_text: Optional[str] = Field(None, description="Display text for link")


# Export all parameter models
__all__ = [
    "AppendToDailyNoteParams",
    "CreateSimpleNoteParams",
    "UpdateNoteSectionParams",
    "CreateFromTemplateParams",
    "DeleteNoteParams",
    "UpdateNoteParams",
    "RenameNoteParams",
    "MoveNoteParams",
    "ListFolderParams",
    "AddTagsParams",
    "GetTodayTasksParams",
    "FindRelatedNotesParams",
    "SearchVaultParams",
    "CreateLinkParams",
]
