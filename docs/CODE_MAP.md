---
title: Codebase Map
last_verified: 2026-01-12
verified_by: Codex
applies_to: Post-Cleanup Workspace
---

# WebAppChat Codebase Map

High-level map of the `WebAppChat` codebase for quick orientation.

## Root Directory

| File | Purpose |
| :--- | :--- |
| `app.py` | Flask app setup and route registration. |
| `config.py` | Pydantic settings loaded from `.env`. |
| `prices.py` | Model catalog and pricing. |
| `context_aware.py` | Prompt context injection. |
| `autonomous_prompts.py` | Autonomous prompt presets. |
| `prompt_variants.py` | System prompt variants. |
| `obsidian.py` | Legacy wrapper over the Obsidian service. |
| `obsidian_functions.py` | Obsidian tool functions. |
| `general_tools.py` | Generic tool functions. |
| `ollama_tooling.py` | Ollama tool formatting. |
| `auth_routes.py` | Auth endpoints (root-level). |
| `observability.py` | Logging/telemetry helpers. |
| `docker-compose.yml` | Docker services; Ollama is commented out. |
| `Dockerfile` | Webchat build. |
| `Dockerfile.webdav` | WebDAV build. |

## Services (`services/`)
Business logic used by routes.

| Service | Purpose |
| :--- | :--- |
| `llm_service.py` | LLM routing, streaming, tool loops. |
| `obsidian_service.py` | Vault read/write/search logic. |
| `tool_calling_service.py` | Tool call parsing and execution. |
| `conversation_service.py` | Chat formatting and limits. |
| `rag_service.py` | RAG ingest and retrieval. |
| `storage_service.py` | Chat persistence API. |
| `cost_tracking_service.py` | Usage and cost tracking. |
| `scheduler_service.py` | Background job scheduling. |

## Routes (`routes/`)
Flask endpoints (auth routes live at root).

| File | Purpose |
| :--- | :--- |
| `chat_routes.py` | `/api/chat/*` endpoints. |
| `obsidian_routes.py` | `/api/obsidian/*` endpoints. |
| `rag_routes.py` | `/api/rag/*` endpoints. |
| `voice_routes.py` | `/api/voice/*` endpoints. |
| `admin_routes.py` | Admin endpoints. |
| `analytics_routes.py` | Analytics endpoints. |

## Providers (`providers/`)
LLM adapters.

| File | Purpose |
| :--- | :--- |
| `base.py` | Provider interface. |
| `openai_provider.py` | OpenAI adapter. |
| `anthropic_provider.py` | Anthropic adapter. |
| `ollama_provider.py` | Ollama adapter. |
| `ollama_mcp_provider.py` | Ollama MCP adapter. |
| `embedding_provider.py` | Embedding adapter. |

## Database Layer

| File | Purpose |
| :--- | :--- |
| `auth_db.py` | Users and auth persistence. |
| `chat_db.py` | Chats and messages persistence. |
| `rag_db.py` | RAG embeddings persistence. |
| `user_settings_db.py` | User settings persistence. |
| `storage.py` | Deprecated wrapper over StorageService. |
| `storage_sqlite.py` | SQLite chat storage module. |

## Tooling and Schemas

| File | Purpose |
| :--- | :--- |
| `tool_schema.py` | Tool JSON schema for LLM calls. |
| `obsidian_tool_models.py` | Pydantic models for tool IO. |
| `obsidian_tools.schema.json` | Obsidian tool schema definitions. |
| `mcp_stdio.py` | MCP filesystem server helper/bridge. |
| `schema_generator.py` | Stub for `scripts/schema_generator.py`. |

## Integrations

| Integration | Files | Purpose |
| :--- | :--- | :--- |
| Microsoft To Do | `microsoft_todo_service.py`, `microsoft_todo_functions.py`, `sync_todo_to_obsidian.py` | Graph API and vault sync. |
| Smarthome / Home Assistant | `smarthome_functions.py` | Tool functions for HA control. |

## WebDAV

| File | Purpose |
| :--- | :--- |
| `webdav_server.py` | WebDAV server entrypoint. |
| `webdav_config.py` | WebDAV configuration. |
| `webdav_security.py` | WebDAV auth and guards. |
| `webdav_users.json` | Credentials file (gitignored). |

## Frontend

* `templates/`: Jinja templates.
* `static/`: JS/CSS/assets.

## Data & Scripts

* `chats.sqlite3`: Chat/user DB.
* `rag.sqlite3`: RAG embeddings DB.
* `data/`: Reserved for DB consolidation.
* `scripts/`: Operational scripts (deploy, certs, sync, schema).
* Root stubs: `manage.py`, `deploy.sh`, `generate_webdav_credentials.py`, `sync_todo_to_obsidian.py`.
* `vault/`: Mounted Obsidian vault (host-mapped).

---
*Updated by Codex on 2026-01-12*
