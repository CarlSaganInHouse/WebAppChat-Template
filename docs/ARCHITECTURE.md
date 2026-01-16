---
title: Architecture Overview
last_verified: 2026-01-16
verified_by: Claude
applies_to: Current codebase
---

# Architecture Overview

WebAppChat is a self-hosted AI chat application with deep integrations for Obsidian, Microsoft To Do, and Home Assistant. It supports multiple LLM providers and features a tool-calling system that allows LLMs to interact with external services.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web Browser                              │
│                    (index.html + JavaScript)                     │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ HTTP/SSE
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Flask Application                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  Routes  │  │ Services │  │Providers │  │    Databases     │ │
│  │          │──│          │──│          │  │                  │ │
│  │ chat_    │  │ llm_     │  │ openai   │  │ chats.sqlite3    │ │
│  │ obsidian │  │ obsidian │  │anthropic │  │ rag.sqlite3      │ │
│  │ rag_     │  │ rag_     │  │ ollama   │  │                  │ │
│  │ voice_   │  │ tool_    │  │          │  │                  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              ┌──────────┐  ┌──────────┐  ┌──────────┐
              │ Obsidian │  │ MS To Do │  │   Home   │
              │  Vault   │  │  (Graph) │  │Assistant │
              └──────────┘  └──────────┘  └──────────┘
```

---

## Layer Architecture

The application follows a clean layered architecture:

```
HTTP Request
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  ROUTES (routes/*.py)                               │
│  - HTTP endpoint handlers                           │
│  - Request validation                               │
│  - Response formatting                              │
│  - Thin wrappers that delegate to services          │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  SERVICES (services/*.py)                           │
│  - Business logic                                   │
│  - Orchestration between components                 │
│  - State management                                 │
│  - The "brain" of the application                   │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  PROVIDERS (providers/*.py)                         │
│  - LLM API adapters                                 │
│  - Common interface for different backends          │
│  - Streaming support                                │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  DATABASE (*_db.py)                                 │
│  - Persistence layer                                │
│  - SQLite for chats, users, RAG                     │
│  - JSON files for legacy chat storage               │
└─────────────────────────────────────────────────────┘
```

---

## Request Flow: Chat Message

Here's how a chat message flows through the system:

```
1. User sends message
   │
   ▼
2. POST /api/chat/ask-stream
   │  (routes/chat_routes.py)
   │
   ▼
3. LLMService.chat_stream()
   │  (services/llm_service.py)
   │  - Builds conversation context
   │  - Selects provider based on model
   │  - Injects system prompt + tools
   │
   ▼
4. Provider.chat_stream()
   │  (providers/*_provider.py)
   │  - Calls external API (OpenAI/Anthropic/Ollama)
   │  - Streams response tokens
   │
   ▼
5. Tool Call Detection
   │  (services/tool_calling_service.py)
   │  - If response contains tool calls:
   │    └─► Execute tools (see Tool Calling Flow)
   │    └─► Continue conversation with results
   │
   ▼
6. SSE Stream to Browser
   │  - Tokens streamed as they arrive
   │  - Final message saved to database
   │
   ▼
7. ChatDatabase.save_message()
   (chat_db.py)
```

---

## Request Flow: Tool Calling

When an LLM decides to use a tool:

```
1. Intent Detection (routes/chat_routes.py)
   │  - message_requires_write_tool() for create/add/update
   │  - message_requires_read_tool() for check/search/find
   │  - Sets write_intent and read_intent flags
   │
   ▼
2. LLM API Call with Enforcement
   │  - OpenAI: tool_choice="required" if intent detected
   │  - Anthropic: Soft enforcement via retry
   │  - RESPONSE STYLE prompt suppresses narration
   │
   ▼
3. LLM Response includes tool_calls
   │  [{"name": "read_note", "arguments": {"file_path": "..."}}]
   │  - If intent detected but no tool_calls: retry with reminder
   │  - Preamble text stripped from context
   │
   ▼
4. ToolCallingService.execute_tools()
   │  (services/tool_calling_service.py)
   │  - Validates tool call against schema
   │  - Routes to appropriate function
   │
   ▼
5. Function Dispatch
   │  ┌─────────────────────────────────────────────┐
   │  │ obsidian_functions.py  → ObsidianService   │
   │  │ microsoft_todo_functions.py → ToDoService  │
   │  │ smarthome_functions.py → Home Assistant API│
   │  │ general_tools.py → Web search, etc.        │
   │  └─────────────────────────────────────────────┘
   │
   ▼
6. Tool Execution
   │  - ObsidianService.read_note() / create_note() / etc.
   │  - Verification if enabled (read-after-write)
   │
   ▼
7. Result Formatting
   │  - Standardized response format
   │  - Success/error status
   │
   ▼
8. Continue Conversation
   │  - Tool results added to context
   │  - LLM generates final response
   │
   ▼
9. Stream to User
```

---

## Key Components

### Routes (`routes/`)

| File | Endpoints | Purpose |
|------|-----------|---------|
| `chat_routes.py` | `/api/chat/*` | Chat, streaming, model switching, inbox |
| `obsidian_routes.py` | `/api/obsidian/*` | Vault operations for web UI |
| `rag_routes.py` | `/api/rag/*` | RAG sources, uploads, sync |
| `voice_routes.py` | `/api/voice/*` | Speech-to-text, text-to-speech |
| `admin_routes.py` | `/api/admin/*` | System status, logs |
| `analytics_routes.py` | `/api/analytics/*` | Usage stats, costs |
| `auth_routes.py` | `/auth/*` | Login, logout, OAuth |

### Services (`services/`)

| File | Responsibility |
|------|----------------|
| `llm_service.py` | **Core orchestrator.** Provider routing, context management, tool execution loops, streaming. |
| `obsidian_service.py` | All vault operations. Path security, daily notes, templates, search. |
| `tool_calling_service.py` | Parses tool calls, validates against schema, executes functions. |
| `rag_service.py` | Document chunking, embedding, semantic search. |
| `conversation_service.py` | Chat history, token limits, message formatting. |
| `storage_service.py` | Unified chat persistence (JSON or SQLite). |
| `cost_tracking_service.py` | Token usage, cost calculation per model. |
| `scheduler_service.py` | Background jobs (RAG sync, etc.). |

### Providers (`providers/`)

All providers implement a common interface for chat and streaming:

| File | Backend | Features |
|------|---------|----------|
| `openai_provider.py` | OpenAI API | GPT-4o, GPT-4-turbo, function calling |
| `anthropic_provider.py` | Anthropic API | Claude 3.5 Sonnet, Claude 3 Opus |
| `ollama_provider.py` | Local Ollama | Llama, Qwen, Mistral, etc. |
| `ollama_mcp_provider.py` | Ollama + MCP | Structured tool calling for local models |
| `embedding_provider.py` | OpenAI | Text embeddings for RAG |

### Function Definitions

| File | Domain | Tools |
|------|--------|-------|
| `obsidian_functions.py` | Vault operations | 20+ tools (read, write, search, daily notes) |
| `microsoft_todo_functions.py` | Task management | create, list, complete, delete tasks |
| `smarthome_functions.py` | Home automation | lights, thermostat, plugs |
| `general_tools.py` | Utilities | web search, calculations |

---

## Agent Modes

The application supports two agent modes (configured via `AGENT_MODE`):

### Structured Mode (Default)

```
- 30+ specific, well-defined tools
- Explicit tool routing based on intent
- Schema validation before execution
- Best for: Reliability, predictable behavior
```

### Autonomous Mode

```
- 5 general-purpose tools
- Permissive system prompts
- LLM has more freedom in tool selection
- Best for: Flexibility, complex multi-step tasks
```

---

## Integrations

### Obsidian Vault

```
┌─────────────────────────────────────────────────────┐
│                  ObsidianService                     │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Daily Notes │  │   Search    │  │  Templates  │  │
│  │             │  │             │  │             │  │
│  │ get_or_     │  │ search_     │  │ create_     │  │
│  │ create_     │  │ notes()     │  │ from_       │  │
│  │ daily_note  │  │             │  │ template()  │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                      │
│  Security: All paths validated via safe_vault_path() │
└─────────────────────────────────────────────────────┘
           │
           ▼
    /app/vault (Docker mount)
           │
           ▼
    /root/obsidian-vault (LXC container)
```

### Microsoft To Do

```
┌─────────────────────────────────────────────────────┐
│              MicrosoftToDoService                    │
│                                                      │
│  - OAuth 2.0 via MSAL                               │
│  - Tokens stored in user_settings table             │
│  - Graph API for task operations                    │
│                                                      │
│  Functions: create_task, get_tasks, complete_task   │
└─────────────────────────────────────────────────────┘
           │
           ▼
    Microsoft Graph API
```

### Home Assistant

```
┌─────────────────────────────────────────────────────┐
│              smarthome_functions.py                  │
│                                                      │
│  - Direct REST API calls                            │
│  - Long-lived access token authentication           │
│                                                      │
│  Functions: control_lights, control_thermostat,     │
│             control_plug, get_device_state          │
└─────────────────────────────────────────────────────┘
           │
           ▼
    Home Assistant API (http://${HOME_ASSISTANT_IP}:8123)
```

---

## Database Schema

### chats.sqlite3

```sql
┌─────────────────────────────────────────────────────┐
│                       users                          │
├─────────────────────────────────────────────────────┤
│ id          INTEGER PRIMARY KEY                     │
│ username    TEXT UNIQUE                             │
│ password_hash TEXT                                  │
│ created_at  TIMESTAMP                               │
└─────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────┐
│                       chats                          │
├─────────────────────────────────────────────────────┤
│ id          TEXT PRIMARY KEY (UUID)                 │
│ user_id     INTEGER → users.id                      │
│ title       TEXT                                    │
│ model       TEXT                                    │
│ created_at  TIMESTAMP                               │
│ updated_at  TIMESTAMP                               │
└─────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────┐
│                      messages                        │
├─────────────────────────────────────────────────────┤
│ id          INTEGER PRIMARY KEY                     │
│ chat_id     TEXT → chats.id                         │
│ role        TEXT (user/assistant/system/tool)       │
│ content     TEXT                                    │
│ tool_calls  TEXT (JSON)                             │
│ created_at  TIMESTAMP                               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                   user_settings                      │
├─────────────────────────────────────────────────────┤
│ id          INTEGER PRIMARY KEY                     │
│ user_id     INTEGER → users.id                      │
│ key         TEXT                                    │
│ value       TEXT                                    │
└─────────────────────────────────────────────────────┘
```

### rag.sqlite3

```sql
┌─────────────────────────────────────────────────────┐
│                      sources                         │
├─────────────────────────────────────────────────────┤
│ id          INTEGER PRIMARY KEY                     │
│ name        TEXT UNIQUE                             │
│ created_at  TIMESTAMP                               │
└─────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────┐
│                       chunks                         │
├─────────────────────────────────────────────────────┤
│ id          INTEGER PRIMARY KEY                     │
│ source_id   INTEGER → sources.id                    │
│ ord         INTEGER (chunk order)                   │
│ text        TEXT                                    │
│ embedding   BLOB (vector as bytes)                  │
└─────────────────────────────────────────────────────┘
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Proxmox Host (${PROXMOX_HOST_IP})                  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              LXC Container ${LXC_ID} (Ubuntu)                    │  │
│  │                                                            │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │                    Docker                            │  │  │
│  │  │                                                      │  │  │
│  │  │  ┌──────────────┐      ┌──────────────┐             │  │  │
│  │  │  │ webchat-app  │      │webdav-server │             │  │  │
│  │  │  │  Port 5000   │      │  Port 8080   │             │  │  │
│  │  │  │              │      │              │             │  │  │
│  │  │  │ Flask +      │      │ WsgiDAV      │             │  │  │
│  │  │  │ Gunicorn     │      │              │             │  │  │
│  │  │  └──────────────┘      └──────────────┘             │  │  │
│  │  │         │                     │                      │  │  │
│  │  │         └──────────┬──────────┘                      │  │  │
│  │  │                    │                                 │  │  │
│  │  │              /app/vault                              │  │  │
│  │  └────────────────────┼─────────────────────────────────┘  │  │
│  │                       │                                    │  │
│  │                       ▼                                    │  │
│  │              /root/obsidian-vault                          │  │
│  │              /root/WebAppChat                              │  │
│  │                                                            │  │
│  │  Systemd Services:                                         │  │
│  │  ├── claude-proxy  (port 9876)                            │  │
│  │  ├── codex-proxy   (port 9877)                            │  │
│  │  └── gemini-proxy  (port 9878)                            │  │
│  │                                                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ Cloudflare Tunnel
           ▼
    https://your-domain.com
```

---

## Security Considerations

### Path Security

All vault file operations go through `safe_vault_path()`:

```python
from utils.vault_security import safe_vault_path

# Prevents path traversal attacks
safe_path = safe_vault_path(vault_root, user_path)
# Raises exception if path escapes vault
```

### Authentication

- Session-based auth with Flask-Login
- Bcrypt password hashing (configurable rounds)
- API key support for integrations
- Rate limiting on login attempts

### Secrets

Never commit to git:
- `.env` (API keys, secrets)
- `webdav_users.json` (bcrypt hashes)
- `*.pem` (SSL certificates)

---

## See Also

- [AI_CONTEXT.md](../AI_CONTEXT.md) - Agent rules and patterns
- [CONFIGURATION.md](CONFIGURATION.md) - All environment variables
- [API.md](API.md) - Endpoint reference
- [DEPLOYMENT.md](DEPLOYMENT.md) - Proxmox/LXC/Docker setup
