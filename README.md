# WebAppChat

**Your self-hosted AI workspace.** WebAppChat integrates cloud and local LLMs with your Obsidian vault, smart home, and task management systems into a single, unified interface.

---

## ⚡ Quick Start

1.  **Access:** [https://your-domain.com](https://your-domain.com) (Production)
2.  **Onboarding:** Read the [Getting Started Guide](docs/GETTING_STARTED.md).
3.  **Local Vault:** Map your Obsidian notes via [WebDAV](docs/GETTING_STARTED.md#📂-webdav-mapping-your-vault).

---

## 🛠️ Key Features

*   **PARA Vault Sync:** Deep integration with Obsidian using PARA organization.
*   **Multi-Model Support:** Seamlessly switch between OpenAI, Claude, and local Ollama.
*   **CLI Proxies:** Use your existing Claude Code, Codex, and Gemini CLI subscriptions.
*   **Voice Control:** Optimized hands-free "Kitchen Mode" using OpenAI Whisper.
*   **RAG Engine:** Semantic search across your entire knowledge base with citations.
*   **Automations:** Built-in sync for Microsoft To Do and Home Assistant controls.
*   **Inbox Sorting:** Automated classification and routing of voice/text captures using Claude.

---

## 📂 Documentation Index

Detailed guides are located in the `docs/` directory:

| Document | Audience | Purpose |
| :--- | :--- | :--- |
| **[INDEX.md](docs/INDEX.md)** | **All** | **The Master Table of Contents** |
| [README.md](docs/README.md) | **All** | **Docs lobby (quick links, system overview).** |
| [GETTING_STARTED.md](docs/GETTING_STARTED.md) | Users | Onboarding, URLs, and common tasks. |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Users | Fixes for connection and sync issues. |
| [OPERATIONS.md](docs/OPERATIONS.md) | Admins | Runbooks, backups, and restarts. |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Admins | Proxmox -> LXC -> Docker environment map. |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Admins | `.env` and configuration settings. |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Devs | Code layers and system design. |
| [API.md](docs/API.md) | Devs | API Endpoint reference. |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Devs | Local dev, tests, standards. |
| [AI_CONTEXT.md](AI_CONTEXT.md) | **Agents** | **Crucial rules for AI coding assistants.** |

---

## 🏗️ Environment

*   **Host:** Proxmox VE
*   **Container:** LXC ${LXC_ID} (Ubuntu)
*   **Runtime:** Docker Compose
*   **Stack:** Python 3.11 (Flask), Gunicorn, SQLite

---
*Last Updated: 2026-01-11 | Version: 1.0*
