# WebAppChat Setup - Handoff Prompt for Claude Code

**Copy everything below this line and paste it to Claude Code to begin setup.**

---

## Context

I'm setting up **WebAppChat**, a self-hosted AI chat application with Obsidian vault integration. The codebase was shared with me by my brother and is now cloned to my machine.

## Your Task

Help me deploy and configure WebAppChat on my system. Work through the setup phases methodically, and verify each step works before moving on.

## Key Files to Reference

- **`SETUP.md`** - Your primary guide. Read this first. It's structured for AI agents and contains all setup phases.
- **`AI_CONTEXT.md`** - Codebase architecture and rules. Read if you need to understand how the code works.
- **`.env.example`** - All available configuration options with descriptions.
- **`docker-compose.yml`** - Container orchestration config.

## What I Have Ready

- Docker and Docker Compose installed
- An Obsidian vault (I'll tell you the path when you ask)
- API keys for LLM providers (I'll provide when needed)

## How to Work

1. **Start by reading `SETUP.md`** to understand the full process
2. **Work through phases sequentially** - don't skip ahead
3. **Verify each phase works** before proceeding (check logs, test endpoints)
4. **Infer what you can** - examine my system, check existing configs, detect paths
5. **Ask me only when you genuinely need my input**:
   - API keys and secrets (never guess these)
   - My Obsidian vault location
   - Which optional features I want (Microsoft To Do, Home Assistant, etc.)
   - Preferences that affect how I'll use the app
6. **Don't ask about things you can figure out**:
   - Docker/system configuration (just check)
   - Default values that are sensible
   - Technical implementation details

## Optional Features (ask me about these)

The app has several optional integrations. Ask me which ones I want before configuring them:

- **Ollama** - Local LLM models
- **Microsoft To Do** - Task sync (requires Azure app registration)
- **Home Assistant** - Smart home control
- **WebDAV** - Obsidian vault sync from mobile
- **CLI Proxies** - Use Claude Code/Codex/Gemini CLI subscriptions (advanced)
- **Inbox Sorting** - Auto-classify captures with AI (advanced)

## Success Criteria

Setup is complete when:
- [ ] App is running and accessible in browser
- [ ] I can log in with credentials you helped me create
- [ ] I can send a chat message and get an AI response
- [ ] The app can read/write to my Obsidian vault
- [ ] Any optional features I requested are working

## Begin

Start by reading `SETUP.md`, then begin Phase 1. Examine my system to understand what we're working with, and let me know what information you need from me to proceed.
