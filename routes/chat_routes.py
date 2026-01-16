"""
Chat Routes Blueprint

This module contains all chat-related routes extracted from app.py.
Includes chat CRUD operations, messaging endpoints, search, tags, and export functionality.
"""

from flask import Blueprint, render_template, request, Response, jsonify, g
import os
import csv
import datetime
import json
import uuid
import base64
import time
import subprocess
import pytz

from openai import OpenAI

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

import ollama
import structlog

# Configuration
from config import get_settings

# Local modules
from prices import (
    allowed_models,
    get_model_meta,
    prices_for,
    DEFAULT_MODEL,
    is_local_model,
    streaming_supported,
    get_provider_type,
)
from storage import (
    new_chat,
    load_chat,
    save_chat,
    list_chats,
    rename_chat,
    append_message,
    delete_chat,
)
from context_aware import (
    initialize_context,
    update_context_from_tool,
    format_context_for_prompt,
    should_include_context,
)
from rag_db import search as rag_search, get_db
from rag import chunk_text, embed_texts
from chat_db import get_chat_db
from obsidian_functions import OBSIDIAN_FUNCTIONS, execute_obsidian_function
from observability import log_tool_call
from tool_schema import validate_tool_call

# Service layer imports
from services.llm_service import LLMService
from services.conversation_service import ConversationService
from services.cost_tracking_service import CostTrackingService

# Initialize settings
settings = get_settings()
logger = structlog.get_logger()

# Initialize Ollama client
ollama_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))

# Tool-calling guard constants and helpers
WRITE_INTENT_VERBS = (
    "create",
    "add",
    "update",
    "write",
    "append",
    "insert",
    "put in",
    "record",
    "log",
    "capture",
    "populate",
    "fill",
)
WRITE_INTENT_TARGETS = (
    "note",
    "job",
    "vault",
    "file",
    "folder",
    "schedule",
    "entry",
    "task",
    "daily",
    "document",
    "list",
)
READ_INTENT_VERBS = (
    "check",
    "read",
    "search",
    "find",
    "look",
    "show",
    "list",
    "get",
    "what",
    "where",
    "is there",
    "do i have",
    "did i",
)
READ_INTENT_TARGETS = (
    "note",
    "vault",
    "file",
    "folder",
    "task",
    "todo",
    "project",
    "attachment",
    "receipt",
    "daily",
    "template",
    "list",
)
WRITE_VERIFICATION_FUNCTIONS = {
    # File creation
    "create_simple_note",
    "create_job_note",
    "create_from_template",
    "create_custom_template",

    # Content modification
    "update_note",
    "update_note_section",
    "replace_note_content",

    # Append operations
    "append_to_daily_note",

    # Metadata operations
    "apply_tags_to_note",

    # Special operations
    "research_and_save",
    "create_scheduled_task",
}
WRITE_TOOL_REMINDER = (
    "Reminder: Vault operations require calling the appropriate Obsidian tool. "
    "Do not claim success until the tool call succeeds."
)
READ_TOOL_REMINDER = (
    "Reminder: This request requires checking the vault or task list. "
    "Use the appropriate tool to retrieve the information."
)


def message_requires_write_tool(user_text: str) -> bool:
    """Heuristic check to see if the user is asking for a write operation."""
    if not settings.require_tool_for_writes:
        return False
    if not user_text:
        return False
    lowered = user_text.lower()
    if not any(verb in lowered for verb in WRITE_INTENT_VERBS):
        return False
    return any(target in lowered for target in WRITE_INTENT_TARGETS)


def insert_write_tool_reminder(messages: list, reminder: str = WRITE_TOOL_REMINDER):
    """Insert a system reminder just after the existing system messages."""
    reminder_msg = {"role": "system", "content": reminder}
    system_count = sum(1 for m in messages if m.get("role") == "system")
    messages.insert(system_count, reminder_msg)


def message_requires_read_tool(user_text: str) -> bool:
    """Heuristic check to see if the user is asking for a read/search operation."""
    if not settings.require_tool_for_reads:
        return False
    if not user_text:
        return False
    lowered = user_text.lower()
    if not any(verb in lowered for verb in READ_INTENT_VERBS):
        return False
    return any(target in lowered for target in READ_INTENT_TARGETS)


def insert_read_tool_reminder(messages: list, reminder: str = READ_TOOL_REMINDER):
    """Insert a read-tool reminder just after the existing system messages."""
    reminder_msg = {"role": "system", "content": reminder}
    system_count = sum(1 for m in messages if m.get("role") == "system")
    messages.insert(system_count, reminder_msg)


def _normalized_fragment(text: str, limit=None) -> str:
    fragment = (text or "").strip()
    if not fragment:
        return ""
    fragment = fragment.replace("\r", " ").replace("\n", " ")
    if limit is not None and limit > 0:
        fragment = fragment[:limit]
    return " ".join(fragment.split())


def verify_tool_result(function_name: str, arguments: dict, result: dict):
    """
    Comprehensive read-after-write verification for vault write operations.

    Uses the centralized obsidian_verification module for operation-specific
    verification logic across all 11 write operations.

    Returns:
        Tuple of (status, error_message, details_dict)
        - status: "passed" | "failed" | "skipped"
        - error_message: Error description if failed, None otherwise
        - details_dict: Verification details for logging/debugging
    """
    # Gracefully handle import failures (e.g., permission errors on bind-mounted files)
    try:
        from utils.obsidian_verification import verify_operation, WRITE_OPERATIONS
    except (ImportError, PermissionError, OSError) as import_err:
        logger.error(
            "verify_tool_import_failed",
            function_name=function_name,
            error=str(import_err),
            exc_info=True
        )
        # Skip verification but don't crash - allow the tool result to pass through
        return ("skipped", None, {
            "reason": "verification_module_unavailable",
            "error": str(import_err)
        })

    # Debug logging
    logger.debug(
        "verify_tool_start",
        function_name=function_name,
        result_keys=list(result.keys()) if result else None,
        file_path=result.get("file_path") if result else None
    )

    # Skip verification if disabled in config
    if not settings.verify_vault_writes:
        return ("skipped", None, {"reason": "verification_disabled"})

    # Skip if not a write operation
    if function_name not in WRITE_OPERATIONS:
        return ("skipped", None, {"reason": "not_write_operation"})

    # Skip if operation reported failure
    if not result or not result.get("success"):
        return ("skipped", None, {"reason": "operation_failed"})

    # Run comprehensive verification
    try:
        verification = verify_operation(function_name, arguments, result)

        if verification.success:
            logger.info(
                "verify_tool_passed",
                function_name=function_name,
                checks_passed=verification.checks_passed
            )
            return ("passed", None, {
                "checks_passed": verification.checks_passed,
                "details": verification.details
            })
        else:
            logger.warning(
                "verify_tool_failed",
                function_name=function_name,
                checks_failed=verification.checks_failed,
                suggestions=verification.suggestions
            )
            return ("failed", verification.details, {
                "checks_passed": verification.checks_passed,
                "checks_failed": verification.checks_failed,
                "suggestions": verification.suggestions
            })

    except Exception as e:
        logger.error(
            "verify_tool_error",
            function_name=function_name,
            error=str(e),
            exc_info=True
        )
        return ("failed", f"Verification error: {str(e)}", {
            "error": str(e),
            "exception_type": type(e).__name__
        })


def trim_history(messages, model: str, max_tokens: int | None = None):
    """Trim message history to fit within model's context window."""
    import tiktoken

    if max_tokens is None:
        model_limits = {
            "gpt-4": 8192,
            "gpt-4-turbo": 128000,
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-5": 200000,
            "gpt-5-mini": 200000,
            "gpt-5-nano": 200000,
            "o1-mini": 128000,
            "o1-preview": 128000,
            "o1": 200000,
            "claude-3-5-sonnet-20241022": 200000,
            "claude-3-5-sonnet-20240620": 200000,
            "claude-3-opus-20240229": 200000,
        }
        max_tokens = model_limits.get(model, 8192)

    target = int(max_tokens * 0.7)

    try:
        enc = tiktoken.encoding_for_model(model)
    except Exception:
        enc = tiktoken.get_encoding("cl100k_base")

    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]

    def count_tokens(msgs):
        total = 0
        for m in msgs:
            content = m.get("content", "")
            if isinstance(content, str):
                total += len(enc.encode(content))
        return total

    system_tokens = count_tokens(system_msgs)
    if not other_msgs:
        return system_msgs

    available = target - system_tokens
    if available <= 0:
        return system_msgs + other_msgs[-1:]

    current_tokens = count_tokens(other_msgs)
    if current_tokens <= available:
        return system_msgs + other_msgs

    trimmed_other = []
    running_tokens = 0
    for msg in reversed(other_msgs):
        content = msg.get("content", "")
        if isinstance(content, str):
            msg_tokens = len(enc.encode(content))
        else:
            msg_tokens = 0

        if running_tokens + msg_tokens > available:
            break

        trimmed_other.insert(0, msg)
        running_tokens += msg_tokens

    if not trimmed_other and other_msgs:
        trimmed_other = [other_msgs[-1]]

    return system_msgs + trimmed_other


def robust_usage(resp_usage):
    """Extract token counts from API response usage object."""
    if not resp_usage:
        return 0, 0
    in_tok = getattr(resp_usage, "prompt_tokens", None) or getattr(
        resp_usage, "input_tokens", 0
    )
    out_tok = getattr(resp_usage, "completion_tokens", None) or getattr(
        resp_usage, "output_tokens", 0
    )
    return int(in_tok or 0), int(out_tok or 0)


# Create blueprint
chat_bp = Blueprint('chat', __name__)


# ---------- Pages ----------


@chat_bp.get("/")
def home():
    from utils.auth_utils import get_current_user
    user = get_current_user()
    return render_template("index.html", current_user=user)


# ---------- Chat storage ----------


@chat_bp.post("/new-chat")
def route_new_chat():
    from utils.auth_utils import get_current_user

    title = (request.get_json(silent=True) or {}).get("title") or "New chat"
    user = get_current_user()
    user_id = user['user_id'] if user else None

    return jsonify(new_chat(title, user_id=user_id))


@chat_bp.get("/chats")
def route_list_chats():
    from utils.auth_utils import get_current_user

    user = get_current_user()
    user_id = user['user_id'] if user else None

    return jsonify(list_chats(user_id=user_id))


@chat_bp.get("/chat/<cid>")
def route_get_chat(cid):
    chat = load_chat(cid)
    if not chat:
        return jsonify({"error": "not_found"}), 404
    return jsonify(chat)


@chat_bp.post("/chat/<cid>/rename")
def route_rename_chat(cid):
    title = (request.get_json(force=True).get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Title cannot be empty"}), 400
    ok = rename_chat(cid, title)
    return jsonify({"ok": ok, "title": title})


@chat_bp.delete("/chat/<cid>")
def route_delete_chat(cid):
    from utils.auth_utils import get_current_user

    user = get_current_user()
    user_id = user['user_id'] if user else None

    ok = delete_chat(cid, user_id=user_id)
    return jsonify({"ok": ok})


@chat_bp.post("/chat/<cid>/delete")
def route_delete_chat_post(cid):
    from utils.auth_utils import get_current_user

    user = get_current_user()
    user_id = user['user_id'] if user else None

    ok = delete_chat(cid, user_id=user_id)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not_found"}), 404


# ========================================================================
# ARCHIVE ENDPOINTS
# ========================================================================

@chat_bp.post("/chat/<cid>/archive")
def route_archive_chat(cid):
    """Archive a chat (soft delete)."""
    from utils.auth_utils import get_current_user
    from services.storage_service import get_storage_service

    user = get_current_user()
    user_id = user['user_id'] if user else None

    storage = get_storage_service()
    ok = storage.archive_chat(cid, user_id=user_id)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not_found"}), 404


@chat_bp.post("/chat/<cid>/unarchive")
def route_unarchive_chat(cid):
    """Unarchive a chat (restore from archive)."""
    from utils.auth_utils import get_current_user
    from services.storage_service import get_storage_service

    user = get_current_user()
    user_id = user['user_id'] if user else None

    storage = get_storage_service()
    ok = storage.unarchive_chat(cid, user_id=user_id)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not_found"}), 404


@chat_bp.get("/chats/archived")
def route_list_archived_chats():
    """List all archived chats."""
    from utils.auth_utils import get_current_user
    from services.storage_service import get_storage_service

    user = get_current_user()
    user_id = user['user_id'] if user else None

    storage = get_storage_service()
    return jsonify(storage.list_archived_chats(user_id=user_id))


@chat_bp.post("/chats/bulk-archive")
def route_bulk_archive_chats():
    """Archive multiple chats at once."""
    from utils.auth_utils import get_current_user
    from services.storage_service import get_storage_service

    user = get_current_user()
    user_id = user['user_id'] if user else None

    data = request.get_json(force=True) or {}
    chat_ids = data.get("chatIds", [])

    if not isinstance(chat_ids, list):
        return jsonify({"error": "chatIds must be an array"}), 400

    storage = get_storage_service()
    result = storage.bulk_archive_chats(chat_ids, user_id=user_id)
    return jsonify({"ok": True, **result})


@chat_bp.post("/chats/bulk-unarchive")
def route_bulk_unarchive_chats():
    """Unarchive multiple chats at once."""
    from utils.auth_utils import get_current_user
    from services.storage_service import get_storage_service

    user = get_current_user()
    user_id = user['user_id'] if user else None

    data = request.get_json(force=True) or {}
    chat_ids = data.get("chatIds", [])

    if not isinstance(chat_ids, list):
        return jsonify({"error": "chatIds must be an array"}), 400

    storage = get_storage_service()
    result = storage.bulk_unarchive_chats(chat_ids, user_id=user_id)
    return jsonify({"ok": True, **result})


@chat_bp.post("/chat/<cid>/set-model")
def route_set_chat_model(cid):
    data = request.get_json(force=True) or {}
    model = data.get("model")
    chat = load_chat(cid)
    if not chat:
        return jsonify({"ok": False, "error": "not_found"}), 404
    chat.setdefault("meta", {})
    if model:
        chat["meta"]["pinned_model"] = model
    else:
        chat["meta"].pop("pinned_model", None)
    save_chat(chat)
    return jsonify({"ok": True, "pinned_model": chat["meta"].get("pinned_model")})


@chat_bp.post("/chat/<cid>/budget")
def set_budget(cid):
    chat = load_chat(cid)
    if not chat:
        return {"ok": False, "error": "not_found"}, 404
    b = (request.get_json(force=True) or {}).get("budget")
    try:
        b = float(b)
    except:
        b = None
    chat.setdefault("meta", {})
    chat["meta"]["budget_usd"] = b
    save_chat(chat)
    return {"ok": True, "budget": b}


@chat_bp.get("/chat/<cid>/meta")
def chat_meta(cid):
    chat = load_chat(cid)
    if not chat:
        return {"error": "not_found"}, 404
    m = chat.get("meta", {"budget_usd": None, "spent_usd": 0.0})
    return {"meta": m}


@chat_bp.get("/chat/<cid>/mode")
def get_mode(cid):
    """Get the chat mode for a chat (agentic or chat)."""
    chat_db = get_chat_db()
    mode = chat_db.get_chat_mode(cid)
    return jsonify({"mode": mode})


@chat_bp.post("/chat/<cid>/mode")
def set_mode(cid):
    """Set the chat mode for a chat (agentic or chat)."""
    data = request.get_json(force=True) or {}
    mode = data.get("mode", "agentic")

    if mode not in ("agentic", "chat"):
        return jsonify({"error": "Invalid mode. Must be 'agentic' or 'chat'"}), 400

    chat_db = get_chat_db()
    success = chat_db.set_chat_mode(cid, mode)

    if not success:
        return jsonify({"error": "Chat not found or mode update failed"}), 404

    logger.info("chat_mode_changed", chat_id=cid, mode=mode)
    return jsonify({"success": True, "mode": mode})


# ============== Chat Search & Tags Endpoints ==============


@chat_bp.get("/chats/search")
def search_chats():
    """
    Search across all chat content (messages, titles).
    Query params:
      - q: search query (required)
      - limit: max results (default 50)

    Returns: List of matching chat excerpts with context
    """
    from utils.auth_utils import get_current_user

    query = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 50)

    if not query:
        return jsonify({"error": "query_required"}), 400

    user = get_current_user()
    user_id = user['user_id'] if user else None

    # Use SQLite FTS5 if feature flag is enabled
    if settings.use_sqlite_chats:
        try:
            db = get_chat_db(settings.chat_db_path)
            results = db.search_messages(query, limit=limit, user_id=user_id)

            logger.info(
                "search_executed_sqlite", query=query, result_count=len(results), user_id=user_id
            )

            return jsonify({"query": query, "count": len(results), "results": results})
        except Exception as e:
            logger.error("search_failed", query=query, error=str(e))
            return jsonify({"error": "search_failed"}), 500

    # Fall back to JSON file-based search
    query_lower = query.lower()
    results = []

    # Scan all chat files
    for chat_summary in list_chats():
        cid = chat_summary["id"]
        chat = load_chat(cid)
        if not chat:
            continue

        matches = []

        # Search in title
        if query_lower in chat["title"].lower():
            matches.append({"type": "title", "snippet": chat["title"]})

        # Search in messages
        for idx, msg in enumerate(chat["messages"]):
            content_lower = msg["content"].lower()
            if query_lower in content_lower:
                # Extract context snippet (50 chars before/after)
                pos = content_lower.find(query_lower)
                start = max(0, pos - 50)
                end = min(len(msg["content"]), pos + len(query_lower) + 50)
                snippet = msg["content"][start:end]

                matches.append(
                    {"type": msg["role"], "role": msg["role"], "snippet": snippet}
                )

        if matches:
            results.append(
                {
                    "chat_id": cid,
                    "title": chat["title"],
                    "matches": matches[:5],  # Limit matches per chat
                }
            )

        if len(results) >= limit:
            break

    logger.info("search_executed_json", query=query, result_count=len(results))

    return jsonify({"query": query, "count": len(results), "results": results})


@chat_bp.post("/chat/<cid>/tags")
def set_chat_tags(cid):
    """
    Set tags for a chat.
    Body: { "tags": ["Work", "Research"] }
    """
    data = request.get_json(force=True) or {}
    tags = data.get("tags", [])

    if not isinstance(tags, list):
        return jsonify({"error": "tags_must_be_array"}), 400

    # Validate tags (alphanumeric, max 20 chars each)
    validated_tags = []
    for tag in tags:
        if isinstance(tag, str) and len(tag.strip()) > 0 and len(tag.strip()) <= 20:
            validated_tags.append(tag.strip())

    chat = load_chat(cid)
    if not chat:
        return jsonify({"error": "chat_not_found"}), 404

    # Update tags
    if "meta" not in chat:
        chat["meta"] = {}
    chat["meta"]["tags"] = validated_tags

    save_chat(chat)

    return jsonify({"ok": True, "tags": chat["meta"]["tags"]})


@chat_bp.get("/tags")
def list_all_tags():
    """
    Get all unique tags across all chats with usage counts.
    Returns: { "tags": [{"name": "Work", "count": 5}, ...] }
    """
    tag_counts = {}

    for chat_summary in list_chats():
        chat = load_chat(chat_summary["id"])
        if not chat:
            continue

        tags = chat.get("meta", {}).get("tags", [])
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Sort by count descending
    sorted_tags = [
        {"name": tag, "count": count}
        for tag, count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    return jsonify({"tags": sorted_tags})


@chat_bp.get("/chats/by-tag/<tag>")
def chats_by_tag(tag: str):
    """
    Get all chats with a specific tag.
    """
    matching_chats = []

    for chat_summary in list_chats():
        chat = load_chat(chat_summary["id"])
        if not chat:
            continue

        tags = chat.get("meta", {}).get("tags", [])
        if tag in tags:
            matching_chats.append(
                {
                    "id": chat["id"],
                    "title": chat["title"],
                    "created_at": chat["created_at"],
                    "updated_at": chat["updated_at"],
                    "tags": tags,
                }
            )

    return jsonify({"tag": tag, "count": len(matching_chats), "chats": matching_chats})


# ============== End Chat Search & Tags ==============


@chat_bp.get("/chat/<cid>/export.md")
def chat_export_md(cid):
    chat = load_chat(cid)
    if not chat:
        return "not found", 404
    lines = [f"# {chat.get('title','Chat')}", ""]
    for m in chat["messages"]:
        who = (
            "You"
            if m["role"] == "user"
            else "Assistant" if m["role"] == "assistant" else "System"
        )
        lines.append(f"**{who}:**")
        lines.append(m["content"])
        lines.append("")
    md = "\n".join(lines)
    return Response(
        md,
        mimetype="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=chat-{cid}.md"},
    )


# ---------- Ask Endpoint ----------


@chat_bp.post("/ask")
def ask():
    """
    Main chat endpoint - handles LLM interactions.

    Refactored to use service layer:
    - LLMService handles provider-specific logic
    - ConversationService handles context preparation
    - CostTrackingService handles usage logging and budget tracking
    """
    from utils.auth_utils import get_current_user

    # ==================== REQUEST PARSING ====================
    data = request.get_json(force=True)
    prompt = (data.get("prompt") or "").strip()

    # Extract image data if provided (for vision models)
    image_base64 = data.get("image")  # base64 encoded image
    image_type = data.get("imageType", "image/png")  # MIME type
    image_name = data.get("imageName", "attached_image")  # filename for reference

    # Allow image-only messages (no text required if image attached)
    if not prompt and not image_base64:
        return jsonify({"error": "empty_prompt"}), 400
    if not prompt and image_base64:
        prompt = "[Image]"  # Default prompt for image-only messages

    # Store image in Flask g context for tool execution (save_image_to_vault)
    saved_image_path = None  # Track the auto-saved image path
    if image_base64:
        g.attached_image_base64 = image_base64
        g.attached_image_type = image_type
        g.attached_image_name = image_name

        # Auto-save image to Attachments/ so model can reference/embed it
        try:
            from services.obsidian_service import ObsidianService
            obsidian_service = ObsidianService()

            # Decode base64 image
            image_bytes = base64.b64decode(image_base64)

            # Generate filename from image_name or timestamp
            ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
            ext = ext_map.get(image_type, "png")
            if image_name and image_name != "attached_image":
                filename = f"{image_name}.{ext}" if not image_name.endswith(f".{ext}") else image_name
            else:
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"image_{timestamp}.{ext}"

            # Save to Attachments/
            save_result = obsidian_service.save_image(image_bytes, filename)
            if save_result.get("success"):
                saved_image_path = save_result.get("filename", filename)
                logger.info("auto_saved_image", path=saved_image_path)
        except Exception as e:
            logger.error("auto_save_image_failed", error=str(e))
            # Continue without auto-save - model can still see image for vision

    debug_tool_calls = data.get("debugToolCalls")
    if debug_tool_calls is None:
        debug_tool_calls = data.get("debug_tool_calls")
    if isinstance(debug_tool_calls, str):
        debug_tool_calls = debug_tool_calls.strip().lower() in ("1", "true", "yes", "y")
    debug_tool_calls = bool(debug_tool_calls)

    write_intent = message_requires_write_tool(prompt)
    read_intent = message_requires_read_tool(prompt)

    # Model resolution
    requested_model = (data.get("model") or "").strip()
    model = requested_model if requested_model in allowed_models() else DEFAULT_MODEL

    # Get current user for multi-user support
    user = get_current_user()
    user_id = user['user_id'] if user else None

    # Log chat request
    chat_id = data.get("chatId", "")
    logger.info("chat_request", chat_id=chat_id, model=model, prompt_length=len(prompt), user_id=user_id)

    # Preset/system/temperature knobs
    preset_id_str = (data.get("presetId") or "").strip()
    from rag_db import get_preset_from_db as get_preset
    preset = get_preset(int(preset_id_str)) if preset_id_str else None
    system_prompt = (data.get("system") or "").strip()
    if not system_prompt and preset:
        system_prompt = preset.get("system")
    if not system_prompt:
        # Skip default system prompt for Ollama models - they use their own prompt variant
        provider = get_provider_type(model)
        if provider in ("ollama_tools", "ollama_mcp", "ollama"):
            system_prompt = ""  # Will be handled by llm_service prompt variants
        else:
            system_prompt = "You are a helpful assistant."

    if model in ["gpt-5", "gpt-5-mini", "gpt-5-nano"]:
        temperature = 1.0
    else:
        temperature = data.get("temperature")
        if temperature is None and preset:
            temperature = preset.get("temperature")
        if temperature is None:
            temperature = 0.3
        try:
            temperature = float(temperature)
            temperature = max(0.0, min(1.0, temperature))
        except (ValueError, TypeError):
            temperature = 0.3

    # RAG knobs
    use_rag = bool(data.get("useRag") or False)
    top_k = int(data.get("topK") or 5)

    # ==================== CHAT LOADING & BUDGET CHECK ====================
    chat_id = (data.get("chatId") or "").strip()
    if chat_id:
        chat = load_chat(chat_id)
        if not chat:
            return jsonify({"error": "chat_not_found"}), 404
    else:
        chat = new_chat(prompt[:50] or "New chat", user_id=user_id)
        chat_id = chat["id"]

    # Ensure context_memory exists (for backward compatibility)
    if "context_memory" not in chat.get("meta", {}):
        chat.setdefault("meta", {})["context_memory"] = initialize_context()
        save_chat(chat)

    # Get chat mode (agentic or chat)
    chat_db = get_chat_db()
    chat_mode = chat_db.get_chat_mode(chat_id) if chat_id else "agentic"
    # Allow override from request (for new chats or explicit mode setting)
    request_mode = data.get("chatMode")
    if request_mode in ("agentic", "chat"):
        chat_mode = request_mode

    # Budget check using CostTrackingService
    cost_service = CostTrackingService()
    budget_ok, spent, budget = cost_service.check_budget(chat)
    if not budget_ok:
        return jsonify({"error": "budget_exceeded"}), 402

    # ==================== CONTEXT PREPARATION ====================
    # Build messages from history + user prompt (may include image for vision models)
    if image_base64:
        # Determine if this model supports vision (multimodal)
        provider = get_provider_type(model)
        vision_models = [
            "gpt-4o", "gpt-4-turbo", "gpt-4-vision", "gpt-5", "gpt-5-mini", "gpt-5-nano",
            "claude-3-5-sonnet", "claude-3-5-haiku", "claude-sonnet-4", "claude-opus-4.5",
            "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash",
            "llava", "bakllava", "moondream"  # Ollama vision models
        ]
        is_vision_model = any(vm in model.lower() for vm in [v.lower() for v in vision_models])
        is_ollama = provider in ("ollama_tools", "ollama_mcp", "ollama")

        # Build enhanced prompt with image file info
        image_info = ""
        if saved_image_path:
            image_info = f"\n\n[User attached image saved as: Attachments/{saved_image_path}. To embed this image in a note, use: ![[{saved_image_path}]]]"

        enhanced_prompt = prompt + image_info

        if is_vision_model and not is_ollama:
            # Vision models (non-Ollama): use multimodal format with image data
            user_content = {
                "_multimodal": True,
                "text": enhanced_prompt,
                "image_base64": image_base64,
                "image_type": image_type,
                "image_name": image_name
            }
            user_message = {"role": "user", "content": user_content}
        else:
            # Non-vision models or Ollama: just include the image path info in text
            # They can still use tools to embed the saved image in notes
            user_message = {"role": "user", "content": enhanced_prompt}
    else:
        user_message = {"role": "user", "content": prompt}

    messages = chat["messages"] + [user_message]

    # Ensure a system message exists/updated (skip if empty for Ollama)
    if system_prompt:
        if any(m.get("role") == "system" for m in messages):
            for m in messages:
                if m.get("role") == "system":
                    m["content"] = system_prompt
                    break
        else:
            messages.insert(0, {"role": "system", "content": system_prompt})

    # Inject conversation context (if any)
    conv_context = chat.get("meta", {}).get("context_memory")
    if should_include_context(conv_context):
        context_text_formatted = format_context_for_prompt(conv_context)
        messages.insert(
            1,
            {
                "role": "system",
                "content": context_text_formatted,
            },
        )

    # Handle RAG context if enabled
    if use_rag:
        # Inject RAG context using ConversationService
        qvec = embed_texts([prompt])[0]
        hits = rag_search(qvec, top_k=top_k, vault_name=settings.vault_name)
        blocks = [f"[{h['source']}#{h['ord']}] {h['text']}" for h in hits]
        context_text = "\n\n".join(blocks)

        # Format citations for response
        citations = [
            {
                "source": hit["source"],
                "chunk_id": hit["chunk_id"],
                "score": round(hit["score"], 4),
                "snippet": (
                    hit["text"][:200] + "..." if len(hit["text"]) > 200 else hit["text"]
                ),
                "obsidian_link": hit.get("obsidian_link", ""),
            }
            for hit in hits
        ]

        # Find insertion index after conversation context
        insert_index = 2 if should_include_context(conv_context) else 1
        messages.insert(
            insert_index,
            {
                "role": "system",
                "content": f"Context from my files; cite like [source#chunk]:\n\n{context_text}",
            },
        )
    else:
        citations = []

    # Trim history for token budget using ConversationService
    conv_service = ConversationService()
    trimmed = conv_service.trim_history(messages, model=model)

    # ==================== VAULT CONTEXT INJECTION (INLINE) ====================
    # This is kept inline because it's not yet in the service layer
    # Skip for Ollama models - they perform better with just tools, no extra context
    # Skip in chat mode - no vault guidance, just conversation
    vault_context = ""
    provider_type = get_provider_type(model)
    skip_vault_injection = provider_type in ("ollama_tools", "ollama_mcp", "ollama") or chat_mode == "chat"

    if skip_vault_injection:
        if chat_mode == "chat":
            print(f"[VAULT] Skipping vault context injection for chat mode")
        else:
            print(f"[VAULT] Skipping vault context injection for {provider_type} model")

    try:
        from obsidian import search_vault

        vault_triggers = [
            "vault", "notes", "wrote", "saved", "remember", "told you",
            "mentioned", "talked about", "job", "project", "daily note",
        ]

        if not skip_vault_injection and any(trigger in prompt.lower() for trigger in vault_triggers):
            stop_words = {
                "what", "when", "where", "about", "have", "that", "this",
                "with", "from", "they", "were", "been", "your", "show", "tell", "find",
            }
            vault_keywords = [
                w.strip("?.,!")
                for w in prompt.lower().split()
                if len(w) > 3 and w.strip("?.,!") not in stop_words
            ][:3]

            all_matches = []
            for keyword in vault_keywords:
                search_result = search_vault(keyword)
                if search_result.get("success"):
                    results = search_result.get("results")
                    if not results:
                        data_obj = search_result.get("data") or {}
                        results = data_obj.get("results")
                    if results:
                        all_matches.extend(results[:2])

            if all_matches:
                vault_context = "\n\nRELEVANT VAULT CONTEXT:\n"
                seen_files = set()
                for match in all_matches[:5]:
                    file_path = match["file"]
                    if file_path not in seen_files:
                        seen_files.add(file_path)
                        vault_context += f"\n**{file_path}:**\n"
                        for m in match.get("matches", [])[:2]:
                            vault_context += f"  {m['text'][:150]}\n"
                trimmed.insert(1, {"role": "system", "content": vault_context})
    except Exception as e:
        print(f"Vault search error: {e}")

    # ==================== LLM COMPLETION ====================
    llm_service = LLMService()
    try:
        result = llm_service.complete_chat(
            model=model,
            messages=trimmed,
            temperature=temperature,
            write_intent=write_intent,
            read_intent=read_intent,
            chat_id=chat_id,
            chat_mode=chat_mode
        )
        text = result["text"]
        in_tok = result["input_tokens"]
        out_tok = result["output_tokens"]
    except RuntimeError as e:
        # LLMService raises RuntimeError with formatted error messages
        error_msg = str(e)
        return jsonify({"error": error_msg}), 500
    except Exception as e:
        logger.error("llm_completion_error", model=model, error=str(e), exc_info=True)
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

    # ==================== MESSAGE PERSISTENCE ====================
    append_message(chat_id, "user", prompt, model=model)
    append_message(chat_id, "assistant", text, model=model)

    # ==================== COST TRACKING & LOGGING ====================
    cost_total = cost_service.log_usage(
        chat_id=chat_id,
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        prompt=prompt
    )

    # ==================== RESPONSE FORMATTING ====================
    response_data = {
        "chatId": chat_id,
        "text": text,
        "usage": {
            "in_tokens": in_tok,
            "out_tokens": out_tok,
            "cost_total": round(cost_total, 6),
        },
        "resolved": {
            "model": model,
            "temperature": temperature,
            "rag": use_rag,
            "topK": top_k,
            "presetId": preset_id_str or None,
            "chatMode": chat_mode,
        },
    }

    if debug_tool_calls:
        response_data["debug"] = {
            "tool_calls": result.get("tool_calls", []),
        }

    if use_rag and citations:
        response_data["citations"] = citations

    return jsonify(response_data)




@chat_bp.post("/ask-stream")
def ask_stream():
    """Streaming version of /ask endpoint for real-time responses"""
    data = request.get_json(force=True)
    prompt = (data.get("prompt") or "").strip()

    model = data.get("model") or DEFAULT_MODEL
    chat_id = data.get("chatId")

    # Extract image data if provided (for vision models)
    image_base64 = data.get("image")  # base64 encoded image
    image_type = data.get("imageType", "image/png")  # MIME type
    image_name = data.get("imageName", "attached_image")  # filename for reference

    # Allow image-only messages (no text required if image attached)
    if not prompt and not image_base64:
        return jsonify({"error": "empty_prompt"}), 400
    if not prompt and image_base64:
        prompt = "[Image]"  # Default prompt for image-only messages

    # Store image in Flask g context for tool execution (save_image_to_vault)
    if image_base64:
        g.attached_image_base64 = image_base64
        g.attached_image_type = image_type
        g.attached_image_name = image_name

    # Get chat mode - in chat mode, allow streaming for all supported models
    chat_db = get_chat_db()
    chat_mode = chat_db.get_chat_mode(chat_id) if chat_id else "agentic"
    request_mode = data.get("chatMode")
    if request_mode in ("agentic", "chat"):
        chat_mode = request_mode

    # Determine if streaming is allowed based on mode
    provider_type = get_provider_type(model)

    if chat_mode == "chat":
        # In chat mode, allow streaming for local models and cloud models
        can_stream = is_local_model(model) or provider_type in ("openai", "anthropic", "gemini")
    else:
        # In agentic mode, only whitelisted local models can stream
        can_stream = is_local_model(model) and streaming_supported(model)

    if not can_stream:
        return jsonify({"error": "Streaming not supported for this model in current mode"}), 400

    def generate_stream():
        try:
            # Get same parameters as regular /ask endpoint
            preset_id_str = data.get("presetId")
            preset = None
            if preset_id_str:
                try:
                    from rag_db import get_preset_from_db as get_preset
                    preset_id = int(preset_id_str)
                    preset = get_preset(preset_id)
                except:
                    pass

            # System prompt and temperature handling (same as /ask)
            system_prompt = (data.get("system") or "").strip()
            if not system_prompt and preset:
                system_prompt = preset.get("system")
            if not system_prompt:
                system_prompt = "You are a helpful assistant."

            if model in ["gpt-5", "gpt-5-mini", "gpt-5-nano"]:
                temperature = 1.0
            else:
                temperature = data.get("temperature")
                if temperature is None and preset:
                    temperature = preset.get("temperature")
                if temperature is None:
                    temperature = 0.3
                try:
                    temperature = float(temperature)
                    temperature = max(0.0, min(1.0, temperature))
                except (ValueError, TypeError):
                    temperature = 0.3

            # RAG handling (same as /ask)
            use_rag = bool(data.get("rag"))
            top_k = int(data.get("topK") or 5)
            context_text = ""

            if use_rag and prompt:
                from rag import embed_texts
                from rag_db import search

                qvec = embed_texts([prompt])[0]
                hits = search(qvec, top_k=top_k, vault_name=settings.vault_name)
                blocks = [f"[{h['source']}#{h['ord']}] {h['text']}" for h in hits]
                context_text = "\n\n".join(blocks)

            # Build messages (same logic as /ask)
            messages = []
            if chat_id:
                chat = load_chat(chat_id)
                if chat:
                    messages = chat.get("messages", [])

            # Build user message content - may include image for vision models
            if image_base64:
                # Build multimodal content array
                # This will be reformatted per-provider when streaming
                user_content = {
                    "_multimodal": True,
                    "text": prompt,
                    "image_base64": image_base64,
                    "image_type": image_type,
                    "image_name": image_name
                }
                messages.append({"role": "user", "content": user_content})
            else:
                messages.append({"role": "user", "content": prompt})

            # Handle system prompt
            if any(m.get("role") == "system" for m in messages):
                for m in messages:
                    if m.get("role") == "system":
                        m["content"] = system_prompt
                        break
            else:
                messages.insert(0, {"role": "system", "content": system_prompt})

            # Add RAG context if available
            if context_text:
                messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": f"Context from my files; cite like [source#chunk]:\n\n{context_text}",
                    },
                )

            # Trim history for token budget
            trimmed = trim_history(messages, model=model)

            # Start streaming response
            yield "data: " + json.dumps({"type": "start", "model": model, "chatMode": chat_mode}) + "\n\n"

            full_response = ""
            thinking_content = ""
            response_content = ""
            in_thinking_phase = False
            thinking_complete = False

            # Route to appropriate streaming provider
            provider_type = get_provider_type(model)

            if provider_type == "anthropic":
                # Stream from Anthropic Claude
                from anthropic import Anthropic
                client = Anthropic(api_key=settings.anthropic_api_key)

                # Filter out system messages for Claude (handle separately)
                system_text = ""
                conv_messages = []
                for m in trimmed:
                    if m.get("role") == "system":
                        if system_text:
                            system_text += "\n\n"
                        system_text += m.get("content", "")
                    else:
                        content = m.get("content", "")
                        # Handle multimodal content for vision
                        if isinstance(content, dict) and content.get("_multimodal"):
                            # Build Anthropic vision content array
                            anthropic_content = [
                                {"type": "text", "text": content.get("text", "")},
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": content.get("image_type", "image/png"),
                                        "data": content.get("image_base64", "")
                                    }
                                }
                            ]
                            conv_messages.append({"role": m["role"], "content": anthropic_content})
                        else:
                            conv_messages.append({"role": m["role"], "content": content})

                # Ensure first message is from user
                if conv_messages and conv_messages[0].get("role") != "user":
                    conv_messages.insert(0, {"role": "user", "content": "..."})

                with client.messages.stream(
                    model=model,
                    max_tokens=4096,
                    system=system_text or "You are a helpful assistant.",
                    messages=conv_messages,
                    temperature=temperature,
                ) as stream:
                    for text in stream.text_stream:
                        response_content += text
                        full_response = response_content
                        yield "data: " + json.dumps({
                            "type": "chunk",
                            "content": text,
                            "full_text": response_content,
                        }) + "\n\n"

            elif provider_type == "openai":
                # Stream from OpenAI
                client = OpenAI(api_key=settings.openai_api_key)

                # Convert multimodal content to OpenAI format
                openai_messages = []
                for m in trimmed:
                    content = m.get("content", "")
                    if isinstance(content, dict) and content.get("_multimodal"):
                        # Build OpenAI vision content array
                        openai_content = [
                            {"type": "text", "text": content.get("text", "")},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{content.get('image_type', 'image/png')};base64,{content.get('image_base64', '')}",
                                    "detail": "auto"
                                }
                            }
                        ]
                        openai_messages.append({"role": m["role"], "content": openai_content})
                    else:
                        openai_messages.append({"role": m["role"], "content": content})

                stream = client.chat.completions.create(
                    model=model,
                    messages=openai_messages,
                    temperature=temperature,
                    stream=True,
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        text = chunk.choices[0].delta.content
                        response_content += text
                        full_response = response_content
                        yield "data: " + json.dumps({
                            "type": "chunk",
                            "content": text,
                            "full_text": response_content,
                        }) + "\n\n"

            elif provider_type == "gemini":
                # Stream from Google Gemini
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                gemini_model = genai.GenerativeModel(model)

                # Convert messages to Gemini format
                gemini_history = []
                for m in trimmed[:-1]:  # All except last message
                    if m.get("role") == "system":
                        continue  # Skip system messages for Gemini
                    role = "model" if m.get("role") == "assistant" else "user"
                    gemini_history.append({"role": role, "parts": [m.get("content", "")]})

                chat = gemini_model.start_chat(history=gemini_history)
                response = chat.send_message(trimmed[-1].get("content", ""), stream=True)

                for chunk in response:
                    if chunk.text:
                        response_content += chunk.text
                        full_response = response_content
                        yield "data: " + json.dumps({
                            "type": "chunk",
                            "content": chunk.text,
                            "full_text": response_content,
                        }) + "\n\n"

            else:
                # Stream from Ollama (local models)
                stream = ollama_client.chat(
                    model=model,
                    messages=trimmed,
                    options={"temperature": temperature},
                    stream=True,
                )

                for chunk in stream:
                    if chunk and "message" in chunk:
                        msg = chunk["message"]

                        # Check for thinking content (comes first in qwen models)
                        thinking = msg.get("thinking", "")
                        content = msg.get("content", "")

                        if thinking:
                            # We're in the thinking phase
                            if not in_thinking_phase:
                                in_thinking_phase = True
                                yield "data: " + json.dumps(
                                    {"type": "thinking_start"}
                                ) + "\n\n"

                            thinking_content += thinking
                            yield "data: " + json.dumps(
                                {"type": "thinking_chunk", "content": thinking}
                            ) + "\n\n"

                        elif content and in_thinking_phase and not thinking_complete:
                            # Transition from thinking to response
                            thinking_complete = True
                            yield "data: " + json.dumps(
                                {"type": "thinking_complete", "thinking": thinking_content}
                            ) + "\n\n"

                            # Now send the content
                            response_content += content
                            full_response = response_content
                            yield "data: " + json.dumps(
                                {
                                    "type": "chunk",
                                    "content": content,
                                    "full_text": response_content,
                                }
                            ) + "\n\n"

                        elif content:
                            # Regular content (either no thinking phase, or continuing response)
                            response_content += content
                            full_response = response_content
                            yield "data: " + json.dumps(
                                {
                                    "type": "chunk",
                                    "content": content,
                                    "full_text": response_content,
                                }
                            ) + "\n\n"

            # Persist the conversation (only save the response, not the thinking)
            append_message(chat_id, "user", prompt, model=model)
            append_message(chat_id, "assistant", full_response, model=model)

            # Send completion signal
            completion_data = {
                "type": "complete",
                "chatId": chat_id,
                "full_text": full_response,
                "usage": {
                    "in_tokens": sum(len(m.get("content", "")) // 4 for m in trimmed),
                    "out_tokens": len(full_response) // 4,
                    "cost_total": 0.0,  # Local models are free
                },
            }

            # Include thinking content if it exists
            if thinking_content:
                completion_data["thinking"] = thinking_content

            yield "data: " + json.dumps(completion_data) + "\n\n"

        except Exception as e:
            yield "data: " + json.dumps(
                {"type": "error", "error": f"Streaming error: {str(e)}"}
            ) + "\n\n"

    return Response(
        generate_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ---------- Claude Code Endpoint ----------


@chat_bp.post("/ask-claude-code")
def ask_claude_code():
    """
    Execute a prompt using Claude Code CLI via proxy service.

    This uses the local Claude Code installation which is authenticated
    via OAuth with a Max subscription (not API billing).

    The proxy runs in the LXC container (not Docker) to avoid socket issues.
    Features:
    - Model selection (opus/sonnet/haiku based on model parameter)
    - Session persistence (tied to chat ID)
    - CLAUDE.md context injection
    """
    import time
    import urllib.request
    import urllib.error
    from prices import get_claude_code_model

    data = request.get_json(force=True)
    prompt = (data.get("prompt") or "").strip()
    chat_id = data.get("chatId")
    model_id = data.get("model", "claude-code-sonnet")  # Full model ID from frontend
    timeout = data.get("timeout", 300)  # 5 minute default timeout

    if not prompt:
        return jsonify({"error": "empty_prompt"}), 400

    # Get or create chat
    if not chat_id:
        chat_id = str(uuid.uuid4().hex[:12])

    # Extract model tier (opus/sonnet/haiku) from model ID
    model_tier = get_claude_code_model(model_id)

    # Allowed tools for vault operations (can be customized)
    allowed_tools = data.get("allowedTools", "Read,Write,Edit,Bash,Glob,Grep")

    # Working directory - default to vault (use host path, not container path)
    work_dir = data.get("workDir", "/root/obsidian-vault")

    logger.info("claude_code_request",
                chat_id=chat_id,
                model=model_tier,
                prompt_length=len(prompt),
                timeout=timeout,
                work_dir=work_dir)

    start_time = time.time()

    try:
        # Call the Claude proxy service running in the LXC container
        # The proxy listens on port 9876 and is accessible via host.docker.internal
        proxy_url = "http://host.docker.internal:9876/claude"

        proxy_data = json.dumps({
            "prompt": prompt,
            "model": model_tier,  # opus, sonnet, or haiku
            "chatId": chat_id,    # For session persistence
            "allowedTools": allowed_tools,
            "workDir": work_dir,
            "timeout": timeout
        }).encode('utf-8')

        req = urllib.request.Request(
            proxy_url,
            data=proxy_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            proxy_response = json.loads(resp.read().decode('utf-8'))

        elapsed = time.time() - start_time
        output = proxy_response.get("text", "")
        stderr = proxy_response.get("stderr")
        exit_code = proxy_response.get("exit_code", 0)

        logger.info("claude_code_response",
                    chat_id=chat_id,
                    elapsed_seconds=round(elapsed, 2),
                    output_length=len(output),
                    exit_code=exit_code)

        # Save messages to chat history
        append_message(chat_id, "user", prompt, model="claude-code")
        append_message(chat_id, "assistant", output, model="claude-code")

        response_data = {
            "chatId": chat_id,
            "text": output,
            "model": "claude-code",
            "elapsed_seconds": round(elapsed, 2),
            "usage": {
                "note": "Uses Max subscription (not API billing)"
            }
        }

        if stderr:
            response_data["stderr"] = stderr

        if exit_code != 0:
            response_data["warning"] = f"Process exited with code {exit_code}"

        return jsonify(response_data)

    except urllib.error.URLError as e:
        elapsed = time.time() - start_time
        if "timed out" in str(e).lower():
            logger.warning("claude_code_timeout", chat_id=chat_id, timeout=timeout)
            return jsonify({
                "error": f"Claude Code timed out after {timeout} seconds",
                "elapsed_seconds": round(elapsed, 2)
            }), 408
        else:
            logger.error("claude_code_proxy_error", error=str(e))
            return jsonify({
                "error": f"Claude Code proxy error: {str(e)}. Ensure claude-proxy service is running."
            }), 503

    except Exception as e:
        logger.error("claude_code_error", error=str(e), exc_info=True)
        return jsonify({
            "error": f"Claude Code error: {str(e)}"
        }), 500


# ---------- Codex CLI Endpoint ----------


@chat_bp.post("/ask-codex")
def ask_codex():
    """
    Execute a prompt using OpenAI Codex CLI via proxy service.

    This uses the local Codex installation which is authenticated
    via OAuth with a ChatGPT Plus/Pro subscription (not API billing).

    The proxy runs in the LXC container (not Docker) to avoid socket issues.
    Features:
    - Model selection (gpt-5-codex, gpt-5-mini based on model parameter)
    - Uses ChatGPT Plus/Pro subscription quota
    """
    import time
    import urllib.request
    import urllib.error
    from prices import get_codex_model

    data = request.get_json(force=True)
    prompt = (data.get("prompt") or "").strip()
    chat_id = data.get("chatId")
    model_id = data.get("model", "codex-gpt52")  # Full model ID from frontend
    timeout = data.get("timeout", 300)  # 5 minute default timeout
    reasoning = data.get("reasoning", "medium")  # low, medium, high

    if not prompt:
        return jsonify({"error": "empty_prompt"}), 400

    # Validate reasoning level
    if reasoning not in ("low", "medium", "high"):
        reasoning = "medium"

    # Get or create chat
    if not chat_id:
        chat_id = str(uuid.uuid4().hex[:12])

    # Extract Codex model name from model ID
    codex_model = get_codex_model(model_id)

    # Working directory - default to vault
    work_dir = data.get("workDir", "/root/obsidian-vault")

    logger.info("codex_request",
                chat_id=chat_id,
                model=codex_model,
                reasoning=reasoning,
                prompt_length=len(prompt),
                timeout=timeout,
                work_dir=work_dir)

    start_time = time.time()

    try:
        # Call the Codex proxy service running in the LXC container
        # The proxy listens on port 9877 and is accessible via host.docker.internal
        proxy_url = "http://host.docker.internal:9877/codex"

        proxy_data = json.dumps({
            "prompt": prompt,
            "model": codex_model,
            "chatId": chat_id,
            "workDir": work_dir,
            "timeout": timeout,
            "reasoning": reasoning
        }).encode('utf-8')

        req = urllib.request.Request(
            proxy_url,
            data=proxy_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            proxy_response = json.loads(resp.read().decode('utf-8'))

        elapsed = time.time() - start_time
        output = proxy_response.get("text", "")
        stderr = proxy_response.get("stderr")
        exit_code = proxy_response.get("exit_code", 0)

        logger.info("codex_response",
                    chat_id=chat_id,
                    elapsed_seconds=round(elapsed, 2),
                    output_length=len(output),
                    exit_code=exit_code)

        # Save messages to chat history
        append_message(chat_id, "user", prompt, model="codex")
        append_message(chat_id, "assistant", output, model="codex")

        response_data = {
            "chatId": chat_id,
            "text": output,
            "model": "codex",
            "reasoning": reasoning,
            "elapsed_seconds": round(elapsed, 2),
            "usage": {
                "note": "Uses ChatGPT Plus/Pro subscription (not API billing)"
            }
        }

        if stderr:
            response_data["stderr"] = stderr

        if exit_code != 0:
            response_data["warning"] = f"Process exited with code {exit_code}"

        return jsonify(response_data)

    except urllib.error.URLError as e:
        elapsed = time.time() - start_time
        if "timed out" in str(e).lower():
            logger.warning("codex_timeout", chat_id=chat_id, timeout=timeout, reasoning=reasoning)
            return jsonify({
                "error": f"Codex timed out after {timeout} seconds",
                "elapsed_seconds": round(elapsed, 2)
            }), 408
        else:
            logger.error("codex_proxy_error", error=str(e))
            return jsonify({
                "error": f"Codex proxy error: {str(e)}. Ensure codex-proxy service is running."
            }), 503

    except Exception as e:
        logger.error("codex_error", error=str(e), exc_info=True)
        return jsonify({
            "error": f"Codex error: {str(e)}"
        }), 500


# ---------- Gemini CLI Endpoint ----------


@chat_bp.post("/ask-gemini-cli")
def ask_gemini_cli():
    """
    Execute a prompt using Google Gemini CLI via proxy service.

    This uses the local Gemini CLI installation which is authenticated
    via Google Login (free tier: 60 req/min, 1000/day).

    The proxy runs in the LXC container (not Docker) to avoid socket issues.
    Features:
    - Model selection (gemini-2.5-pro, gemini-2.5-flash based on model parameter)
    - Uses Google Login free tier quota
    """
    import time
    import urllib.request
    import urllib.error
    from prices import get_gemini_cli_model

    data = request.get_json(force=True)
    prompt = (data.get("prompt") or "").strip()
    chat_id = data.get("chatId")
    model_id = data.get("model", "gemini-cli-flash")  # Full model ID from frontend
    timeout = data.get("timeout", 300)  # 5 minute default timeout

    if not prompt:
        return jsonify({"error": "empty_prompt"}), 400

    # Get or create chat
    if not chat_id:
        chat_id = str(uuid.uuid4().hex[:12])

    # Extract Gemini model name from model ID
    gemini_model = get_gemini_cli_model(model_id)

    # Working directory - default to vault
    work_dir = data.get("workDir", "/root/obsidian-vault")

    logger.info("gemini_cli_request",
                chat_id=chat_id,
                model=gemini_model,
                prompt_length=len(prompt),
                timeout=timeout,
                work_dir=work_dir)

    start_time = time.time()

    try:
        # Call the Gemini proxy service running in the LXC container
        # The proxy listens on port 9878 and is accessible via host.docker.internal
        proxy_url = "http://host.docker.internal:9878/gemini"

        proxy_data = json.dumps({
            "prompt": prompt,
            "model": gemini_model,
            "chatId": chat_id,
            "workDir": work_dir,
            "timeout": timeout
        }).encode('utf-8')

        req = urllib.request.Request(
            proxy_url,
            data=proxy_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            proxy_response = json.loads(resp.read().decode('utf-8'))

        elapsed = time.time() - start_time
        output = proxy_response.get("text", "")
        stderr = proxy_response.get("stderr")
        exit_code = proxy_response.get("exit_code", 0)

        logger.info("gemini_cli_response",
                    chat_id=chat_id,
                    elapsed_seconds=round(elapsed, 2),
                    output_length=len(output),
                    exit_code=exit_code)

        # Save messages to chat history
        append_message(chat_id, "user", prompt, model="gemini-cli")
        append_message(chat_id, "assistant", output, model="gemini-cli")

        response_data = {
            "chatId": chat_id,
            "text": output,
            "model": "gemini-cli",
            "elapsed_seconds": round(elapsed, 2),
            "usage": {
                "note": "Uses Google Login free tier (60 req/min, 1000/day)"
            }
        }

        if stderr:
            response_data["stderr"] = stderr

        if exit_code != 0:
            response_data["warning"] = f"Process exited with code {exit_code}"

        return jsonify(response_data)

    except urllib.error.URLError as e:
        elapsed = time.time() - start_time
        if "timed out" in str(e).lower():
            logger.warning("gemini_cli_timeout", chat_id=chat_id, timeout=timeout)
            return jsonify({
                "error": f"Gemini CLI timed out after {timeout} seconds",
                "elapsed_seconds": round(elapsed, 2)
            }), 408
        else:
            logger.error("gemini_cli_proxy_error", error=str(e))
            return jsonify({
                "error": f"Gemini CLI proxy error: {str(e)}. Ensure gemini-proxy service is running."
            }), 503

    except Exception as e:
        logger.error("gemini_cli_error", error=str(e), exc_info=True)
        return jsonify({
            "error": f"Gemini CLI error: {str(e)}"
        }), 500


# ---------- Gemini Endpoint ----------


@chat_bp.post("/ask-gemini")
def ask_gemini():
    data = request.get_json(force=True)
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "empty_prompt"}), 400

    use_mcp = bool(data.get("useMcp") or False)

    try:
        if use_mcp:
            # Start the MCP filesystem server and bridge it with gemini over stdio
            from mcp_stdio import (
                start_filesystem_process,
                bridge_processes,
                stop_process,
            )

            # Allowed dirs can be provided as a list in the request or via env
            allowed = data.get("allowedDirs")
            if isinstance(allowed, str):
                allowed = [d for d in allowed.split(":") if d]

            fs_proc = start_filesystem_process(allowed_dirs=allowed)

            # Start gemini process; we will attach its stdin/stdout to the fs_proc
            gemini_cmd = ["gemini", prompt]
            gem_proc = subprocess.Popen(
                gemini_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
            )

            try:
                # Bridge until one side exits (or timeout inside bridge)
                bridge_processes(
                    gem_proc, fs_proc, timeout=int(data.get("timeout") or 120)
                )

                # Read any remaining stdout from gemini
                out = b""
                try:
                    out = gem_proc.stdout.read() or b""
                except Exception:
                    pass

                try:
                    stderr = (
                        gem_proc.stderr.read().decode(errors="ignore")
                        if gem_proc.stderr
                        else ""
                    )
                except Exception:
                    stderr = ""

                response_text = (
                    out.decode(errors="ignore").strip()
                    if isinstance(out, (bytes, bytearray))
                    else str(out).strip()
                )

                if gem_proc.returncode not in (0, None) and not response_text:
                    # If gemini errored, return stderr
                    return jsonify({"error": "gemini failed", "stderr": stderr}), 500

                return jsonify({"text": response_text})

            finally:
                stop_process(gem_proc)
                stop_process(fs_proc)

        else:
            # This assumes the 'gemini' command is in the system's PATH.
            # We may need to provide a full path or configure it differently.
            result = subprocess.run(
                ["gemini", prompt],
                capture_output=True,
                text=True,
                check=True,  # This will raise an exception for non-zero exit codes
                timeout=120,  # Add a timeout for safety
            )
            response_text = result.stdout.strip()

            return jsonify({"text": response_text})

    except FileNotFoundError as e:
        return jsonify({"error": "Required command not found", "detail": str(e)}), 500
    except subprocess.CalledProcessError as e:
        print(f"Gemini CLI Error: {e.stderr}")
        return (
            jsonify(
                {"error": "The gemini command failed.", "stderr": e.stderr.strip()}
            ),
            500,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "The gemini command timed out."}, 500)
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}, 500)


@chat_bp.post("/save-to-inbox")
def save_to_inbox():
    """
    Save a voice note or quick capture to the inbox folder as individual file.
    Creates timestamped file for later LLM post-processing.
    Supports optional image attachment (multipart/form-data).
    """
    from datetime import datetime
    import secrets
    from services.obsidian_service import ObsidianService
    from config import get_settings

    obs = ObsidianService()
    settings = get_settings()
    image_link = ""

    # Check content type to determine how to parse request
    content_type = request.content_type or ""

    if content_type.startswith('multipart/form-data'):
        # Multipart request - may have image
        text = (request.form.get("text") or "").strip()
        source = (request.form.get("source") or "").strip()
        image_file = request.files.get("image")

        if image_file and image_file.filename:
            # Validate image type by checking magic bytes
            image_bytes = image_file.read()
            if not _is_valid_image(image_bytes):
                return jsonify({"error": "Invalid image format"}), 400

            # Save image to vault
            img_result = obs.save_image(
                image_bytes=image_bytes,
                filename=image_file.filename
            )

            if img_result.get("success"):
                image_link = "\n\n" + img_result.get("markdown", "")
            else:
                return jsonify({
                    "success": False,
                    "error": img_result.get("error", "Failed to save image")
                }), 500
    else:
        # JSON request - text only
        data = request.get_json(force=True)
        text = (data.get("text") or "").strip()
        source = (data.get("source") or "").strip()

    if not text and not image_link:
        return jsonify({"error": "empty_text"}), 400

    # Generate unique filename: YYYY-MM-DD_HHMMSS_<4-char-shortid>.md
    try:
        user_tz = pytz.timezone(settings.timezone)
    except pytz.UnknownTimeZoneError:
        user_tz = pytz.timezone("America/New_York")
    now = datetime.now(user_tz)
    timestamp_display = now.strftime("%Y-%m-%d %H:%M")
    timestamp_file = now.strftime("%Y-%m-%d_%H%M%S")
    short_id = secrets.token_hex(2)  # 4 hex chars
    filename = f"{timestamp_file}_{short_id}.md"

    # Create note content with frontmatter
    source_line = f"\nsource: {source}" if source else ""
    content = f"""---
captured: {now.strftime("%Y-%m-%d %H:%M:%S")}
type: inbox-capture{source_line}
---

{text}{image_link}
"""

    try:
        result = obs.create_note(
            content=content,
            destination=settings.inbox_folder,
            filename=filename,
            mode="create"
        )

        if result.get("success"):
            return jsonify({
                "success": True,
                "message": "Saved to inbox",
                "path": result.get("path"),
                "timestamp": timestamp_display,
                "has_image": bool(image_link)
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "Failed to save")
            }), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _is_valid_image(data: bytes) -> bool:
    """Check if data is a valid image by examining magic bytes."""
    if len(data) < 8:
        return False

    # Check magic bytes for common image formats
    magic_bytes = {
        b'\x89PNG\r\n\x1a\n': 'png',
        b'\xff\xd8\xff': 'jpeg',
        b'GIF87a': 'gif',
        b'GIF89a': 'gif',
        b'RIFF': 'webp',  # WebP starts with RIFF
        b'<svg': 'svg',
        b'<?xml': 'svg',  # SVG can start with XML declaration
        b'BM': 'bmp',
    }

    for magic, fmt in magic_bytes.items():
        if data.startswith(magic):
            return True

    # Special check for WebP (RIFF....WEBP)
    if data[:4] == b'RIFF' and len(data) > 11 and data[8:12] == b'WEBP':
        return True

    return False


@chat_bp.post("/upload-image")
def upload_image():
    """
    Upload an image to the vault's Attachments folder.
    Optionally embed it in a specified note.
    """
    from services.obsidian_service import ObsidianService

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No file provided"}), 400

    # Read image data
    image_bytes = f.read()

    # Validate image
    if not _is_valid_image(image_bytes):
        return jsonify({"ok": False, "error": "Invalid image format. Supported: PNG, JPEG, GIF, WebP, SVG, BMP"}), 400

    # Optional parameters
    custom_filename = request.form.get("filename", "").strip()
    embed_in_note = request.form.get("embed_in_note", "").strip()
    section = request.form.get("section", "").strip()

    try:
        obs = ObsidianService()
        result = obs.save_image(
            image_bytes=image_bytes,
            filename=custom_filename or f.filename,
            embed_in_note=embed_in_note or None,
            section=section or None
        )

        if result.get("success"):
            return jsonify({
                "ok": True,
                "path": result.get("path"),
                "filename": result.get("filename"),
                "markdown": result.get("markdown"),
                "size_bytes": result.get("size_bytes"),
                "embedded_in": result.get("embedded_in")
            })
        else:
            return jsonify({
                "ok": False,
                "error": result.get("error", "Failed to save image")
            }), 500

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
