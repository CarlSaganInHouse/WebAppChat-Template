---
title: Configuration Reference
last_verified: 2026-01-16
verified_by: Claude
applies_to: config.py (current)
---

# Configuration Reference

All configuration is managed via environment variables, loaded by Pydantic Settings from `.env` or system environment. Settings have sensible defaults for development.

**Source of truth:** `config.py`

---

## Quick Start

1. Copy `.env.example` to `.env`
2. Set required API keys (at minimum, `OPENAI_API_KEY`)
3. Adjust paths if not using Docker defaults
4. Restart the application

---

## API Keys

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENAI_API_KEY` | string | `""` | **Required.** OpenAI API key for GPT models and embeddings. |
| `ANTHROPIC_API_KEY` | string | `null` | Anthropic API key for Claude models. |
| `GOOGLE_API_KEY` | string | `null` | Google API key for Gemini models. |

**Security:** Never commit these to git. Use `.env` file (gitignored) or environment variables.

---

## LLM Configuration

| Variable | Type | Default | Range | Description |
|----------|------|---------|-------|-------------|
| `DEFAULT_MODEL` | string | `gpt-4o-mini` | - | Default LLM model for chat. |
| `MAX_CONTEXT_TOKENS` | int | `8000` | 1000-128000 | Maximum tokens in conversation context. |

---

## Agent Mode

Controls how the LLM interacts with tools.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AGENT_MODE` | string | `structured` | `structured` = 30+ specific tools with routing. `autonomous` = 5 general tools with permissive prompts. |
| `AUTONOMOUS_VERIFY_WRITES` | bool | `false` | Enable write verification in autonomous mode. |
| `ENABLE_ENHANCED_VAULT_GUIDANCE` | bool | `true` | Include detailed vault guidance in system prompts. |
| `REQUIRE_TOOL_FOR_WRITES` | bool | `true` | Force retry when write-intent requests omit tool calls. |
| `REQUIRE_TOOL_FOR_READS` | bool | `true` | Force retry when read-intent requests omit tool calls. |

**Tool Call Enforcement Details:**

The intent guards detect user requests that require tool usage and enforce tool calls:

- **Write Intent**: Triggered by verbs like "create", "add", "update", "save" combined with targets like "note", "task", "file"
- **Read Intent**: Triggered by verbs like "check", "search", "find", "read" combined with targets like "note", "vault", "project"

When intent is detected:
1. **OpenAI**: Uses `tool_choice="required"` to force tool calls (hard enforcement)
2. **Anthropic**: Retries with a reminder if no tool was called (soft enforcement)
3. Both providers include a RESPONSE STYLE prompt to suppress anticipatory narration
4. **Post-tool response clamp**: After tool execution, a system message instructs the model to respond with the answer only, without narrating tool usage

Set to `false` to disable enforcement (model may output text instead of calling tools).
| `VERIFY_VAULT_WRITES` | bool | `true` | Perform read-after-write check for note operations. |
| `VERIFICATION_MAX_RETRIES` | int | `2` | Max retry attempts for failed verifications (0-5). |
| `VERIFICATION_RETRY_DELAY` | float | `0.5` | Delay in seconds between retries (0.0-5.0). |
| `VERIFICATION_STRICT_MODE` | bool | `true` | If `true`, mark operation failed on verification failure. If `false`, log warning only. |

---

## RAG (Retrieval-Augmented Generation)

| Variable | Type | Default | Range | Description |
|----------|------|---------|-------|-------------|
| `CHUNK_SIZE` | int | `500` | 100-2000 | Max tokens per text chunk. |
| `CHUNK_OVERLAP` | int | `50` | 0-500 | Token overlap between chunks. |
| `TOP_K` | int | `5` | 1-20 | Number of results from RAG search. |
| `EMBEDDING_MODEL` | string | `text-embedding-3-small` | - | OpenAI embedding model. |
| `RAG_DB_PATH` | path | `rag.sqlite3` | - | Path to RAG SQLite database. |

### RAG Auto-Sync

| Variable | Type | Default | Range | Description |
|----------|------|---------|-------|-------------|
| `RAG_AUTO_SYNC_ENABLED` | bool | `true` | - | Enable automatic vault sync to RAG. |
| `RAG_AUTO_SYNC_INTERVAL_MINUTES` | int | `15` | 5-60 | Sync interval in minutes. |
| `RAG_SYNC_ON_STARTUP` | bool | `true` | - | Sync on application startup. |
| `RAG_SYNC_LOG_PATH` | path | `logs/rag_sync.log` | - | Path to sync log file. |

---

## Obsidian Vault

### Core Paths

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VAULT_PATH` | path | `/app/vault` | Path to Obsidian vault directory. In Docker, this is bind-mounted from host. |
| `VAULT_NAME` | string | `obsidian-vault` | Vault name for generating `obsidian://` deep links. |
| `TIMEZONE` | string | `America/New_York` | User's timezone for daily notes (e.g., `Europe/London`). |

### Folder Structure

These define the PARA-inspired folder hierarchy. **Do not hardcode these in application code.**

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `INBOX_FOLDER` | string | `00-Inbox` | Quick captures, unsorted items. |
| `DAILY_NOTES_FOLDER` | string | `60-Calendar/Daily` | Daily notes location. |
| `TEMPLATES_FOLDER` | string | `90-Meta/Templates` | Note templates. |
| `ATTACHMENTS_FOLDER` | string | `90-Meta/Attachments` | Image uploads and attachments. |
| `RAG_EXCLUDE_FOLDERS` | list | `["00-Inbox","90-Meta"]` | Folders to exclude from RAG indexing. Accepts JSON array or comma-separated. |
| `TODO_SYNC_PATH` | string | `60-Calendar/Task-List.md` | Path for Microsoft To Do sync file. |

**Example `.env`:**
```bash
INBOX_FOLDER=00-Inbox
DAILY_NOTES_FOLDER=60-Calendar/Daily
TEMPLATES_FOLDER=90-Meta/Templates
ATTACHMENTS_FOLDER=90-Meta/Attachments
RAG_EXCLUDE_FOLDERS=["00-Inbox","90-Meta"]
```

---

## Ollama (Local Models)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OLLAMA_HOST` | string | `http://ollama:11434` | Ollama service URL. Use `http://localhost:11434` for local dev. |
| `OLLAMA_PROMPT_VARIANT` | string | `NO_PROMPT` | System prompt variant. Options: `NO_PROMPT`, `TIME_ONLY`, `CURRENT`, `OBSIDIAN_ONLY`, `CLAUDE_STYLE`, `STRUCTURED_COMPACT`, `ACTION_FOCUSED`. |
| `OLLAMA_TEMPERATURE` | float | `0.3` | Sampling temperature (0.0-2.0). Lower = more deterministic. |
| `OLLAMA_PAYLOAD_DEBUG_DIR` | path | `null` | If set, write request payloads here for debugging. |

---

## Flask Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLASK_ENV` | string | `production` | Environment: `development` or `production`. |
| `FLASK_DEBUG` | bool | `false` | Enable Flask debug mode (auto-reload, debugger). |
| `PORT` | int | `5000` | Server port (1-65535). |
| `ALLOW_DEBUG_ENDPOINT` | bool | `false` | Enable `/_debug_env` endpoint. **Development only.** |

---

## Rate Limiting

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `RATE_LIMIT_ENABLED` | bool | `true` | Enable rate limiting. |
| `RATE_LIMIT_DEFAULT` | string | `200 per day, 50 per hour` | Default limit for all endpoints. |
| `RATE_LIMIT_ASK` | string | `20 per minute` | Limit for `/ask` endpoint (most expensive). |

---

## Chat Storage

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `USE_SQLITE_CHATS` | bool | `false` | Use SQLite instead of JSON files for chat storage. |
| `CHATS_DIR` | path | `chats` | Directory for JSON chat files. |
| `CHAT_DB_PATH` | path | `chats.sqlite3` | Path to chat SQLite database. |
| `USAGE_LOG_PATH` | path | `chats/usage_log.csv` | Path to usage/cost log CSV. |

---

## WebDAV Server

For remote Obsidian sync (e.g., from mobile devices).

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `WEBDAV_ENABLED` | bool | `false` | Enable WebDAV server. |
| `WEBDAV_PORT` | int | `8080` | WebDAV server port. |
| `WEBDAV_AUTH_USERS` | string | `{}` | JSON dict of `username:bcrypt_hash`. Generate with `scripts/generate_webdav_credentials.py`. |
| `WEBDAV_MAX_FILE_SIZE` | int | `104857600` | Max upload size in bytes (default: 100MB). |
| `WEBDAV_LOG_LEVEL` | string | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

---

## MCP (Model Context Protocol)

For structured tool calling with compatible local models.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_ENABLED` | bool | `true` | Enable MCP filesystem. |
| `MCP_ALLOWED_DIRS` | string | `/mnt/obsidian-vault` | Comma-separated allowed directories. |
| `MCP_MAX_ITERATIONS` | int | `5` | Max function call iterations (1-20). |
| `MCP_FUNCTION_TIMEOUT` | int | `30` | Function execution timeout in seconds (5-300). |
| `MCP_LOG_FUNCTION_CALLS` | bool | `true` | Log all function calls. |

---

## Voice Assistant

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VOICE_ENABLED` | bool | `true` | Enable voice endpoints (`/voice/*`). |
| `WHISPER_MODEL` | string | `whisper-1` | OpenAI Whisper model for STT. |
| `TTS_MODEL` | string | `tts-1` | OpenAI TTS model (`tts-1`, `tts-1-hd`). |
| `TTS_VOICE` | string | `alloy` | TTS voice: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`. |
| `VOICE_CHAT_PREFIX` | string | `Kitchen Voice` | Prefix for voice chat session names. |
| `VOICE_MAX_AUDIO_MB` | int | `10` | Max audio upload size in MB (1-25). |
| `VOICE_DEFAULT_MODEL` | string | `gpt-4o-mini` | Default LLM for voice interactions. |

---

## Authentication

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AUTH_ENABLED` | bool | `true` | Enable authentication on protected routes. |
| `FLASK_SECRET_KEY` | string | `dev-secret-key...` | **Change in production!** Session secret (32+ random chars). |
| `SESSION_LIFETIME_DAYS` | int | `30` | Session cookie lifetime (1-365 days). |
| `BCRYPT_ROUNDS` | int | `12` | Password hashing rounds (10-14). |
| `LOGIN_RATE_LIMIT` | string | `5/minute` | Rate limit for login attempts. |

**Security:** Always set a strong `FLASK_SECRET_KEY` in production. Generate with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Environment-Specific Examples

### Development (local, no Docker)

```bash
FLASK_ENV=development
FLASK_DEBUG=true
VAULT_PATH=./vault
OLLAMA_HOST=http://localhost:11434
AUTH_ENABLED=false
```

### Production (Docker)

```bash
FLASK_ENV=production
FLASK_DEBUG=false
VAULT_PATH=/app/vault
OLLAMA_HOST=http://proxmox.internal:11434
AUTH_ENABLED=true
FLASK_SECRET_KEY=<your-64-char-random-string>
```

### Minimal (just OpenAI)

```bash
OPENAI_API_KEY=sk-...
DEFAULT_MODEL=gpt-4o-mini
VAULT_PATH=/app/vault
```

---

## Validation

Pydantic validates all settings on startup. Invalid values cause immediate errors with clear messages.

**Range constraints:**
- `MAX_CONTEXT_TOKENS`: 1000-128000
- `CHUNK_SIZE`: 100-2000
- `TOP_K`: 1-20
- `PORT`: 1-65535
- `BCRYPT_ROUNDS`: 10-14

**Path handling:**
- String paths are automatically converted to `Path` objects
- `RAG_EXCLUDE_FOLDERS` accepts JSON array (`["a","b"]`) or comma-separated (`a,b`)

---

## See Also

- [AI_CONTEXT.md](../AI_CONTEXT.md) - Agent onboarding with rules and patterns
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design overview
- [DEPLOYMENT.md](DEPLOYMENT.md) - Proxmox/LXC/Docker setup
