"""
Obsidian Routes Blueprint

This module contains all Obsidian vault-related routes extracted from app.py.
Includes endpoints for daily notes, note creation, job creation, and vault structure.
"""

from flask import Blueprint, request, jsonify

# Obsidian integration functions
from obsidian import (
    append_to_daily,
    create_note,
    read_daily_note,
    list_vault_structure,
)

# Create blueprint
obsidian_bp = Blueprint('obsidian', __name__)


# ---------- Obsidian Vault Endpoints ----------


@obsidian_bp.post("/obsidian/append-daily")
def obsidian_append_daily():
    """Append content to today's daily note"""
    data = request.get_json(force=True)
    content = data.get("content", "").strip()
    section = data.get("section", "Quick Captures")

    if not content:
        return jsonify({"error": "No content provided"}), 400

    result = append_to_daily(content, section)

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 500


@obsidian_bp.post("/obsidian/create-note")
def obsidian_create_note():
    """Create a new note in the Obsidian vault"""
    data = request.get_json(force=True)
    content = data.get("content", "")
    destination = data.get("destination", "")
    filename = data.get("filename")
    mode = data.get("mode", "create")  # create, append, or overwrite

    if not content:
        return jsonify({"error": "content is required"}), 400
    if not destination:
        return jsonify({"error": "destination is required"}), 400

    result = create_note(content, destination, filename, mode)

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), (
            400 if "already exists" in result.get("error", "") else 500
        )


@obsidian_bp.post("/obsidian/create-job")
def obsidian_create_job():
    """
    DEPRECATED: Create a new job note.
    Use /obsidian/create-note with a template instead.
    """
    return jsonify({
        "success": False,
        "error": "create-job is deprecated. Use /obsidian/create-note with create_from_template instead.",
        "deprecated": True,
        "alternative": "/obsidian/create-note"
    }), 410  # HTTP 410 Gone


@obsidian_bp.get("/obsidian/daily/<date_str>")
@obsidian_bp.get("/obsidian/daily")
def obsidian_read_daily(date_str=None):
    """Read a daily note (default: today)"""
    result = read_daily_note(date_str)

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 404


@obsidian_bp.get("/obsidian/structure")
def obsidian_structure():
    """Get vault structure"""
    result = list_vault_structure()

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 500
