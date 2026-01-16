---
title: Deployment Guide
last_verified: 2026-01-11
verified_by: Codex
applies_to: current working tree
---

# Deployment Guide

This guide documents the actual deployment stack: Proxmox host -> LXC container ${LXC_ID} -> Docker containers. It is based on `docker-compose.yml`,
`Dockerfile`, `Dockerfile.webdav`, `.env`, and host scripts under `/root/`.

## Topology (Layers)

1. **Proxmox host**
   - Runs the LXC container (ID 500).
   - Host scripts (examples): `/root/restart_webapp.sh`, `/root/sync_todo.sh`.
2. **LXC container ${LXC_ID}**
   - Runs Docker and Docker Compose.
   - Repo path: `/root/WebAppChat` (bind-mounted from host).
3. **Docker containers**
   - `webchat-app` (Flask app)
   - `webdav-server` (WsgiDAV for Obsidian sync)

## Host File Operations (ZFS Subvolume Warning)

The Proxmox host path `/rpool/data/subvol-${LXC_ID}-disk-0/` is a ZFS subvolume. To avoid permission glitches or stale file handles, perform
file operations **inside LXC ${LXC_ID} whenever possible**. If you must touch `/rpool/...`, stop the containers first.

## Services (Docker Compose)

Defined in `docker-compose.yml`:

- **webchat**
  - Container: `webchat-app`
  - Ports: `5000:5000`
  - Volumes:
    - `.:/app` (repo source)
    - `./chats:/app/chats`
    - `webchat-data:/app/data`
    - `${HOST_VAULT_PATH:-/root}:/app/vault`
    - `/root/.claude:/root/.claude:rw`
    - `/root/.claude.json:/root/.claude.json:rw`
    - `/root/.codex:/root/.codex:rw`
    - `/root/.gemini:/root/.gemini:rw`
  - Env file: `.env`
  - Extra hosts:
    - `host.docker.internal:${LXC_HOST_IP}` (LXC IP for CLI proxies)
    - `proxmox.internal:${PROXMOX_HOST_IP}` (Proxmox host services)

- **webdav**
  - Container: `webdav-server`
  - Ports: `8080:8080`
  - Volumes:
    - `${HOST_VAULT_PATH:-/root}:/app/vault:rw`
    - `${HOST_VAULT_PATH:-/root}/webdav-certs:/app/certs:ro`
    - `./webdav_users.json:/app/webdav_users.json:ro`

## Proxy Layer (Claude/Codex/Gemini)

CLI proxy services run in LXC ${LXC_ID} and are reachable inside Docker via `host.docker.internal`:

- `claude-proxy` -> `http://host.docker.internal:9876/claude`
- `codex-proxy` -> `http://host.docker.internal:9877/codex`
- `gemini-proxy` -> `http://host.docker.internal:9878/gemini`

Restart proxies (from host):

```bash
pct exec ${LXC_ID} -- systemctl restart claude-proxy codex-proxy gemini-proxy
```

## Vault Path Mapping

Current config in `.env`:

- `VAULT_PATH=/app/vault/obsidian-vault`
- `WEBDAV_VAULT_PATH=/app/vault`

With the default mount `HOST_VAULT_PATH=/root`, this resolves to:

- **Host/LXC:** `/root/obsidian-vault`
- **Docker:** `/app/vault/obsidian-vault`

If you change `HOST_VAULT_PATH`, update it for both services.

## Startup and Restart

From the LXC container (500):

```bash
cd /root/WebAppChat
docker compose up -d
```

From the Proxmox host:

```bash
pct exec ${LXC_ID} -- docker restart webchat-app
pct exec ${LXC_ID} -- docker logs -f webchat-app
```

Host helper script:

```bash
/root/restart_webapp.sh
```

## Microsoft To Do Sync (Cron)

Host wrapper script:

```bash
/root/sync_todo.sh
```

This calls inside the container:

```bash
python3 /app/scripts/sync_todo_to_obsidian.py
```

Logs: `/var/log/sync_todo.log` on the host.

## OLLAMA Host Note

`docker-compose.yml` sets:

```
OLLAMA_HOST=http://proxmox.internal:11434
```

This overrides any `OLLAMA_HOST` value in `.env` for the container.

## Entry Point Behavior

The app container entrypoint (`entrypoint.sh`) fixes permissions on `/app` and `/app/vault`, then runs:

```bash
python app.py
```

as user `appuser` (UID 1002).
