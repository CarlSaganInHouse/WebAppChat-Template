# WebAppChat Setup Guide

**Target Audience**: AI coding assistants (Claude Code, Codex, etc.) helping users set up this application.

This document provides structured instructions for deploying WebAppChat. Follow the phases sequentially.

---

## Prerequisites

Before starting, verify the user has:

- [ ] Docker and Docker Compose installed
- [ ] An Obsidian vault (local folder)
- [ ] At least one LLM API key (OpenAI or Anthropic)
- [ ] Basic familiarity with terminal/command line

---

## Phase 1: Clone and Configure Environment

### Step 1.1: Clone Repository

```bash
git clone <repository-url> WebAppChat
cd WebAppChat
```

### Step 1.2: Create Environment File

```bash
cp .env.example .env
```

### Step 1.3: Configure Required Variables

Open `.env` and set these **required** values:

| Variable | Description | How to Get |
|----------|-------------|------------|
| `OPENAI_API_KEY` | OpenAI API key | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | Anthropic API key | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| `VAULT_PATH` | Path to Obsidian vault | User's local path (e.g., `/home/user/Documents/MyVault`) |
| `VAULT_NAME` | Vault name for deep links | Name shown in Obsidian app |

**Example minimal .env:**
```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx
VAULT_PATH=/home/user/Documents/ObsidianVault
VAULT_NAME=MyVault
```

### Step 1.4: Configure Optional Features

Set these only if the user wants these features:

| Feature | Variables Required | Setup Link |
|---------|-------------------|------------|
| **Local Models (Ollama)** | `OLLAMA_HOST=http://localhost:11434` | [ollama.ai](https://ollama.ai) |
| **Microsoft To Do** | `MS_TODO_CLIENT_ID`, `MS_TODO_CLIENT_SECRET`, `MS_TODO_REDIRECT_URI` | See [Microsoft OAuth Setup](#microsoft-oauth-setup) |
| **Home Assistant** | `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN` | Settings → Long-lived access tokens |
| **Voice (TTS/STT)** | Uses `OPENAI_API_KEY` | Already configured if OpenAI key set |

---

## Phase 2: Vault Structure Setup

### Step 2.1: Create Required Folders

The app expects these folders in the vault. Create them if they don't exist:

```
VaultRoot/
├── 00-Inbox/           # Quick captures
├── 60-Calendar/
│   └── Daily/          # Daily notes
└── 90-Meta/
    ├── Templates/      # Note templates
    └── Attachments/    # Image uploads
```

**Commands to create:**
```bash
VAULT="/path/to/vault"  # Replace with actual path
mkdir -p "$VAULT/00-Inbox"
mkdir -p "$VAULT/60-Calendar/Daily"
mkdir -p "$VAULT/90-Meta/Templates"
mkdir -p "$VAULT/90-Meta/Attachments"
```

### Step 2.2: Configure Folder Paths (if different)

If user's vault uses different folder names, update `.env`:

```env
INBOX_FOLDER=00-Inbox
DAILY_NOTES_FOLDER=60-Calendar/Daily
TEMPLATES_FOLDER=90-Meta/Templates
ATTACHMENTS_FOLDER=90-Meta/Attachments
```

---

## Phase 3: Docker Deployment

### Step 3.1: Update docker-compose.yml Paths

Edit `docker-compose.yml` and update the vault mount path:

```yaml
services:
  webchat:
    volumes:
      - ${HOST_VAULT_PATH:-/path/to/vault}:/app/vault  # Update this path
```

Or set in `.env`:
```env
HOST_VAULT_PATH=/home/user/Documents/ObsidianVault
```

### Step 3.2: Build and Start

```bash
docker-compose up -d --build
```

### Step 3.3: Verify Startup

```bash
# Check container is running
docker ps | grep webchat-app

# View logs for errors
docker logs webchat-app --tail 50

# Test the endpoint
curl http://localhost:5000/api/health
```

**Expected output**: Container running, no errors in logs, health check returns OK.

---

## Phase 4: Initial User Setup

### Step 4.1: Create Admin User

```bash
docker exec -it webchat-app python scripts/manage.py create-user admin
```

This will prompt for a password. Save these credentials.

### Step 4.2: Create API Key (Optional)

For programmatic access:

```bash
docker exec -it webchat-app python scripts/manage.py create-api-key "My API Key"
```

### Step 4.3: Access the App

Open browser to: `http://localhost:5000`

Login with the admin credentials created above.

---

## Phase 5: Optional Feature Setup

### Microsoft OAuth Setup

For Microsoft To Do integration:

1. Go to [Azure Portal](https://portal.azure.com/) → App registrations → New registration
2. Name: "WebAppChat"
3. Redirect URI: `http://localhost:5000/auth/microsoft/callback` (Web)
4. After creation, note the **Application (client) ID**
5. Go to Certificates & secrets → New client secret → Copy the **Value**
6. Go to API permissions → Add permission → Microsoft Graph → Delegated:
   - `Tasks.ReadWrite`
   - `User.Read`
7. Update `.env`:
   ```env
   MS_TODO_CLIENT_ID=<application-id>
   MS_TODO_CLIENT_SECRET=<client-secret>
   MS_TODO_REDIRECT_URI=http://localhost:5000/auth/microsoft/callback
   ```
8. Restart: `docker-compose restart webchat`
9. In app: Settings → Connect Microsoft Account

### Home Assistant Setup

1. In Home Assistant: Profile → Long-lived access tokens → Create token
2. Update `.env`:
   ```env
   HOME_ASSISTANT_URL=http://192.168.x.x:8123
   HOME_ASSISTANT_TOKEN=<your-token>
   ```
3. Restart: `docker-compose restart webchat`

### WebDAV Setup (Obsidian Sync)

For syncing Obsidian vault via WebDAV:

1. Generate credentials:
   ```bash
   docker exec -it webchat-app python scripts/generate_webdav_credentials.py MyDevice
   ```
2. Note the generated password
3. In Obsidian, use a WebDAV sync plugin with:
   - URL: `http://localhost:8080/`
   - Username: `MyDevice`
   - Password: (generated password)

---

## Phase 6: Verification Checklist

Run through this checklist to verify setup:

- [ ] **App loads**: `http://localhost:5000` shows login page
- [ ] **Login works**: Can log in with created user
- [ ] **Chat works**: Can send a message and get response
- [ ] **Vault access**: Can create a note via chat ("create a test note")
- [ ] **Model switching**: Can change models in settings dropdown

### Troubleshooting Commands

```bash
# View all logs
docker logs webchat-app -f

# Check environment variables loaded
docker exec webchat-app env | grep -E "(OPENAI|ANTHROPIC|VAULT)"

# Test vault mount
docker exec webchat-app ls -la /app/vault

# Restart fresh
docker-compose down && docker-compose up -d --build
```

---

## Configuration Reference

### Full .env Variable List

```env
# === REQUIRED ===
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-api03-...
VAULT_PATH=/app/vault
VAULT_NAME=MyVault

# === VAULT FOLDERS ===
INBOX_FOLDER=00-Inbox
DAILY_NOTES_FOLDER=60-Calendar/Daily
TEMPLATES_FOLDER=90-Meta/Templates
ATTACHMENTS_FOLDER=90-Meta/Attachments
RAG_EXCLUDE_FOLDERS=["00-Inbox","90-Meta"]

# === LLM SETTINGS ===
DEFAULT_MODEL=gpt-4o-mini
MAX_CONTEXT_TOKENS=8000

# === RAG SETTINGS ===
CHUNK_SIZE=500
EMBEDDING_MODEL=text-embedding-3-small
TOP_K=5

# === LOCAL MODELS (OPTIONAL) ===
OLLAMA_HOST=http://localhost:11434

# === MICROSOFT TODO (OPTIONAL) ===
MS_TODO_CLIENT_ID=
MS_TODO_CLIENT_SECRET=
MS_TODO_REDIRECT_URI=http://localhost:5000/auth/microsoft/callback

# === HOME ASSISTANT (OPTIONAL) ===
HOME_ASSISTANT_URL=http://192.168.x.x:8123
HOME_ASSISTANT_TOKEN=

# === STORAGE ===
USE_SQLITE_CHATS=True
CHAT_DB_PATH=chats.sqlite3
RAG_DB_PATH=rag.sqlite3

# === FLASK ===
FLASK_ENV=production
PORT=5000
SECRET_KEY=<generate-random-string>

# === WEBDAV (OPTIONAL) ===
WEBDAV_ENABLED=true
WEBDAV_PORT=8080
```

---

## Quick Reference for AI Agents

### Key Files
- `app.py` - Flask application entry point
- `config.py` - All settings with Pydantic validation
- `docker-compose.yml` - Container orchestration
- `AI_CONTEXT.md` - Detailed codebase documentation for agents

### Key Commands
```bash
# Start
docker-compose up -d --build

# Stop
docker-compose down

# Logs
docker logs webchat-app -f

# Shell into container
docker exec -it webchat-app bash

# Run tests
docker exec webchat-app pytest tests/ -v
```

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| "Connection refused" on chat | API key invalid | Check `.env` API keys |
| "Vault not found" | Path mismatch | Verify `VAULT_PATH` and docker mount |
| "Permission denied" on vault | Docker volume permissions | Check folder ownership |
| Container won't start | Port conflict | Change `PORT` in `.env` |

---

## Phase 7: Advanced Host Services (Optional)

These features require scripts running **outside** Docker, directly on the host machine. They are entirely optional.

### Overview of Host Services

| Service | Purpose | Schedule |
|---------|---------|----------|
| **CLI Proxies** | Use Claude Code/Codex/Gemini CLI subscriptions via HTTP | Systemd (always on) |
| **Inbox Sorting** | Auto-classify voice/text captures using Claude | Cron (every 15 min) |
| **Daily Notes** | Create daily notes from template | Cron (1 AM) |
| **To Do Sync** | Sync Microsoft To Do to Obsidian | Cron (every 15 min) |

### CLI Proxy Services (systemd)

These allow using existing Claude Code, Codex, or Gemini CLI subscriptions through WebAppChat.

**Requirements**: The respective CLI tools must be installed and authenticated on the host.

#### Step 7.1: Create Proxy Scripts

Create `/root/claude_proxy.py` (and similar for codex/gemini):

```python
#!/usr/bin/env python3
"""Claude Code CLI Proxy - accepts HTTP requests and forwards to CLI"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import json

class ProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = json.loads(self.rfile.read(content_length))

        prompt = post_data.get('prompt', '')
        model = post_data.get('model', 'sonnet')  # opus, sonnet, haiku

        # Call Claude Code CLI
        result = subprocess.run(
            ['claude', '-p', prompt, '--model', model],
            capture_output=True, text=True, timeout=120
        )

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'response': result.stdout,
            'error': result.stderr if result.returncode != 0 else None
        }).encode())

if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 9876), ProxyHandler).serve_forever()
```

#### Step 7.2: Create Systemd Service

Create `/etc/systemd/system/claude-proxy.service`:

```ini
[Unit]
Description=Claude Code CLI Proxy
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /root/claude_proxy.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
systemctl daemon-reload
systemctl enable claude-proxy
systemctl start claude-proxy
```

Repeat for `codex-proxy.service` (port 9877) and `gemini-proxy.service` (port 9878).

#### Step 7.3: Configure Docker Networking

In `docker-compose.yml`, add extra_hosts to allow Docker to reach host services:

```yaml
services:
  webchat:
    extra_hosts:
      - "host.docker.internal:${HOST_IP}"  # Your host's LAN IP
```

### Cron Jobs Setup

#### Inbox Sorting (sort_inbox.py)

Automatically processes captures from `00-Inbox/` using Claude.

1. Create stub at `/root/sort_inbox.py`:
```python
#!/usr/bin/env python3
import subprocess, sys
result = subprocess.run(
    [sys.executable, '/root/WebAppChat/scripts/sort_inbox.py'] + sys.argv[1:],
    cwd='/root/WebAppChat'
)
sys.exit(result.returncode)
```

2. Add to crontab (`crontab -e`):
```
*/15 * * * * /usr/bin/python3 /root/sort_inbox.py >> /var/log/inbox_sort.log 2>&1
```

#### Daily Note Creation

Creates daily notes from template at 1 AM.

1. Create stub at `/root/create_daily_note.py`:
```python
#!/usr/bin/env python3
import subprocess, sys
result = subprocess.run(
    [sys.executable, '/root/WebAppChat/scripts/create_daily_note.py', '--tomorrow'] + sys.argv[1:],
    cwd='/root/WebAppChat'
)
sys.exit(result.returncode)
```

2. Add to crontab:
```
0 1 * * * /usr/bin/python3 /root/create_daily_note.py >> /var/log/daily_note.log 2>&1
```

#### Microsoft To Do Sync

Syncs tasks bidirectionally between Microsoft To Do and Obsidian.

1. Create stub at `/root/sync_todo_to_obsidian.py`:
```python
#!/usr/bin/env python3
import subprocess, sys
result = subprocess.run(
    [sys.executable, '/root/WebAppChat/scripts/sync_todo_to_obsidian.py'] + sys.argv[1:],
    cwd='/root/WebAppChat'
)
sys.exit(result.returncode)
```

2. Add to crontab:
```
*/15 * * * * /usr/bin/python3 /root/sync_todo_to_obsidian.py >> /var/log/todo_sync.log 2>&1
```

### WorldModel Setup (For Inbox Sorting)

The inbox sorting agent uses a WorldModel JSON file for context about your life.

1. Copy example to vault:
```bash
cp docs/WorldModel/WorldModel.example.json /path/to/vault/90-Meta/WorldModel.json
```

2. Edit the file to add your personal entities (people, pets, locations, vocabulary)

3. The sorting agent reads this for entity recognition and routing decisions

---

## Phase 8: Updating from Template

When the template repository receives updates (new features, bug fixes), pull them into your installation.

### Check for Updates

```bash
cd ~/WebAppChat  # or wherever you cloned the repo
git fetch origin
git log HEAD..origin/main --oneline
```

If output is empty, you're up to date. Otherwise, you'll see a list of new commits.

### Pull Updates

```bash
git pull origin main
```

**If you see merge conflicts:** You've modified tracked files locally. Resolve conflicts manually or stash your changes:

```bash
git stash
git pull origin main
git stash pop  # Reapply your local changes
```

### Rebuild and Restart

```bash
docker-compose down
docker-compose up -d --build
```

### Verify

```bash
# Check container is running
docker ps | grep webchat-app

# Check for errors
docker logs webchat-app --tail 50

# Test the app
curl http://localhost:5000/api/health
```

### What's Preserved

Your personal data is **never overwritten** by updates:

| File | Status |
|------|--------|
| `.env` | Gitignored - your settings preserved |
| `webdav_users.json` | Gitignored - your credentials preserved |
| `*.sqlite3` | Gitignored - your data preserved |
| `chats/` | Gitignored - your history preserved |

### If Something Breaks

Roll back to previous state:

```bash
git log --oneline -5  # Find the commit before the update
git reset --hard <previous-commit-hash>
docker-compose up -d --build
```

---

*This document is optimized for AI coding assistants. For human-readable docs, see `docs/GETTING_STARTED.md`.*
