from flask import Flask, render_template, request, Response, jsonify, redirect, url_for, g
import os, csv, re, datetime, tiktoken, subprocess, json, logging, uuid

# ========== CRITICAL: Load environment variables BEFORE any config imports ==========
from dotenv import load_dotenv
load_dotenv()
# ========================================================================================

from openai import OpenAI
import pytz

try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print(
        "WARNING: anthropic package not installed. Claude models will not be available."
    )
    print("Install with: pip install anthropic>=0.39.0")
import ollama
import structlog
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from apscheduler.schedulers.background import BackgroundScheduler
import threading
from datetime import datetime as dt

# Configuration
from config import get_settings

# Initialize Ollama client with host from environment
ollama_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))

# Local modules
from prices import (
    allowed_models,
    get_model_meta,
    prices_for,
    DEFAULT_MODEL,
    is_local_model,
    streaming_supported,
    is_claude_model,
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

from rag_db import (
    init_db,
    upsert_source,
    add_chunks,
    list_sources,
    delete_source,
    search,
    list_presets_from_db as list_presets,
    get_preset_from_db as get_preset,
    add_preset_to_db,
    update_preset_in_db,
    delete_preset_from_db,
    get_db,
)
from rag import chunk_text, embed_texts
from chat_db import get_chat_db

# Obsidian integration
from obsidian import (
    append_to_daily,
    create_job_note,
    create_note,
    read_daily_note,
    read_note,
    list_vault_structure,
)
from obsidian_functions import OBSIDIAN_FUNCTIONS, execute_obsidian_function

# Tool calling observability and validation
import time
from observability import log_tool_call, get_tool_call_stats
from tool_schema import validate_tool_call

# Initialize settings (load_dotenv() was already called at top of file)
settings = get_settings()
settings.ensure_directories()
init_db()

app = Flask(__name__)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)
logger = structlog.get_logger()


# ---------- Tool-calling guard helpers ----------
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
WRITE_VERIFICATION_FUNCTIONS = {
    "create_simple_note",
    "create_job_note",
    "create_from_template",
    "update_note",
}
WRITE_TOOL_REMINDER = (
    "Reminder: Vault operations require calling the appropriate Obsidian tool. "
    "Do not claim success until the tool call succeeds."
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
    Lightweight read-after-write verification for note-writing tools.

    Returns:
        ("passed"|"failed"|"skipped", reason_if_any)
    """
    if (
        not settings.verify_vault_writes
        or function_name not in WRITE_VERIFICATION_FUNCTIONS
        or not result
        or not result.get("success")
    ):
        return "skipped", None

    path = (
        result.get("path")
        or arguments.get("file_path")
    )
    if not path:
        return "skipped", None

    try:
        note_result = read_note(path)
    except Exception as exc:
        return "failed", f"Could not read note '{path}': {exc}"

    if not note_result.get("success"):
        return "failed", note_result.get("error") or f"Unable to read note '{path}'"

    expected_fragment = ""
    if function_name == "create_simple_note":
        expected_fragment = arguments.get("content", "")
    elif function_name == "create_job_note":
        expected_fragment = arguments.get("job_name", "") or arguments.get("client", "")
    elif function_name == "create_from_template":
        vars_arg = arguments.get("variables") or {}
        expected_fragment = vars_arg.get("title", "")
    elif function_name == "update_note":
        expected_fragment = arguments.get("new_content", "")

    normalized_expected = _normalized_fragment(expected_fragment)
    if normalized_expected and len(normalized_expected) > 0:
        normalized_note = _normalized_fragment(note_result.get("content", ""), limit=None)
        if normalized_expected not in normalized_note:
            return "failed", f"Written content not found in '{path}' after tool execution."

    return "passed", None


# Global response headers for security, compatibility, and caching
@app.after_request
def _add_default_headers(resp):
    try:
        # Security: reduce header leakage and prevent MIME sniffing
        resp.headers["Server"] = "WebAppChat"
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")

        # Performance: set caching policy (long cache for static, no-store for dynamic)
        path = request.path or ""
        if path.startswith("/static/"):
            resp.headers.setdefault(
                "Cache-Control", "public, max-age=31536000, immutable"
            )
        else:
            resp.headers.setdefault("Cache-Control", "no-store, max-age=0")

        # Compatibility: ensure UTF-8 charset on text/* content types
        if resp.mimetype and resp.mimetype.startswith("text/"):
            ct = resp.headers.get("Content-Type", "")
            base = resp.mimetype
            resp.headers["Content-Type"] = f"{base}; charset=utf-8"
    except Exception:
        # Do not block the response on header adjustments
        pass
    return resp


# Configure rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    enabled=settings.rate_limit_enabled,
    storage_uri="memory://",
)

# ========== Authentication Setup ==========
# Initialize auth database
from auth_db import init_auth_db
from auth_routes import auth_bp
from alexa_handler import alexa_bp
from routes.voice_routes import voice_bp
from utils.auth_utils import get_current_user

init_auth_db(settings.chat_db_path)

# Configure Flask sessions
from datetime import timedelta
app.config['SECRET_KEY'] = settings.flask_secret_key
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = settings.flask_env == 'production'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=settings.session_lifetime_days)
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25MB max upload size for images

# Register auth blueprint
app.register_blueprint(auth_bp)
app.register_blueprint(alexa_bp)
app.register_blueprint(voice_bp)

# Register route blueprints
from routes.chat_routes import chat_bp
from routes.rag_routes import rag_bp
from routes.analytics_routes import analytics_bp
from routes.obsidian_routes import obsidian_bp
from routes.admin_routes import admin_bp, set_ollama_client

app.register_blueprint(chat_bp)
app.register_blueprint(rag_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(obsidian_bp)
app.register_blueprint(admin_bp)

# Set ollama_client for admin routes
set_ollama_client(ollama_client)

# Authentication middleware - run before every request
PUBLIC_ENDPOINTS = {
    'auth.login', 'auth.logout', 'static', 'health',
    'static.index',  # Allow access to static files without auth
    'alexa.alexa_webhook',  # Alexa Skills endpoint
    'voice.voice_process',  # ESP32 voice assistant endpoint
    'voice.voice_transcribe',  # Voice STT endpoint
    'voice.voice_tts',  # Voice TTS endpoint
    'voice.voice_status',  # Voice health check
    'admin.route_list_models',  # Model list for dropdown (needed before auth)
}

@app.before_request
def check_authentication():
    """Check authentication status before processing request."""
    # Allow access to public endpoints without authentication
    if request.endpoint in PUBLIC_ENDPOINTS or (request.endpoint and request.endpoint.startswith('static')):
        return

    # Check if auth is enabled
    if not settings.auth_enabled:
        return

    # Skip auth check for auth routes themselves
    if request.blueprint == 'auth':
        return

    # Check if user is authenticated via session
    current_user = get_current_user()
    if current_user:
        g.current_user = current_user
        g.auth_method = 'session'
        return

    # Check for API key authentication
    from utils.auth_utils import extract_api_key_from_request, hash_api_key
    from auth_db import get_auth_db

    api_key = extract_api_key_from_request()
    if api_key:
        auth_db = get_auth_db(settings.chat_db_path)
        api_key_hash = hash_api_key(api_key)
        key_data = auth_db.get_api_key_by_hash(api_key_hash)

        if key_data and not key_data.get('revoked'):
            # Valid API key - authenticate
            auth_db.update_api_key_last_used(key_data['id'])
            g.current_user = {
                'user_id': None,
                'username': None,
                'api_key_label': key_data['label']
            }
            g.auth_method = 'api_key'
            logger.info("api_key_authenticated", label=key_data['label'])
            return
        else:
            # Invalid or revoked API key - log attempt
            ip_address = request.remote_addr
            auth_db.log_auth_attempt(
                event_type='api_key_auth',
                success=False,
                ip_address=ip_address,
                key_label='invalid'
            )
            logger.warning("invalid_api_key_attempt", ip_address=ip_address)

    # Not authenticated - determine if this is a JSON API request or browser request
    # Use best_match to properly handle Accept header with wildcards (e.g., */*)
    best_match = request.accept_mimetypes.best_match(['application/json', 'text/html'])

    if best_match == 'application/json':
        # API request - return 401 Unauthorized
        return jsonify({"error": "Unauthorized"}), 401

    # Browser request - redirect to login
    return redirect(url_for('auth.login', next=request.url))

# ========== RAG Auto-Sync Scheduler ==========
# Global scheduler instance and sync lock
scheduler = None
rag_sync_lock = threading.Lock()
last_rag_sync_time = None
last_rag_sync_duration = None
last_rag_sync_error = None
files_synced_count = 0


def _rag_sync_task():
    """
    Background task for automatic RAG synchronization.
    Syncs Obsidian vault files to RAG database periodically.
    """
    global last_rag_sync_time, last_rag_sync_duration, last_rag_sync_error, files_synced_count
    
    # Use lock to prevent concurrent syncs (manual + scheduled)
    if not rag_sync_lock.acquire(blocking=False):
        logger.warning("RAG sync already in progress, skipping scheduled sync")
        return
    
    try:
        start_time = dt.utcnow()
        start_timestamp = start_time.isoformat() + "Z"
        
        # Log sync start
        log_message = f"[{start_timestamp}] SYNC START | Interval: {settings.rag_auto_sync_interval_minutes} minutes"
        logger.info("rag_sync_start", message=log_message)
        
        # Call the existing RAG sync logic directly
        from pathlib import Path
        
        vault = settings.vault_path
        
        # Handle vault path resolution (same as in the endpoint)
        if not vault.exists():
            alternative_paths = [
                Path("/obsidian-vault"),
                Path("../obsidian-vault"),
                Path("r:/obsidian-vault"),
                Path("/mnt/obsidian-vault"),
                Path("/app/vault"),
                Path("r:/WebAppChat/vault"),
                Path("./vault"),
            ]
            
            for alt_path in alternative_paths:
                if alt_path.exists():
                    vault = alt_path
                    break
            else:
                error_msg = f"Vault not found at configured path {settings.vault_path}"
                logger.error("rag_sync_vault_error", error=error_msg)
                last_rag_sync_error = error_msg
                return
        
        synced = []
        errors = []
        skipped = 0
        
        # Find all markdown files in vault
        md_files = list(vault.rglob("*.md"))
        
        # Get excluded folders from settings (e.g., ["00-Inbox", "90-Meta"])
        # Convert to path parts for robust prefix matching (supports nested excludes)
        excluded_parts = [Path(f.strip("/\\")).parts for f in settings.rag_exclude_folders] if settings.rag_exclude_folders else []

        for md_file in md_files:
            try:
                # Skip hidden files and directories
                if any(part.startswith(".") for part in md_file.parts):
                    skipped += 1
                    continue

                # Skip files in excluded folders (compare path parts, not string prefix)
                relative_path = md_file.relative_to(vault)
                rel_parts = relative_path.parts
                if any(rel_parts[:len(parts)] == parts for parts in excluded_parts):
                    skipped += 1
                    continue

                # Read file content
                content = md_file.read_text(encoding="utf-8")
                
                # Skip empty files
                if not content.strip():
                    skipped += 1
                    continue
                
                # Create a source name with vault: prefix
                relative_path = md_file.relative_to(vault)
                source_name = f"vault:{relative_path}"
                
                # Check if source already exists
                conn = get_db()
                existing = conn.execute(
                    "SELECT id FROM sources WHERE name = ?", (source_name,)
                ).fetchone()
                
                if existing:
                    # Update existing source - delete old chunks first
                    source_id = existing[0]
                    conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
                    conn.commit()
                else:
                    # Create new source
                    source_id = upsert_source(source_name)
                
                conn.close()
                
                # Chunk and embed the content
                chunks = chunk_text(content, max_tokens=500)
                if not chunks:
                    skipped += 1
                    continue
                
                vectors = embed_texts(chunks)
                add_chunks(source_id, [(i, chunks[i], vectors[i]) for i in range(len(chunks))])
                
                synced.append({
                    "name": str(relative_path),
                    "chunks": len(chunks)
                })
                
            except Exception as e:
                errors.append({
                    "file": str(md_file.name),
                    "error": str(e)
                })
        
        # Calculate duration
        end_time = dt.utcnow()
        duration = (end_time - start_time).total_seconds()
        end_timestamp = end_time.isoformat() + "Z"
        
        # Update global tracking variables
        last_rag_sync_time = end_timestamp
        last_rag_sync_duration = duration
        last_rag_sync_error = None
        files_synced_count = len(synced)
        
        # Log completion
        log_message = f"[{end_timestamp}] SYNC COMPLETE | Files: {len(synced)}, Errors: {len(errors)}, Duration: {duration:.1f}s"
        logger.info("rag_sync_complete", message=log_message, files_synced=len(synced), errors=len(errors), duration_seconds=duration)
        
    except Exception as e:
        error_msg = f"RAG sync error: {str(e)}"
        logger.error("rag_sync_error", error=error_msg)
        last_rag_sync_error = error_msg
    finally:
        rag_sync_lock.release()


def _initialize_scheduler():
    """Initialize and start the APScheduler for RAG auto-sync"""
    global scheduler
    
    if not settings.rag_auto_sync_enabled:
        logger.info("rag_sync_disabled", message="RAG auto-sync is disabled")
        return
    
    try:
        scheduler = BackgroundScheduler()
        
        # Add the RAG sync job
        scheduler.add_job(
            _rag_sync_task,
            'interval',
            minutes=settings.rag_auto_sync_interval_minutes,
            id='rag_sync_job',
            name='RAG Auto-Sync',
            replace_existing=True,
            next_run_time=None  # Run immediately on first startup if enabled
        )
        
        scheduler.start()
        logger.info("rag_sync_scheduler_started", interval_minutes=settings.rag_auto_sync_interval_minutes)
        
    except Exception as e:
        logger.error("rag_sync_scheduler_error", error=str(e))


def _shutdown_scheduler():
    """Gracefully shutdown the scheduler"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("rag_sync_scheduler_stopped")


# Initialize scheduler on app startup
_initialize_scheduler()

# Register shutdown handler
import atexit
atexit.register(_shutdown_scheduler)



# ---------- Helpers ----------


def trim_history(messages, model: str, max_tokens: int | None = None):
    """
    Trim oldest non-system turns until under token budget.

    Args:
        messages: List of message dicts
        model: Model name for token encoding
        max_tokens: Maximum tokens (defaults to settings.max_context_tokens)
    """
    if max_tokens is None:
        max_tokens = settings.max_context_tokens
    # For local models, use a simpler character-based estimation
    if is_local_model(model):

        def count_tokens(msgs):
            # Rough estimation: 1 token ≈ 4 characters
            return sum(len(m.get("content", "")) // 4 for m in msgs)

    else:
        try:
            enc = tiktoken.encoding_for_model(model)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

        def count_tokens(msgs):
            return sum(len(enc.encode(m.get("content", ""))) for m in msgs)

    msgs = list(messages)
    while len(msgs) > 1 and count_tokens(msgs) > max_tokens:
        # drop earliest non-system
        for i, m in enumerate(msgs):
            if m.get("role") != "system":
                msgs.pop(i)
                break
        else:
            break
    return msgs


def robust_usage(resp_usage):
    """Support Responses API usage or legacy names; return (in_tok, out_tok)."""
    if not resp_usage:
        return 0, 0
    in_tok = getattr(resp_usage, "input_text_tokens", None)
    out_tok = getattr(resp_usage, "output_text_tokens", None)
    if in_tok is None or out_tok is None:
        in_tok = getattr(resp_usage, "prompt_tokens", 0)
        out_tok = getattr(resp_usage, "completion_tokens", 0)
    return in_tok or 0, out_tok or 0


# --- PDF text extraction helper ---
def _pdf_to_text(file_storage):
    """
    Try multiple PDF parsers to extract text. Returns (text, error).
    Tries, in order: pypdf, PyPDF2, pdfminer.six, PyMuPDF (fitz).
    """
    from io import BytesIO

    # Read bytes once (file_storage.stream may be a stream-like)
    try:
        file_storage.stream.seek(0)
    except Exception:
        pass
    data = file_storage.stream.read()
    if not data:
        return None, "empty_pdf"

    last_exc = None

    # 1) Try pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        pages = []
        for p in reader.pages:
            t = p.extract_text() or ""
            pages.append(t.strip())
        return "\n\n".join(pages).strip(), None
    except Exception as e:
        last_exc = e

    # 2) Try PyPDF2
    try:
        from PyPDF2 import PdfReader as PyPDF2Reader

        reader = PyPDF2Reader(BytesIO(data))
        pages = []
        for p in reader.pages:
            try:
                t = p.extract_text() or ""
            except Exception:
                t = ""
            pages.append(t.strip())
        return "\n\n".join(pages).strip(), None
    except Exception as e:
        last_exc = e

    # 3) Try pdfminer.six
    try:
        from pdfminer.high_level import extract_text

        # extract_text can accept a file-like object
        text = extract_text(BytesIO(data)) or ""
        return text.strip(), None
    except Exception as e:
        last_exc = e

    # 4) Try PyMuPDF (fitz)
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        pages = []
        for page in doc:
            try:
                t = page.get_text() or ""
            except Exception:
                t = ""
            pages.append(t.strip())
        doc.close()
        return "\n\n".join(pages).strip(), None
    except Exception as e:
        last_exc = e

    return None, f"no pdf parser available: {last_exc}"


# Background task executor for scheduled tasks
def run_scheduled_tasks():
    """Start the scheduler service for background tasks"""
    from services.scheduler_service import get_scheduler_service

    try:
        scheduler = get_scheduler_service()
        scheduler.start()
        print("[Scheduler] SchedulerService started successfully")
    except Exception as e:
        print(f"[Scheduler] Error starting scheduler: {e}")


if __name__ == "__main__":
    # Start scheduled task executor
    run_scheduled_tasks()

    # SSL certificate paths
    ssl_cert = r"C:\SharedFiles\certs\cert.pem"
    ssl_key = r"C:\SharedFiles\certs\key.pem"

    # Check if SSL certificates exist
    import os

    # First try the SharedFiles location
    if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        print(f"[SSL] Starting with HTTPS using {ssl_cert}")
        app.run(host="0.0.0.0", port=5000, ssl_context=(ssl_cert, ssl_key), debug=False)
    # Then check for local certificates in the app directory
    elif os.path.exists("cert.pem") and os.path.exists("key.pem"):
        print(f"[SSL] Starting with HTTPS using local certificates")
        app.run(
            host="0.0.0.0", port=5000, ssl_context=("cert.pem", "key.pem"), debug=False
        )
    # Fall back to HTTP only
    else:
        print(
            f"[SSL] No certificates found, starting with HTTP on http://${PROXMOX_HOST_IP}:5000"
        )
        print(f"[SSL] To enable HTTPS, place cert.pem and key.pem in the app directory")
        app.run(host="0.0.0.0", port=5000, debug=False)
