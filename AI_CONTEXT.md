# AI_CONTEXT.md - Agent Onboarding

This file is optimized for AI agents (Claude, Codex, Gemini) working on this codebase.

---

## System Architecture

```
Host Machine (${PROXMOX_HOST_IP})
└── LXC Container ${LXC_ID} (Ubuntu)
    ├── Docker: webchat-app (Flask, port 5000)
    ├── Docker: webdav-server (WsgiDAV, port 8080)
    ├── Systemd Services (optional):
    │   ├── claude-proxy (9876)
    │   ├── codex-proxy (9877)
    │   └── gemini-proxy (9878)
    ├── /root/WebAppChat - this codebase
    └── /root/obsidian-vault - Obsidian vault (bind-mounted to Docker)
```

**Path Mapping:**
| Context | WebAppChat Path | Vault Path |
|---------|-----------------|------------|
| Host | `/path/to/WebAppChat` | `/path/to/obsidian-vault` |
| Docker Container | `/app` | `/app/vault` |

**Networking (Docker Context):**
| From | To Access Host Service | To Access Docker Service |
|------|----------------------|--------------------------|
| Docker Container | `host.docker.internal:port` | `localhost:port` |

---

## Tech Stack

- **Backend**: Flask + Gunicorn (Python 3.11), SQLite
- **LLM Providers**: OpenAI, Anthropic, Ollama, CLI proxies (optional)
- **Integrations**: Obsidian vault, Microsoft To Do (optional), Home Assistant (optional)
- **Frontend**: Vanilla JS, SSE streaming, Web Speech API

---

## Vault Structure

The vault uses a PARA-inspired numbered folder hierarchy. **Never hardcode folder names.**

### System Folders (Configured in .env)

| Folder | Config Variable | Purpose |
|--------|-----------------|---------|
| `00-Inbox/` | `INBOX_FOLDER` | Quick captures |
| `60-Calendar/Daily/` | `DAILY_NOTES_FOLDER` | Daily notes |
| `90-Meta/Templates/` | `TEMPLATES_FOLDER` | Note templates |
| `90-Meta/Attachments/` | `ATTACHMENTS_FOLDER` | Images, uploads |

### Folder Discovery Pattern

```python
# CORRECT - discover folders dynamically
structure = obsidian_service.list_vault_structure()
available_folders = list(structure["folders"].keys())

# WRONG - assuming folder exists
path = vault / "Projects" / "my-note.md"  # May not exist!
```

---

## Critical Rules

### 1. Path Security
**Always use `safe_vault_path()`** for any vault file operations.

```python
from utils.vault_security import safe_vault_path

# CORRECT
safe_path = safe_vault_path(vault_root, user_provided_path)

# WRONG - path traversal vulnerability
path = vault_root / user_provided_path
```

### 2. No Hardcoded Folder Names
**Always use config settings** for system folders.

```python
# CORRECT
daily_path = vault / settings.daily_notes_folder / f"{date}.md"

# WRONG - breaks if user customizes folders
daily_path = vault / "Daily Notes" / f"{date}.md"
```

---

## Code Layers

```
Routes (routes/*.py)      ← HTTP endpoints, thin wrappers
    ↓
Services (services/*.py)  ← Business logic, the "brain"
    ↓
Providers (providers/*.py) ← LLM API adapters
    ↓
Database (*_db.py)        ← Persistence layer
```

---

## Common Operations

### Restart App
```bash
docker restart webchat-app
```

### View Logs
```bash
docker logs webchat-app --tail 100 -f
```

### Run Tests
```bash
docker exec webchat-app pytest tests/ -v
```

---

## No-Go List

| Forbidden Action | Why |
|------------------|-----|
| Create root-level vault folders | User controls vault structure |
| Move `chats.sqlite3` or `rag.sqlite3` | External scripts may depend on paths |
| Hardcode folder paths | Breaks user customization |
| Commit `.env` or credentials | Contains secrets |

---

*Last updated: 2026-01-16*
