"""
Standardized response format for Obsidian vault operations.

All vault functions should return responses in this format for consistency
and predictability in tool calling and UI rendering.
"""

from typing import Any, Optional


def success_response(
    message: str,
    data: Optional[dict] = None,
    **legacy_fields
) -> dict:
    """
    Create a successful operation response.

    Args:
        message: Human-readable success message
        data: Structured data about the operation (optional)
        **legacy_fields: Backward compatibility fields (will be merged)

    Returns:
        Standardized success response

    Example:
        >>> success_response(
        ...     "Created note successfully",
        ...     data={"path": "Reference/test.md", "created": True},
        ...     path="Reference/test.md"  # legacy compatibility
        ... )
        {
            "success": True,
            "message": "Created note successfully",
            "data": {"path": "Reference/test.md", "created": True},
            "path": "Reference/test.md"  # legacy field preserved
        }
    """
    response = {
        "success": True,
        "message": message,
    }

    # Add data if provided
    if data is not None:
        response["data"] = data

    # Add legacy fields for backward compatibility
    response.update(legacy_fields)

    return response


def error_response(
    error: str,
    data: Optional[dict] = None,
    **legacy_fields
) -> dict:
    """
    Create an error response.

    Args:
        error: Error message describing what went wrong
        data: Additional error context (optional)
        **legacy_fields: Backward compatibility fields

    Returns:
        Standardized error response

    Example:
        >>> error_response(
        ...     "File not found",
        ...     data={"path": "missing.md", "exists": False}
        ... )
        {
            "success": False,
            "error": "File not found",
            "data": {"path": "missing.md", "exists": False}
        }
    """
    response = {
        "success": False,
        "error": error,
    }

    # Add data if provided
    if data is not None:
        response["data"] = data

    # Add legacy fields for backward compatibility
    response.update(legacy_fields)

    return response


def dry_run_response(
    message: str,
    data: Optional[dict] = None,
    **legacy_fields
) -> dict:
    """
    Create a dry-run response (preview without execution).

    Args:
        message: Description of what would happen
        data: Preview data
        **legacy_fields: Backward compatibility fields

    Returns:
        Standardized dry-run response

    Example:
        >>> dry_run_response(
        ...     "Would create note at Reference/test.md",
        ...     data={"path": "Reference/test.md", "action": "create"}
        ... )
        {
            "success": True,
            "dry_run": True,
            "message": "Would create note at Reference/test.md",
            "data": {"path": "Reference/test.md", "action": "create"}
        }
    """
    response = {
        "success": True,
        "dry_run": True,
        "message": message,
    }

    # Add data if provided
    if data is not None:
        response["data"] = data

    # Add legacy fields for backward compatibility
    response.update(legacy_fields)

    return response
