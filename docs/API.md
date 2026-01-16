---
title: API Reference
last_verified: 2026-01-11
verified_by: Claude
applies_to: routes/*.py, auth_routes.py
---

# API Reference

Complete endpoint reference for WebAppChat. All endpoints return JSON unless otherwise noted.

---

## Base URLs

| Environment | Base URL |
|-------------|----------|
| Production | `https://your-domain.com` |
| Local Dev | `http://localhost:5000` |
| Docker Internal | `http://webchat-app:5000` |

---

## Authentication

Most endpoints require authentication via session cookie or API key.

### Session Authentication

Login at `/auth/login` to receive a session cookie. The cookie is automatically sent with subsequent requests.

### API Key Authentication

Include API key in request header:

```http
X-API-Key: your-api-key-here
```

Or as query parameter (less secure):

```
/api/endpoint?api_key=your-api-key-here
```

---

## Chat Endpoints

Base path: `/` (chat_routes.py blueprint)

### Pages

#### `GET /`

Returns the main chat interface HTML page.

**Response:** HTML page

---

### Chat CRUD

#### `POST /new-chat`

Create a new chat session.

**Request Body:**
```json
{
  "title": "Optional chat title"
}
```

**Response:**
```json
{
  "id": "abc123",
  "title": "New chat",
  "created_at": "2026-01-11T10:30:00Z",
  "messages": []
}
```

---

#### `GET /chats`

List all chats for the current user.

**Response:**
```json
[
  {
    "id": "abc123",
    "title": "My Chat",
    "created_at": "2026-01-11T10:30:00Z",
    "updated_at": "2026-01-11T10:35:00Z"
  }
]
```

---

#### `GET /chat/<cid>`

Get a specific chat with all messages.

**Path Parameters:**
- `cid` (string): Chat ID

**Response:**
```json
{
  "id": "abc123",
  "title": "My Chat",
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ],
  "meta": {
    "budget_usd": 1.00,
    "spent_usd": 0.05
  }
}
```

**Errors:**
- `404`: Chat not found

---

#### `POST /chat/<cid>/rename`

Rename a chat.

**Request Body:**
```json
{
  "title": "New Title"
}
```

**Response:**
```json
{
  "ok": true,
  "title": "New Title"
}
```

---

#### `DELETE /chat/<cid>`

Delete a chat permanently.

**Response:**
```json
{
  "ok": true
}
```

---

#### `POST /chat/<cid>/delete`

Delete a chat (POST alternative for clients that don't support DELETE).

**Response:** Same as DELETE

---

### Chat Archive

#### `POST /chat/<cid>/archive`

Archive a chat (soft delete).

**Response:**
```json
{
  "ok": true
}
```

---

#### `POST /chat/<cid>/unarchive`

Restore a chat from archive.

**Response:**
```json
{
  "ok": true
}
```

---

#### `GET /chats/archived`

List all archived chats.

**Response:** Same format as `GET /chats`

---

#### `POST /chats/bulk-archive`

Archive multiple chats at once.

**Request Body:**
```json
{
  "chatIds": ["abc123", "def456"]
}
```

**Response:**
```json
{
  "ok": true,
  "archived": 2,
  "failed": 0
}
```

---

#### `POST /chats/bulk-unarchive`

Unarchive multiple chats at once.

**Request Body:**
```json
{
  "chatIds": ["abc123", "def456"]
}
```

---

### Chat Settings

#### `POST /chat/<cid>/set-model`

Pin a specific model to a chat.

**Request Body:**
```json
{
  "model": "gpt-4o"
}
```

**Response:**
```json
{
  "ok": true,
  "pinned_model": "gpt-4o"
}
```

---

#### `POST /chat/<cid>/budget`

Set a spending budget for a chat.

**Request Body:**
```json
{
  "budget": 5.00
}
```

**Response:**
```json
{
  "ok": true,
  "budget": 5.00
}
```

---

#### `GET /chat/<cid>/meta`

Get chat metadata (budget, spending, etc.).

**Response:**
```json
{
  "meta": {
    "budget_usd": 5.00,
    "spent_usd": 1.23,
    "pinned_model": "gpt-4o"
  }
}
```

---

#### `GET /chat/<cid>/mode`

Get the chat mode (agentic or chat).

**Response:**
```json
{
  "mode": "agentic"
}
```

---

#### `POST /chat/<cid>/mode`

Set the chat mode.

**Request Body:**
```json
{
  "mode": "chat"
}
```

**Values:**
- `agentic`: Full tool access, vault operations enabled
- `chat`: Conversation only, no tool calls

**Response:**
```json
{
  "success": true,
  "mode": "chat"
}
```

---

### Chat Search & Tags

#### `GET /chats/search`

Search across all chat content.

**Query Parameters:**
- `q` (required): Search query
- `limit` (optional, default 50): Max results

**Response:**
```json
{
  "query": "obsidian",
  "count": 3,
  "results": [
    {
      "chat_id": "abc123",
      "title": "Note Discussion",
      "matches": [
        {"type": "user", "role": "user", "snippet": "...obsidian vault..."}
      ]
    }
  ]
}
```

---

#### `POST /chat/<cid>/tags`

Set tags for a chat.

**Request Body:**
```json
{
  "tags": ["Work", "Research", "AI"]
}
```

**Response:**
```json
{
  "ok": true,
  "tags": ["Work", "Research", "AI"]
}
```

---

#### `GET /tags`

Get all unique tags with usage counts.

**Response:**
```json
{
  "tags": [
    {"name": "Work", "count": 15},
    {"name": "Research", "count": 8}
  ]
}
```

---

#### `GET /chats/by-tag/<tag>`

Get all chats with a specific tag.

**Response:**
```json
{
  "tag": "Work",
  "count": 15,
  "chats": [
    {
      "id": "abc123",
      "title": "Project Notes",
      "tags": ["Work", "AI"]
    }
  ]
}
```

---

### Chat Export

#### `GET /chat/<cid>/export.md`

Export a chat as Markdown file.

**Response:** `text/markdown` file download

---

### Chat Completion

#### `POST /ask`

Main chat completion endpoint (non-streaming).

**Request Body:**
```json
{
  "prompt": "Your message here",
  "chatId": "abc123",
  "model": "gpt-4o",
  "temperature": 0.7,
  "system": "Optional system prompt override",
  "useRag": true,
  "topK": 5,
  "presetId": "1",
  "chatMode": "agentic",
  "debugToolCalls": false,
  "image": "base64-encoded-image",
  "imageType": "image/png",
  "imageName": "screenshot.png"
}
```

**Response:**
```json
{
  "chatId": "abc123",
  "text": "Assistant response here",
  "usage": {
    "in_tokens": 150,
    "out_tokens": 200,
    "cost_total": 0.0035
  },
  "resolved": {
    "model": "gpt-4o",
    "temperature": 0.7,
    "rag": true,
    "topK": 5,
    "presetId": "1",
    "chatMode": "agentic"
  },
  "citations": [
    {
      "source": "vault:Notes/project.md",
      "chunk_id": 3,
      "score": 0.89,
      "snippet": "Relevant context...",
      "obsidian_link": "obsidian://open?vault=..."
    }
  ]
}
```

**Errors:**
- `400`: Empty prompt
- `402`: Budget exceeded
- `404`: Chat not found
- `500`: LLM error

---

#### `POST /ask-stream`

Streaming chat completion via Server-Sent Events (SSE).

**Request Body:** Same as `/ask`

**Response:** `text/event-stream`

**Event Types:**
```
data: {"type": "start", "model": "gpt-4o", "chatMode": "agentic"}

data: {"type": "thinking_start"}
data: {"type": "thinking_chunk", "content": "Let me think..."}
data: {"type": "thinking_complete", "thinking": "Full thinking content"}

data: {"type": "chunk", "content": "Hello", "full_text": "Hello"}
data: {"type": "chunk", "content": " there", "full_text": "Hello there"}

data: {"type": "complete", "chatId": "abc123", "full_text": "Hello there", "usage": {...}}

data: {"type": "error", "error": "Error message"}
```

---

### CLI Proxy Endpoints

#### `POST /ask-claude-code`

Execute prompt via Claude Code CLI proxy (uses Max subscription).

**Request Body:**
```json
{
  "prompt": "Your request",
  "chatId": "abc123",
  "model": "claude-code-sonnet",
  "timeout": 300,
  "allowedTools": "Read,Write,Edit,Bash,Glob,Grep",
  "workDir": "/root/obsidian-vault"
}
```

**Response:**
```json
{
  "chatId": "abc123",
  "text": "Claude Code response",
  "model": "claude-code",
  "elapsed_seconds": 12.5,
  "usage": {
    "note": "Uses Max subscription (not API billing)"
  }
}
```

**Errors:**
- `408`: Timeout
- `503`: Proxy service unavailable

---

#### `POST /ask-codex`

Execute prompt via OpenAI Codex CLI proxy (uses ChatGPT Plus/Pro).

**Request Body:**
```json
{
  "prompt": "Your request",
  "chatId": "abc123",
  "model": "codex-gpt52",
  "timeout": 300,
  "reasoning": "medium",
  "workDir": "/root/obsidian-vault"
}
```

**Reasoning Levels:** `low`, `medium`, `high`

**Response:** Similar to Claude Code

---

#### `POST /ask-gemini-cli`

Execute prompt via Gemini CLI proxy (uses free tier).

**Request Body:**
```json
{
  "prompt": "Your request",
  "chatId": "abc123",
  "model": "gemini-cli-flash",
  "timeout": 300,
  "workDir": "/root/obsidian-vault"
}
```

**Response:**
```json
{
  "chatId": "abc123",
  "text": "Gemini response",
  "model": "gemini-cli",
  "elapsed_seconds": 8.2,
  "usage": {
    "note": "Uses Google Login free tier (60 req/min, 1000/day)"
  }
}
```

---

### Inbox & Image Upload

#### `POST /save-to-inbox`

Save quick capture to inbox folder.

**JSON Request:**
```json
{
  "text": "Quick note content",
  "source": "voice"
}
```

**Multipart Request (with image):**
- `text`: Note content
- `source` (optional): Capture source (`voice`, `text`, etc.) - included in frontmatter
- `image`: Image file

**Response:**
```json
{
  "success": true,
  "message": "Saved to inbox",
  "path": "00-Inbox/2026-01-11_103000_a1b2.md",
  "timestamp": "2026-01-11 10:30",
  "has_image": false
}
```

**Generated File Frontmatter:**
```yaml
---
captured: 2026-01-11 10:30:00
type: inbox-capture
source: voice
---
```

The `source` field helps the inbox sorting agent distinguish voice captures (which may have transcription errors) from typed text.

---

#### `POST /upload-image`

Upload image to vault's Attachments folder.

**Multipart Request:**
- `file`: Image file (PNG, JPEG, GIF, WebP, SVG, BMP)
- `filename` (optional): Custom filename
- `embed_in_note` (optional): Note path to embed image in
- `section` (optional): Section name within note

**Response:**
```json
{
  "ok": true,
  "path": "90-Meta/Attachments/image_20260111_103000.png",
  "filename": "image_20260111_103000.png",
  "markdown": "![[image_20260111_103000.png]]",
  "size_bytes": 45678,
  "embedded_in": "Notes/project.md"
}
```

---

## Obsidian Endpoints

Base path: `/obsidian` (obsidian_routes.py blueprint)

#### `POST /obsidian/append-daily`

Append content to today's daily note.

**Request Body:**
```json
{
  "content": "Note content to append",
  "section": "Quick Captures"
}
```

**Response:**
```json
{
  "success": true,
  "path": "60-Calendar/Daily/2026-01-11.md"
}
```

---

#### `POST /obsidian/create-note`

Create a new note in the vault.

**Request Body:**
```json
{
  "content": "Note content",
  "destination": "30-Resources",
  "filename": "my-note.md",
  "mode": "create"
}
```

**Mode Values:**
- `create`: Fail if file exists
- `append`: Append to existing file
- `overwrite`: Replace existing file

**Response:**
```json
{
  "success": true,
  "path": "30-Resources/my-note.md"
}
```

---

#### `GET /obsidian/daily/<date_str>`
#### `GET /obsidian/daily`

Read a daily note (defaults to today).

**Path Parameters:**
- `date_str` (optional): Date in YYYY-MM-DD format

**Response:**
```json
{
  "success": true,
  "path": "60-Calendar/Daily/2026-01-11.md",
  "content": "# Daily Note\n\n..."
}
```

---

#### `GET /obsidian/structure`

Get vault folder structure.

**Response:**
```json
{
  "success": true,
  "folders": {
    "00-Inbox": {"files": 5},
    "30-Resources": {"files": 12, "subfolders": ["AI", "Homelab"]}
  }
}
```

---

## RAG Endpoints

Base path: `/api/rag` (rag_routes.py blueprint)

### Presets

#### `GET /presets`

List all presets.

**Response:**
```json
[
  {
    "id": 1,
    "label": "Research Mode",
    "system": "You are a research assistant...",
    "temperature": 0.3
  }
]
```

---

#### `GET /presets/<pid>`

Get a specific preset.

---

#### `POST /presets`

Create a new preset.

**Request Body:**
```json
{
  "label": "Research Mode",
  "system": "You are a research assistant...",
  "temperature": 0.3
}
```

**Response:**
```json
{
  "id": 2
}
```

---

#### `PUT /presets/<pid>`

Update a preset.

---

#### `DELETE /presets/<pid>`

Delete a preset.

---

### RAG Documents

#### `POST /upload`

Upload text to RAG database.

**Request Body:**
```json
{
  "name": "My Document",
  "text": "Document content here..."
}
```

**Response:**
```json
{
  "ok": true,
  "chunks": 5
}
```

---

#### `POST /upload-pdf`

Upload PDF to RAG database.

**Multipart Request:**
- `file`: PDF file
- `name` (optional): Source name

**Response:**
```json
{
  "ok": true,
  "chunks": 15
}
```

---

#### `GET /sources`

List all RAG sources.

**Response:**
```json
[
  {
    "id": 1,
    "name": "vault:Notes/project.md",
    "chunk_count": 5,
    "created_at": "2026-01-11T10:30:00Z"
  }
]
```

---

#### `POST /sources/delete`

Delete a RAG source.

**Request Body:**
```json
{
  "id": 1
}
```

---

#### `GET /chunk`

Get a specific chunk by source and ordinal.

**Query Parameters:**
- `source`: Source name
- `ord`: Chunk ordinal number

**Response:**
```json
{
  "ok": true,
  "source": "vault:Notes/project.md",
  "ord": 3,
  "text": "Chunk content..."
}
```

---

### RAG Sync

#### `GET /rag-sync-status`

Get RAG auto-sync status.

**Response:**
```json
{
  "enabled": true,
  "running": true,
  "interval_minutes": 15,
  "last_sync": "2026-01-11T10:15:00Z",
  "last_sync_duration_seconds": 12.5,
  "files_synced": 45,
  "errors": null,
  "next_sync": "2026-01-11T10:30:00Z"
}
```

---

#### `POST /obsidian/sync-to-rag`

Manually sync vault to RAG database.

**Response:**
```json
{
  "success": true,
  "synced": 45,
  "skipped": 10,
  "errors": 0,
  "files": [
    {"name": "Notes/project.md", "chunks": 5}
  ],
  "error_details": []
}
```

---

## Voice Endpoints

Base path: `/voice` (voice_routes.py blueprint)

#### `POST /voice/process`

Full voice pipeline: STT -> LLM -> TTS.

**Multipart Request:**
- `audio`: WAV file (16kHz, 16-bit, mono recommended)
- `session_id` (optional): Session ID for continuity
- `model` (optional): LLM model override
- `use_rag` (optional, default true): Enable RAG

**Response:** `audio/mpeg` (MP3 binary)

**Response Headers:**
- `X-Session-Id`: Session ID for follow-up requests
- `X-Transcription`: What was heard
- `X-STT-Cost`: Whisper cost
- `X-LLM-Cost`: LLM cost
- `X-TTS-Cost`: TTS cost
- `X-Total-Cost`: Combined cost

---

#### `POST /voice/transcribe`

Speech-to-text only.

**Multipart Request:**
- `audio`: WAV file

**Response:**
```json
{
  "text": "Transcribed text here",
  "usage": {
    "model": "whisper-1",
    "estimated_duration_seconds": 5.2,
    "estimated_cost": 0.00052
  }
}
```

---

#### `POST /voice/tts`

Text-to-speech only.

**Request Body:**
```json
{
  "text": "Text to synthesize",
  "voice": "alloy"
}
```

**Available Voices:** `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`

**Response:** `audio/mpeg` (MP3 binary)

**Response Headers:**
- `X-Voice`: Voice used
- `X-Character-Count`: Characters synthesized
- `X-Estimated-Cost`: TTS cost

---

#### `GET /voice/status`

Voice service health check.

**Response:**
```json
{
  "enabled": true,
  "whisper_model": "whisper-1",
  "tts_model": "tts-1",
  "tts_voice": "alloy",
  "voice_chat_prefix": "Kitchen Voice",
  "voice_default_model": "gpt-4o-mini",
  "max_audio_mb": 10,
  "openai_configured": true
}
```

---

## Admin Endpoints

Base path: `/` (admin_routes.py blueprint)

#### `GET /models`

Get list of available models with metadata.

**Response:**
```json
{
  "models": [
    {
      "id": "gpt-4o",
      "name": "GPT-4o",
      "provider": "openai",
      "in_price": 5.0,
      "out_price": 15.0,
      "context_window": 128000
    }
  ],
  "grouped": {
    "OpenAI": ["gpt-4o", "gpt-4o-mini"],
    "Anthropic": ["claude-3-5-sonnet"],
    "Local": ["qwen2.5:3b", "llama3.2:3b"]
  },
  "default": "gpt-4o-mini"
}
```

---

#### `GET /ollama-status`

Get Ollama model loading status.

**Response:**
```json
{
  "status": "ok",
  "models": [
    {
      "name": "qwen2.5:3b",
      "loaded": true,
      "size": "5.9 GB",
      "until": "2 minutes from now"
    }
  ],
  "total_loaded": 1
}
```

---

#### `GET /list-models`

List available Ollama models.

**Response:**
```json
{
  "success": true,
  "models": ["qwen2.5:3b", "llama3.2:3b", "mistral:7b"],
  "count": 3
}
```

---

#### `GET /debug/tool-call-stats`

Get tool call observability metrics.

**Response:**
```json
{
  "total_calls": 150,
  "by_function": {
    "read_note": 45,
    "search_vault": 32,
    "create_note": 18
  },
  "average_duration_ms": 125
}
```

---

#### `GET /_debug_env`

Debug environment info (disabled by default).

**Config:** Set `ALLOW_DEBUG_ENDPOINT=true` to enable.

---

## Analytics Endpoints

Base path: `/api/analytics` (analytics_routes.py blueprint)

#### `GET /analytics/usage`

Overall usage statistics.

**Query Parameters:**
- `start_date` (optional): YYYY-MM-DD
- `end_date` (optional): YYYY-MM-DD

**Response:**
```json
{
  "total_chats": 150,
  "total_messages": 2500,
  "total_spend_usd": 45.67,
  "top_tags": [
    {"tag": "Work", "chat_count": 25, "message_count": 500}
  ],
  "model_mix": {
    "gpt-4o": 1500,
    "gpt-4o-mini": 800
  },
  "chats_over_budget": []
}
```

---

#### `GET /analytics/tokens`

Token usage by model.

**Response:**
```json
{
  "by_model": {
    "gpt-4o": {
      "in_tokens": 500000,
      "out_tokens": 300000,
      "cost_usd": 35.50,
      "message_count": 1500
    }
  }
}
```

---

#### `GET /analytics/daily`

Daily message counts and spending.

**Response:**
```json
{
  "daily": [
    {
      "date": "2026-01-10",
      "message_count": 50,
      "chat_count": 5,
      "tokens": 25000,
      "cost_usd": 1.25
    }
  ]
}
```

---

#### `GET /analytics/tags`

Usage breakdown by tag.

**Response:**
```json
{
  "by_tag": {
    "Work": {
      "chat_count": 25,
      "message_count": 500,
      "tokens": 250000,
      "cost_usd": 12.50
    }
  }
}
```

---

#### `GET /total-usage`

Get total spend from usage log.

**Response:**
```json
{
  "total_usd": 45.67
}
```

---

## Auth Endpoints

Base path: `/auth` (auth_routes.py blueprint)

#### `GET /auth/login`
#### `POST /auth/login`

Login page and handler.

**POST Request (form-encoded):**
- `username`: Username
- `password`: Password
- `remember_me` (optional): "on" for persistent session

**Success:** Redirect to `/` or `next` URL
**Failure:** 401 with error message

---

#### `GET /auth/logout`
#### `POST /auth/logout`

Logout and destroy session.

**Response:** Redirect to `/auth/login`

---

#### `GET /auth/api-keys`
#### `POST /auth/api-keys`

API key management page.

**POST Request (form-encoded):**
- `label`: Key description

**Response:** HTML page with new key displayed (key shown only once)

---

#### `POST /auth/api-keys/<key_id>/revoke`

Revoke an API key.

**Response:** Redirect or JSON based on Accept header

---

#### `GET /auth/settings`
#### `POST /auth/settings`

User settings page.

**POST Request (form-encoded):**
- `vault_path`: Custom vault path
- `shared_paths`: Comma-separated paths
- `rag_collection`: RAG collection name

---

#### `GET /auth/authorize-microsoft`

Initiate Microsoft To Do OAuth flow.

**Response:** HTML page with JavaScript redirect to Microsoft login

---

#### `GET /auth/callback`

Microsoft OAuth callback handler.

**Query Parameters (from Microsoft):**
- `code`: Authorization code
- `error`: Error code (if failed)
- `error_description`: Error details

**Response:** HTML page showing success or failure

---

## Error Responses

All endpoints return consistent error format:

```json
{
  "error": "error_code_here",
  "detail": "Human-readable description"
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `empty_prompt` | 400 | No prompt provided |
| `chat_not_found` | 404 | Chat ID doesn't exist |
| `budget_exceeded` | 402 | Chat budget limit reached |
| `voice_disabled` | 503 | Voice features disabled |
| `analytics_requires_sqlite` | 400 | Analytics needs SQLite storage |
| `invalid_wav` | 400 | Invalid audio format |
| `audio_too_large` | 400 | Audio exceeds size limit |

---

## Rate Limiting

Default rate limits (configurable via `RATE_LIMIT_*` env vars):

| Endpoint Pattern | Limit |
|-----------------|-------|
| `/ask` | 20/minute |
| All others | 200/day, 50/hour |

Rate limit headers are included in responses:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - System design overview
- [CONFIGURATION.md](CONFIGURATION.md) - Environment variables
- [AI_CONTEXT.md](../AI_CONTEXT.md) - Agent onboarding
