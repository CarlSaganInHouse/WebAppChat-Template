"""
Admin and debug routes for the Flask application.
These routes are extracted from app.py and organized in a blueprint.
"""

from flask import Blueprint, jsonify, request
import subprocess
import sys
import json

# Import dependencies from config and local modules
from config import get_settings
from prices import allowed_models, is_local_model
from observability import get_tool_call_summary

# Initialize settings
settings = get_settings()

# Create the admin blueprint
admin_bp = Blueprint('admin', __name__)

# Import ollama client - will be initialized by the main app
import ollama
ollama_client = None  # Will be set by the app when registering the blueprint


def set_ollama_client(client):
    """Set the ollama client instance for this blueprint"""
    global ollama_client
    ollama_client = client


# ---------- Admin/Debug Routes ----------


@admin_bp.get("/favicon.ico")
def favicon():
    """Handle favicon requests"""
    return "", 204  # No Content - simple way to handle favicon requests


@admin_bp.get("/_debug_env")
def _debug_env():
    """Debug endpoint to show environment info (disabled by default)"""
    if not settings.allow_debug_endpoint:
        return jsonify({"error": "disabled"}), 404

    parsers = {}
    for mod in ("pypdf", "PyPDF2", "pdfminer", "fitz"):
        try:
            __import__(mod)
            parsers[mod] = True
        except Exception:
            parsers[mod] = False

    return jsonify(
        {
            "executable": sys.executable,
            "python_version": sys.version,
            "parsers": parsers,
            "sys_path": sys.path[:10],
        }
    )


@admin_bp.get("/models")
def route_list_models():
    """Get list of available models with metadata, plus default model and grouped data"""
    from prices import get_model_meta, get_models_by_category, DEFAULT_MODEL
    from flask import make_response
    models = [get_model_meta(m) for m in allowed_models()]
    grouped = get_models_by_category()
    payload = {
        "models": models,
        "grouped": grouped,  # Models organized by category for grouped dropdown
        "default": DEFAULT_MODEL
    }
    response = make_response(jsonify(payload))
    # Prevent Cloudflare and browser caching
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@admin_bp.get("/ollama-status")
def route_ollama_status():
    """Get current Ollama model loading status"""
    try:
        # Get currently loaded models
        result = subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=5
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:  # Skip header line
                loaded_models = []
                for line in lines[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 5:
                        model_name = parts[0]
                        size = " ".join(parts[2:4])  # Size might be "5.9 GB"
                        until = " ".join(parts[4:])  # "2 minutes from now"
                        loaded_models.append(
                            {
                                "name": model_name,
                                "size": size,
                                "until": until,
                                "loaded": True,
                            }
                        )

                # Check which of our local models are loaded
                our_models = [m for m in allowed_models() if is_local_model(m)]
                model_status = []
                for model in our_models:
                    is_loaded = any(lm["name"] == model for lm in loaded_models)
                    if is_loaded:
                        loaded_info = next(
                            lm for lm in loaded_models if lm["name"] == model
                        )
                        model_status.append(loaded_info)
                    else:
                        model_status.append(
                            {
                                "name": model,
                                "loaded": False,
                                "size": "Not loaded",
                                "until": "Not loaded",
                            }
                        )

                return jsonify(
                    {
                        "status": "ok",
                        "models": model_status,
                        "total_loaded": len(loaded_models),
                    }
                )
            else:
                return jsonify(
                    {
                        "status": "ok",
                        "models": [
                            {"name": m, "loaded": False}
                            for m in allowed_models()
                            if is_local_model(m)
                        ],
                        "total_loaded": 0,
                    }
                )
        else:
            return jsonify(
                {"status": "error", "message": "Could not get Ollama status"}
            )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@admin_bp.get("/list-models")
def list_models():
    """List available Ollama models"""
    try:
        models = ollama.list()
        model_names = []
        if hasattr(models, "models"):
            model_names = [
                model.name if hasattr(model, "name") else str(model)
                for model in models.models
            ]
        elif isinstance(models, dict) and "models" in models:
            model_names = [model.get("name", str(model)) for model in models["models"]]

        return jsonify(
            {"success": True, "models": model_names, "count": len(model_names)}
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.post("/investigate-qwen-thinking")
def investigate_qwen_thinking():
    """Debug endpoint to investigate Qwen3 thinking output structure"""
    data = request.get_json()

    # Simple test prompt to trigger thinking
    test_prompt = data.get(
        "prompt", "Solve this problem: What is 15 * 23? Think through it step by step."
    )
    model = data.get("model", "qwen2.5:3b")

    try:
        # Get raw chunks from Ollama
        response = ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": test_prompt}],
            stream=True,
        )

        chunks = []
        full_response = ""

        for chunk in response:
            # Convert chunk to dict if it's an object
            chunk_dict = {}
            if hasattr(chunk, "__dict__"):
                chunk_dict = chunk.__dict__
            elif isinstance(chunk, dict):
                chunk_dict = chunk
            else:
                chunk_dict = {"raw": str(chunk)}

            chunks.append(chunk_dict)

            # Try to extract content
            content = ""
            if hasattr(chunk, "message") and hasattr(chunk.message, "content"):
                content = chunk.message.content
            elif (
                isinstance(chunk, dict)
                and "message" in chunk
                and "content" in chunk["message"]
            ):
                content = chunk["message"]["content"]
            elif "content" in chunk_dict:
                content = chunk_dict["content"]

            full_response += content

        return jsonify(
            {
                "success": True,
                "prompt": test_prompt,
                "model": model,
                "full_response": full_response,
                "total_chunks": len(chunks),
                "sample_chunks": (
                    chunks[:3] if len(chunks) > 3 else chunks
                ),  # First 3 chunks for analysis
                "chunk_structure": list(chunks[0].keys()) if chunks else [],
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.get("/debug/tool-call-stats")
def debug_tool_call_stats():
    """Return tool call observability metrics (Phase 1)"""
    try:
        return jsonify(get_tool_call_summary()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
