"""
RAG routes blueprint for Flask application
Handles preset management, document uploads, and RAG synchronization
"""

from flask import Blueprint, request, jsonify, Response
from io import BytesIO

# Import necessary modules from parent package
import sys
from pathlib import Path

# Get parent directory for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from rag_db import (
    upsert_source,
    add_chunks,
    list_sources,
    delete_source,
    list_presets_from_db as list_presets,
    get_preset_from_db as get_preset,
    add_preset_to_db,
    update_preset_in_db,
    delete_preset_from_db,
    get_db,
)
from rag import chunk_text, embed_texts
from config import get_settings

# Create blueprint
rag_bp = Blueprint('rag', __name__)

# Get settings
settings = get_settings()


def _pdf_to_text(file_storage):
    """
    Try multiple PDF parsers to extract text. Returns (text, error).
    Tries, in order: pypdf, PyPDF2, pdfminer.six, PyMuPDF (fitz).
    """
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


# ========== PRESETS ==========

@rag_bp.get("/presets")
def route_presets_list():
    return jsonify(list_presets())


@rag_bp.get("/presets/<int:pid>")
def route_presets_get(pid):
    p = get_preset(pid)
    if not p:
        return jsonify({"error": "not_found"}), 404
    return jsonify(p)


@rag_bp.post("/presets")
def route_add_preset():
    data = request.get_json(force=True)
    label = data.get("label")
    system = data.get("system")
    temperature = data.get("temperature")
    if not label:
        return jsonify({"error": "Label is required"}), 400
    new_id = add_preset_to_db(label, system, temperature)
    return jsonify({"id": new_id}), 201


@rag_bp.put("/presets/<int:pid>")
def route_update_preset(pid):
    data = request.get_json(force=True)
    label = data.get("label")
    system = data.get("system")
    temperature = data.get("temperature")
    if not label:
        return jsonify({"error": "Label is required"}), 400
    update_preset_in_db(pid, label, system, temperature)
    return jsonify({"ok": True})


@rag_bp.delete("/presets/<int:pid>")
def route_delete_preset(pid):
    delete_preset_from_db(pid)
    return jsonify({"ok": True})


# ========== RAG UPLOAD/LIST/DELETE ==========

# JSON text upload: { name, text }
@rag_bp.post("/upload")
def upload_text():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    text = (data.get("text") or "").strip()
    if not name or not text:
        return jsonify({"ok": False, "error": "name_and_text_required"}), 400

    sid = upsert_source(name)
    parts = chunk_text(text, max_tokens=500)
    if not parts:
        return jsonify({"ok": False, "error": "no_text_after_chunking"}), 400
    vecs = embed_texts(parts)
    add_chunks(sid, [(i, parts[i], vecs[i]) for i in range(len(parts))])
    return jsonify({"ok": True, "chunks": len(parts)})


# Multipart PDF upload: form-data fields { file=<pdf>, name=<label> }
@rag_bp.post("/upload-pdf")
def upload_pdf():
    f = request.files.get("file")
    name = (request.form.get("name") or "").strip()
    if not f:
        return jsonify({"ok": False, "error": "file_required"}), 400
    if not name:
        raw = f.filename or "PDF"
        name = raw.rsplit(".", 1)[0][:80]

    text, err = _pdf_to_text(f)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    if not text:
        return jsonify({"ok": False, "error": "empty_pdf_text_or_needs_ocr"}), 400

    sid = upsert_source(name)
    parts = chunk_text(text, max_tokens=500)
    if not parts:
        return jsonify({"ok": False, "error": "no_text_after_chunking"}), 400
    vecs = embed_texts(parts)
    add_chunks(sid, [(i, parts[i], vecs[i]) for i in range(len(parts))])
    return jsonify({"ok": True, "chunks": len(parts)})


# List sources
@rag_bp.get("/sources")
def sources_list():
    return jsonify(list_sources())


# Delete a source (called by the web UI)
@rag_bp.post("/sources/delete")
def sources_delete():
    data = request.get_json(force=True) or {}
    sid = data.get("id")
    try:
        sid = int(sid)
    except Exception:
        return jsonify({"ok": False, "error": "bad_id"}), 400
    try:
        delete_source(sid)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Get a chunk by source and ordinal
@rag_bp.get("/chunk")
def get_chunk():
    name = (request.args.get("source") or "").strip()
    ord_i = request.args.get("ord")
    try:
        ord_i = int(ord_i)
    except:
        return {"error": "bad_ord"}, 400
    if not name:
        return {"error": "bad_source"}, 400

    conn = get_db()
    row = conn.execute(
        """
        SELECT c.text
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.name = ? AND c.ord = ?
        LIMIT 1
    """,
        (name, ord_i),
    ).fetchone()
    conn.close()
    if not row:
        return {"error": "not_found"}, 404
    return {"ok": True, "source": name, "ord": ord_i, "text": row[0]}


# ========== RAG SYNCHRONIZATION ==========

@rag_bp.get("/rag-sync-status")
def rag_sync_status():
    """Get the status of RAG auto-sync scheduler"""
    try:
        from apscheduler.schedulers.base import SchedulerAlreadyRunningError

        # Try to import scheduler from main app context
        try:
            from app import scheduler, last_rag_sync_time, last_rag_sync_duration, files_synced_count, last_rag_sync_error
        except (ImportError, AttributeError):
            # Scheduler not available or not initialized
            return jsonify({
                "enabled": False,
                "message": "Scheduler not available"
            }), 200

        if not settings.rag_auto_sync_enabled:
            return jsonify({
                "enabled": False,
                "message": "RAG auto-sync is disabled"
            }), 200

        if scheduler is None or not scheduler.running:
            return jsonify({
                "enabled": True,
                "running": False,
                "message": "Scheduler is not running"
            }), 200

        # Get next scheduled run time
        job = scheduler.get_job('rag_sync_job')
        next_run = job.next_run_time if job else None

        return jsonify({
            "enabled": True,
            "running": scheduler.running,
            "interval_minutes": settings.rag_auto_sync_interval_minutes,
            "last_sync": last_rag_sync_time,
            "last_sync_duration_seconds": last_rag_sync_duration,
            "files_synced": files_synced_count,
            "errors": last_rag_sync_error,
            "next_sync": next_run.isoformat() if next_run else None
        }), 200
    except Exception as e:
        return jsonify({
            "error": str(e),
            "enabled": settings.rag_auto_sync_enabled if hasattr(settings, 'rag_auto_sync_enabled') else False
        }), 500


@rag_bp.post("/obsidian/sync-to-rag")
def obsidian_sync_to_rag():
    """Sync Obsidian vault files to RAG database"""
    try:
        # Import rate limiter from main app if available
        try:
            from app import limiter
        except ImportError:
            limiter = None

        from pathlib import Path

        # Use vault path from settings
        vault = settings.vault_path

        if not vault.exists():
            # Try alternative paths
            alternative_paths = [
                Path("/obsidian-vault"),  # Sibling directory to /app
                Path("../obsidian-vault"),  # Relative to /app
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
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": f"Vault not found at {vault}",
                            "tried_paths": [str(p) for p in alternative_paths],
                        }
                    ),
                    404,
                )

        synced = []
        errors = []
        skipped = 0

        # Find all markdown files in vault
        md_files = list(vault.rglob("*.md"))

        # Get excluded folders from settings (e.g., ["00-Inbox", "90-Meta"])
        # Convert to path parts for robust prefix matching (supports nested excludes)
        from pathlib import Path as PathLib
        excluded_parts = [PathLib(f.strip("/\\")).parts for f in settings.rag_exclude_folders] if settings.rag_exclude_folders else []

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

                # Check if source already exists and has same content
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
                add_chunks(
                    source_id, [(i, chunks[i], vectors[i]) for i in range(len(chunks))]
                )

                synced.append({"name": str(relative_path), "chunks": len(chunks)})

            except Exception as e:
                errors.append({"file": str(md_file.name), "error": str(e)})

        return jsonify(
            {
                "success": True,
                "synced": len(synced),
                "skipped": skipped,
                "errors": len(errors),
                "files": synced[:10],  # Only show first 10
                "error_details": errors[:5],  # Only show first 5 errors
            }
        )

    except FileNotFoundError as e:
        return (
            jsonify({"success": False, "error": "Vault not found", "details": str(e)}),
            404,
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
