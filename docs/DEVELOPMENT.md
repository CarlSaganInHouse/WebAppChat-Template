---
title: Development Guide
last_verified: 2026-01-11
verified_by: Claude
applies_to: Current codebase
---

# Development Guide

This guide covers code patterns, testing, and development workflows for WebAppChat. It's written for AI agents and developers working on the codebase.

---

## Project Structure Overview

The codebase follows a layered architecture:

```
Routes (routes/*.py)       → HTTP endpoints, request validation
    ↓
Services (services/*.py)   → Business logic, orchestration
    ↓
Providers (providers/*.py) → LLM API adapters
    ↓
Database (*_db.py)         → Persistence layer
```

**Full code map:** See `Project_Structure.md` in repo root.

---

## Code Conventions

### Import Organization

```python
# Standard library
import os
from pathlib import Path
from datetime import datetime

# Third-party
from flask import Blueprint, request, jsonify
import structlog

# Local - config first
from config import get_settings

# Local - by layer (db → services → routes)
from chat_db import get_chat_db
from services.obsidian_service import ObsidianService
```

### Settings Access

Always use the settings object, never hardcode paths or values:

```python
# CORRECT
from config import get_settings
settings = get_settings()
vault_path = settings.vault_path
daily_folder = settings.daily_notes_folder

# WRONG - breaks user customization
vault_path = Path("/app/vault")
daily_folder = "Daily Notes"
```

### Path Security

All user-provided paths must go through `safe_vault_path()`:

```python
from utils.vault_security import safe_vault_path

# CORRECT - validates path doesn't escape vault
safe_path = safe_vault_path(settings.vault_path, user_path)

# WRONG - path traversal vulnerability
path = settings.vault_path / user_path
```

### Logging

Use structlog for structured logging:

```python
import structlog
logger = structlog.get_logger()

# Good - structured context
logger.info("note_created", path=str(note_path), user_id=user_id)

# Avoid - unstructured messages
print(f"Created note at {note_path}")
```

### Error Handling in Routes

Return consistent JSON error responses:

```python
@bp.post("/endpoint")
def my_endpoint():
    if not valid:
        return jsonify({"error": "error_code", "detail": "Human message"}), 400

    try:
        result = service.do_thing()
        return jsonify(result), 200
    except SpecificError as e:
        logger.error("operation_failed", error=str(e))
        return jsonify({"error": "operation_failed", "detail": str(e)}), 500
```

---

## Layer Responsibilities

### Routes (`routes/*.py`)

Routes are **thin wrappers**. They should:
- Validate request input
- Call services
- Format responses
- Handle HTTP concerns (status codes, headers)

Routes should **not** contain business logic.

```python
# CORRECT - delegates to service
@bp.post("/notes")
def create_note():
    data = request.get_json()
    result = obsidian_service.create_note(
        content=data.get("content"),
        destination=data.get("destination")
    )
    return jsonify(result), 200 if result["success"] else 400

# WRONG - business logic in route
@bp.post("/notes")
def create_note():
    data = request.get_json()
    path = vault / data["destination"] / data["filename"]
    path.write_text(data["content"])  # Don't do this!
    return jsonify({"ok": True})
```

### Services (`services/*.py`)

Services contain **business logic**. They should:
- Orchestrate operations
- Enforce business rules
- Call other services and databases
- Return structured results

```python
# services/obsidian_service.py
class ObsidianService:
    def create_note(self, content: str, destination: str, ...) -> dict:
        # Validate path
        safe_path = safe_vault_path(self.vault, destination)

        # Apply business rules
        if safe_path.exists() and mode == "create":
            return {"success": False, "error": "File already exists"}

        # Perform operation
        safe_path.write_text(content)

        # Verify if enabled
        if settings.verify_vault_writes:
            self._verify_write(safe_path, content)

        return {"success": True, "path": str(safe_path)}
```

### Providers (`providers/*.py`)

Providers are **API adapters**. They implement a common interface:

```python
# providers/base.py pattern
class LLMProvider:
    def chat(self, messages, model, temperature, tools) -> dict: ...
    def chat_stream(self, messages, model, ...) -> Generator: ...
```

Each provider translates to/from its backend's format:
- `openai_provider.py` → OpenAI API
- `anthropic_provider.py` → Anthropic API
- `ollama_provider.py` → Local Ollama

---

## Adding New Features

### Adding a New Tool (LLM Function)

1. **Define the function** in the appropriate `*_functions.py`:

```python
# obsidian_functions.py
def archive_note(file_path: str) -> dict:
    """Move a note to the archive folder."""
    service = ObsidianService()
    return service.archive_note(file_path)
```

2. **Add to the function list**:

```python
# obsidian_functions.py
OBSIDIAN_FUNCTIONS = [
    # ... existing functions
    {
        "name": "archive_note",
        "description": "Move a note to the archive folder",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the note relative to vault root"
                }
            },
            "required": ["file_path"]
        },
        "function": archive_note
    }
]
```

3. **Add validation** in `tool_schema.py` if needed.

4. **For Ollama**, add to `LOCAL_MODEL_CORE_TOOLS` in `ollama_tooling.py`.

### Adding a New Route

1. **Create or extend a blueprint** in `routes/`:

```python
# routes/my_routes.py
from flask import Blueprint, request, jsonify

my_bp = Blueprint('my_feature', __name__)

@my_bp.post("/my-endpoint")
def my_endpoint():
    # Implementation
    pass
```

2. **Register in `app.py`**:

```python
from routes.my_routes import my_bp
app.register_blueprint(my_bp, url_prefix='/api/my-feature')
```

### Adding a New Provider

1. **Create provider file** in `providers/`:

```python
# providers/my_provider.py
from providers.base import LLMProvider

class MyProvider(LLMProvider):
    def chat(self, messages, model, temperature=0.7, tools=None):
        # Translate to backend format
        # Call API
        # Translate response back
        pass

    def chat_stream(self, messages, model, ...):
        # Streaming implementation
        pass
```

2. **Register in `llm_service.py`** provider routing.

3. **Add models to `prices.py`** `MODEL_CATALOG`.

---

## Testing

### Test Structure

```
tests/
├── test_auth.py           # Authentication tests
├── test_chat_db.py        # Chat database tests
├── test_config.py         # Configuration validation
├── test_obsidian_*.py     # Obsidian integration tests
├── test_rag_*.py          # RAG functionality tests
├── test_providers.py      # LLM provider tests
└── obsidian_tool_benchmark/  # Performance benchmarks
```

### Running Tests

**Inside Docker container** (recommended for consistency):

```bash
docker exec webchat-app pytest tests/ -v
```

**Specific test file:**

```bash
docker exec webchat-app pytest tests/test_obsidian_service.py -v
```

**By marker:**

```bash
# Skip slow tests
docker exec webchat-app pytest -m "not slow"

# Only RAG tests
docker exec webchat-app pytest -m rag

# Only security tests
docker exec webchat-app pytest -m security
```

**From LXC container** (if not using Docker):

```bash
cd /root/WebAppChat
python -m pytest tests/ -v
```

### Test Markers

Defined in `pytest.ini`:

| Marker | Purpose |
|--------|---------|
| `@pytest.mark.slow` | Long-running tests |
| `@pytest.mark.integration` | Requires external services |
| `@pytest.mark.security` | Security-related tests |
| `@pytest.mark.rag` | RAG functionality |
| `@pytest.mark.obsidian` | Obsidian integration |

### Writing Tests

**Use fixtures** for common setup:

```python
@pytest.fixture
def mock_vault(tmp_path, monkeypatch):
    """Create a temporary vault for testing."""
    vault = tmp_path / "test_vault"
    vault.mkdir()
    (vault / "00-Inbox").mkdir()
    (vault / "60-Calendar" / "Daily").mkdir(parents=True)

    monkeypatch.setenv('VAULT_PATH', str(vault))

    # Reload config to pick up new path
    import importlib
    import config
    importlib.reload(config)

    return vault
```

**Test naming convention:**

```python
class TestCreateNote:
    def test_creates_file_in_correct_location(self, mock_vault):
        """Should create file at specified path."""
        pass

    def test_fails_if_file_exists_in_create_mode(self, mock_vault):
        """Should return error when file exists and mode is 'create'."""
        pass

    def test_rejects_path_traversal_attempts(self, mock_vault):
        """Should reject paths that escape vault root."""
        pass
```

---

## Development Workflows

### Making Code Changes

1. **Read existing code first** - Understand the patterns before modifying
2. **Check for tests** - Run related tests before and after changes
3. **Follow layer boundaries** - Don't put business logic in routes
4. **Use settings** - Never hardcode paths or config values

### Testing Changes Locally

```bash
# 1. Make changes to code

# 2. Restart container to pick up changes
docker restart webchat-app

# 3. Check logs for errors
docker logs webchat-app --tail 50

# 4. Run relevant tests
docker exec webchat-app pytest tests/test_<relevant>.py -v
```

### Rebuilding the Docker Image

If you change `Dockerfile`, `requirements*.txt`, or system packages, rebuild the image (restart alone is not enough):

```bash
# From LXC container (ID 500)
cd /root/WebAppChat
docker compose build webchat-app
docker compose up -d webchat-app
```

If your setup uses `docker-compose`, substitute that for `docker compose`.

### Database Changes

The app uses SQLite databases. To inspect:

```bash
# Chat database
docker exec webchat-app sqlite3 /app/chats.sqlite3 ".tables"
docker exec webchat-app sqlite3 /app/chats.sqlite3 "SELECT * FROM users"

# RAG database
docker exec webchat-app sqlite3 /app/rag.sqlite3 ".tables"
docker exec webchat-app sqlite3 /app/rag.sqlite3 "SELECT COUNT(*) FROM chunks"
```

**Schema changes** require migration scripts. Don't modify tables directly in production.

---

## Environment-Specific Notes

### Docker vs Host

| Task | Docker | Host/LXC |
|------|--------|----------|
| Run tests | `docker exec webchat-app pytest` | `python -m pytest` |
| View logs | `docker logs webchat-app` | Check Gunicorn output |
| Vault path | `/app/vault` | `/root/obsidian-vault` |
| Config | `.env` loaded by compose | `.env` in repo root |

### Path Mapping

| Context | Repo Path | Vault Path |
|---------|-----------|------------|
| Proxmox Host | `/rpool/data/subvol-${LXC_ID}-disk-0/root/WebAppChat` | `/rpool/data/subvol-${LXC_ID}-disk-0/root/obsidian-vault` |
| LXC Container | `/root/WebAppChat` | `/root/obsidian-vault` |
| Docker Container | `/app` | `/app/vault/obsidian-vault` |

### Proxy Service Debugging (Claude/Codex/Gemini)

Proxy health checks and expected responses live in `docs/OPERATIONS.md`.

---

## Common Gotchas

### 1. Forgetting to Reload Config

After changing `.env`, restart the container:
```bash
docker restart webchat-app
```

### 2. Path Security Bypass

Always use `safe_vault_path()`. Direct path concatenation is a security vulnerability.

### 3. Hardcoded Folder Names

Use `settings.daily_notes_folder`, not `"Daily Notes"`. Users can customize these.

### 4. localhost vs host.docker.internal

Inside Docker, use `host.docker.internal` to reach services on the LXC host:
```python
# WRONG (from inside Docker)
ollama_url = "http://localhost:11434"

# CORRECT
ollama_url = "http://host.docker.internal:11434"
```

### 5. Test Isolation

Tests that modify config must reload modules:
```python
import importlib
import config
importlib.reload(config)
```

---

## Documentation Maintenance

To prevent doc drift:

- When `.env` or `config.py` settings change, update `CONFIGURATION.md` and bump its `last_verified` header.
- When routes or request/response schemas change, update `API.md` and bump its `last_verified` header.

Optional later improvement: auto-generate the config and API reference sections from code to keep them in sync.

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - System design deep dive
- [API.md](API.md) - Endpoint reference
- [CONFIGURATION.md](CONFIGURATION.md) - All settings explained
- [Project_Structure.md](../Project_Structure.md) - Full code map
- [AI_CONTEXT.md](../AI_CONTEXT.md) - Agent onboarding
