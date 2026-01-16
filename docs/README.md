---
title: WebAppChat Documentation
last_verified: 2026-01-11
verified_by: Claude
applies_to: Current codebase
---

# WebAppChat

A self-hosted AI chat application with deep integrations for Obsidian, Microsoft To Do, and Home Assistant. Supports multiple LLM providers (OpenAI, Anthropic, Ollama) and features a tool-calling system that lets LLMs interact with your personal knowledge base.

## Quick Links

| I want to... | Go to |
|--------------|-------|
| Start using the app | [GETTING_STARTED.md](GETTING_STARTED.md) |
| Fix something broken | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Understand the system | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Configure settings | [CONFIGURATION.md](CONFIGURATION.md) |
| Work on the code | [DEVELOPMENT.md](DEVELOPMENT.md) |
| Perform ops tasks | [OPERATIONS.md](OPERATIONS.md) |

## For AI Agents

If you're an AI agent working on this codebase, start with **[AI_CONTEXT.md](../AI_CONTEXT.md)** in the repo root. It contains architecture, patterns, rules, and gotchas optimized for agent consumption.

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Web Browser                          │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTPS (Cloudflare Tunnel)
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Flask Application (Docker)                 │
│                                                         │
│  Chat ─► LLM Service ─► Tool Calling ─► Obsidian Vault │
│                                                         │
│  Providers: OpenAI | Anthropic | Ollama | CLI Proxies  │
└─────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ Obsidian │   │ MS To Do │   │   Home   │
    │  Vault   │   │  (Graph) │   │Assistant │
    └──────────┘   └──────────┘   └──────────┘
```

## Key Features

- **Multi-provider LLM support** - GPT-4o, Claude, Ollama local models, plus CLI proxies for subscription-based access
- **Obsidian integration** - Read, write, search notes; daily notes; templates; PARA folder structure
- **RAG (Retrieval-Augmented Generation)** - Semantic search across your vault with citations
- **Voice interface** - Whisper STT + OpenAI TTS for hands-free "kitchen mode"
- **Tool calling** - 30+ tools for vault operations, task management, smart home control
- **Cost tracking** - Per-chat budgets and usage analytics

## Documentation Map

```
docs/
├── README.md           ← You are here
├── INDEX.md            ← Detailed table of contents
│
├── GETTING_STARTED.md  ← First-time setup and usage
├── TROUBLESHOOTING.md  ← Common issues and fixes
│
├── CONFIGURATION.md    ← All .env settings explained
├── DEPLOYMENT.md       ← Proxmox/LXC/Docker topology
├── OPERATIONS.md       ← Restart, backup, maintenance
│
├── ARCHITECTURE.md     ← System design and data flow
├── API.md              ← Endpoint reference
├── DEVELOPMENT.md      ← Code patterns and testing
│
└── integrations/       ← Deep dives
    ├── microsoft-todo.md
    └── home-assistant.md

AI_CONTEXT.md           ← Agent onboarding (repo root)
Project_Structure.md    ← Code map (repo root)
```

## Access Points

| Service | URL (examples) |
|---------|----------------|
| Web App (External) | `https://<your-domain>` |
| Web App (LAN) | `http://<lxc-host-ip>:5000` |
| WebDAV (Obsidian Sync) | `http://<lxc-host-ip>:8080` |

Local defaults in this environment:

- Web App (External): `https://your-domain.com`
- Web App (LAN): `http://${LXC_HOST_IP}:5000`
- WebDAV (Obsidian Sync): `http://${LXC_HOST_IP}:8080`

## Tech Stack

- **Backend**: Python 3.11, Flask, Gunicorn, SQLite
- **Frontend**: Vanilla JS, SSE streaming
- **Infrastructure**: Proxmox, LXC, Docker
- **LLM Providers**: OpenAI, Anthropic, Ollama, Claude/Codex/Gemini CLI proxies
