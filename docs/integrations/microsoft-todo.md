---
title: Microsoft To Do Integration
last_verified: 2026-01-11
verified_by: Codex
applies_to: current codebase
---

# Microsoft To Do Integration

This integration connects WebAppChat to Microsoft To Do via Microsoft Graph. It supports OAuth login, task CRUD, and sync to an Obsidian markdown file.

## What It Does

- OAuth login for the current WebAppChat user
- Read/write tasks in Microsoft To Do
- Sync open tasks to a vault note (default: `60-Calendar/Task-List.md`)

## Required Environment Variables

Set these in `.env`:

- `WEBCHAT_CLIENT_ID` - Azure app client ID
- `WEBCHAT_CLIENT_SECRET` - Azure app client secret
- `WEBCHAT_REDIRECT_URI` - OAuth callback (e.g., `https://<your-domain>/auth/callback`)
- `TODO_SYNC_PATH` - Output note path (see `docs/CONFIGURATION.md`)

## Azure App Registration Checklist

1. Create an App Registration in Azure Portal.
2. Supported account types: personal accounts or multi-tenant (code uses tenant `common`).
3. Add redirect URIs:
   - `https://<your-domain>/auth/callback`
   - Optional: `http://<lxc-host-ip>:5000/auth/callback` (local dev)
4. Create a client secret and store it in `.env`.
5. Add Microsoft Graph delegated permissions:
   - `Tasks.ReadWrite`
   - `User.Read`
   - `Mail.Send`
6. Save the client ID + secret in `.env` and restart the app.

## OAuth Flow in the App

- Start authorization: `GET /auth/authorize-microsoft`
- Callback: `GET /auth/callback`
- The LLM tool `authorize_microsoft_account` triggers the same flow.

## Token Storage

Tokens are stored per user in `chats.sqlite3`:

- Table: `user_settings`
- Column: `preferences` (JSON)
- Keys: `microsoft_todo_token_cache`, `microsoft_todo_email`

## Sync to Obsidian

- Script: `scripts/sync_todo_to_obsidian.py`
- Host wrapper: `/root/sync_todo.sh`
- Uses `TODO_SYNC_PATH` from settings (default `60-Calendar/Task-List.md`)
- Only incomplete tasks are written

## Troubleshooting

- Missing OAuth configuration: check `WEBCHAT_CLIENT_ID/SECRET` in `.env`.
- Redirect URI mismatch: ensure Azure app redirect matches `WEBCHAT_REDIRECT_URI`.
- No token cache: reauthorize via `/auth/authorize-microsoft`.
