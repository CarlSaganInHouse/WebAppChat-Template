---
title: Operations Runbook
last_verified: 2026-01-15
verified_by: Claude
applies_to: current working tree
---

# Operations Runbook

This is the day-to-day ops guide for running WebAppChat. It focuses on the live stack:
Proxmox host -> LXC container ${LXC_ID} -> Docker containers (`webchat-app`, `webdav-server`).

## Where to Run Commands

- **Proxmox host**: use `pct exec ${LXC_ID} -- ...` to run inside LXC ${LXC_ID}.
- **LXC ${LXC_ID}**: run Docker/Docker Compose commands directly.
- **Docker container**: use `docker exec webchat-app ...` for app-level commands.

Note: Avoid direct edits under `/rpool/data/subvol-${LXC_ID}-disk-0/` while containers are running. Prefer file operations inside LXC ${LXC_ID}.

## Start / Stop / Restart

From LXC ${LXC_ID}:

```bash
cd /root/WebAppChat
docker compose up -d
docker compose restart webchat-app
docker compose restart webdav-server
```

From Proxmox host:

```bash
pct exec ${LXC_ID} -- docker restart webchat-app
pct exec ${LXC_ID} -- docker restart webdav-server
```

Host helper:

```bash
/root/restart_webapp.sh
```

## Logs

Container logs:

```bash
docker logs webchat-app --tail 100 -f
docker logs webdav-server --tail 100 -f
```

RAG sync log (inside repo):

```
logs/rag_sync.log
```

If the file or directory is missing, it will be created on the first sync. An empty `logs/` directory is normal after a fresh setup.

Microsoft To Do sync log (host):

```
/var/log/sync_todo.log
```

## Configuration Changes

After editing `.env`, restart the container:

```bash
docker restart webchat-app
```

Note: `docker-compose.yml` sets `OLLAMA_HOST` directly for the container, overriding `.env`.

## WebDAV Credentials

Generate/rotate credentials:

```bash
python scripts/generate_webdav_credentials.py <device_name>
```

Then restart WebDAV:

```bash
docker restart webdav-server
```

## Proxy Health Checks (Claude/Codex/Gemini)

Service status (LXC):

```bash
# From Proxmox host
pct exec ${LXC_ID} -- systemctl status claude-proxy codex-proxy gemini-proxy
```

Run from inside the app container to verify the CLI proxies are reachable:

```bash
docker exec webchat-app curl -sS http://host.docker.internal:9876/claude \
  -H "Content-Type: application/json" \
  -d '{"prompt":"ping","timeout":10}'

docker exec webchat-app curl -sS http://host.docker.internal:9877/codex \
  -H "Content-Type: application/json" \
  -d '{"prompt":"ping","timeout":10}'

docker exec webchat-app curl -sS http://host.docker.internal:9878/gemini \
  -H "Content-Type: application/json" \
  -d '{"prompt":"ping","timeout":10}'
```

Expected response (JSON):

```json
{"text":"...","stderr":null,"exit_code":0}
```

If these fail, restart the proxies:

```bash
pct exec ${LXC_ID} -- systemctl restart claude-proxy codex-proxy gemini-proxy
```

## RAG Sync

Check auto-sync status:

```
GET /rag-sync-status
```

Trigger a manual sync:

```
POST /obsidian/sync-to-rag
```

## Database Maintenance

Databases:

- `/app/chats.sqlite3` (chat history, users, settings)
- `/app/rag.sqlite3` (RAG embeddings)

Recommended backup (stop app first):

```bash
pct exec ${LXC_ID} -- docker stop webchat-app
pct exec ${LXC_ID} -- bash -c 'mkdir -p /root/WebAppChat/_archive_2026_01_11/db_backups'
pct exec ${LXC_ID} -- bash -c 'cp /root/WebAppChat/chats.sqlite3 /root/WebAppChat/_archive_2026_01_11/db_backups/chats.sqlite3.$(date +%F)'
pct exec ${LXC_ID} -- bash -c 'cp /root/WebAppChat/rag.sqlite3 /root/WebAppChat/_archive_2026_01_11/db_backups/rag.sqlite3.$(date +%F)'
pct exec ${LXC_ID} -- docker start webchat-app
```

Optional VACUUM (maintenance window):

```bash
pct exec ${LXC_ID} -- docker exec webchat-app python3 - <<'PY'
import sqlite3
for path in ("/app/chats.sqlite3", "/app/rag.sqlite3"):
    conn = sqlite3.connect(path)
    conn.execute("VACUUM")
    conn.close()
print("VACUUM complete")
PY
```

## Obsidian Vault Backups

Automated hourly backups protect the vault from accidental deletion, corruption, or unintended changes by AI agents.

### Backup System Overview

| Component | Location |
|-----------|----------|
| Backup script | `/storage/backups/scripts/backup-obsidian-vault.sh` |
| Restore script | `/storage/backups/scripts/restore-obsidian-vault.sh` |
| Backup storage | `/storage/backups/obsidian-vault-automated/` |
| Log file | `/var/log/obsidian-vault-backup.log` |
| Schedule | Hourly at minute 0 (cron on Proxmox host) |

### Retention Policy (8 weeks)

- **24 hourly** backups - restore to any hour in the last day
- **7 daily** backups - restore to any day in the last week
- **8 weekly** backups - restore to any week in the last 2 months

Storage is efficient (~50-100MB total) because rsync uses hard links for unchanged files.

### List Available Backups

```bash
/storage/backups/scripts/restore-obsidian-vault.sh --list
```

### Preview a Restore

Shows what files differ between backup and current vault:

```bash
/storage/backups/scripts/restore-obsidian-vault.sh --preview daily/2026-01-14
```

### Restore from Backup

Creates a safety backup of current state before restoring:

```bash
/storage/backups/scripts/restore-obsidian-vault.sh --restore weekly/2026-W02
```

### Check Backup Logs

```bash
tail -50 /var/log/obsidian-vault-backup.log
```

### Manual Backup

Trigger an immediate backup outside the hourly schedule:

```bash
/storage/backups/scripts/backup-obsidian-vault.sh
```

## Proxmox Backups (Containers & VMs)

Full container/VM backups protect against OS corruption, failed updates, or complete data loss.

### Backup Schedule

| Job | Schedule | Targets | Retention |
|-----|----------|---------|-----------|
| weekly-full | Sunday 2:00 AM | All containers & VMs | 4 weeks |
| daily-critical | Daily 2:30 AM | 500, 502, 503 | 7 daily + 4 weekly |

Backups stored at: `/storage/backups/proxmox-vzdump/dump/`

### ZFS Snapshots

Lightweight point-in-time snapshots for quick rollback.

| Schedule | Retention | Use Case |
|----------|-----------|----------|
| Hourly (minute 15) | 24 snapshots | "I broke something an hour ago" |
| Daily (3:00 AM) | 7 snapshots | "I need yesterday's version" |

### List vzdump Backups

```bash
ls -lh /storage/backups/proxmox-vzdump/dump/
```

### List ZFS Snapshots

```bash
/storage/backups/scripts/zfs-snapshot.sh --list
```

### Restore Container from vzdump

```bash
# List available backups
ls /storage/backups/proxmox-vzdump/dump/

# Restore container (DESTRUCTIVE - replaces existing)
pct restore 500 /storage/backups/proxmox-vzdump/dump/vzdump-lxc-500-2026_01_15-13_17_53.tar.zst --storage local-zfs

# Or restore to a new VMID
pct restore 599 /storage/backups/proxmox-vzdump/dump/vzdump-lxc-500-2026_01_15-13_17_53.tar.zst --storage local-zfs
```

### Restore VM from vzdump

```bash
qmrestore /storage/backups/proxmox-vzdump/dump/vzdump-qemu-9000-2026_01_15.vma.zst 9000 --storage local-zfs
```

### Rollback ZFS Snapshot

```bash
# List snapshots for a container
zfs list -t snapshot rpool/data/subvol-${LXC_ID}-disk-0

# STOP the container first
pct stop 500

# Rollback to snapshot (DESTRUCTIVE - loses all changes since snapshot)
zfs rollback rpool/data/subvol-${LXC_ID}-disk-0@autosnap_hourly_2026-01-15_12-15

# Start container
pct start 500
```

### Clone from ZFS Snapshot (Non-destructive)

If you want to inspect a snapshot without affecting the running container:

```bash
# Clone snapshot to temporary dataset
zfs clone rpool/data/subvol-${LXC_ID}-disk-0@autosnap_hourly_2026-01-15_12-15 rpool/data/snapshot-inspection

# Browse the files
ls /rpool/data/snapshot-inspection/

# Clean up when done
zfs destroy rpool/data/snapshot-inspection
```

### Manual Backup Commands

```bash
# Backup single container now
vzdump 500 --storage storage-backups --compress zstd --mode snapshot

# Backup all containers
vzdump 500 501 502 503 --storage storage-backups --compress zstd --mode snapshot

# Create ZFS snapshot manually
/storage/backups/scripts/zfs-snapshot.sh hourly
```

### Check Backup Logs

```bash
# vzdump logs (Proxmox task log)
cat /var/log/pve/tasks/active

# ZFS snapshot logs
tail -50 /var/log/zfs-snapshot.log
```

## Microsoft To Do Sync

Host wrapper (cron or manual):

```bash
/root/sync_todo.sh
```

This runs inside the container:

```bash
python3 /app/scripts/sync_todo_to_obsidian.py
```

## Template Repository Sync

A public template repository exists for sharing the codebase without personal data. Use the sync script to push updates.

### Template Repository

- **URL**: https://github.com/CarlSaganInHouse/WebAppChat-Template
- **Purpose**: Shareable template for others to deploy their own instance
- **Differences**: Personal data (IPs, domains, credentials) replaced with placeholders

### Push Updates to Template

The script strips personal data and pushes to the template repo:

```bash
cd /root/WebAppChat
./scripts/push_to_template.sh
```

**With automatic push (requires GitHub token):**

```bash
GITHUB_TOKEN=ghp_xxx ./scripts/push_to_template.sh
```

**Permanent token setup:**

```bash
# Add to shell profile (run once)
echo 'export GITHUB_TOKEN=ghp_xxx' >> ~/.bashrc
source ~/.bashrc

# Then just run:
./scripts/push_to_template.sh
```

### What Gets Stripped

The `scripts/prepare_template.py` script replaces:

| Personal Data | Replaced With |
|---------------|---------------|
| `your-domain.com` | `your-domain.com` |
| `${LXC_HOST_IP}` (LXC) | `${LXC_HOST_IP}` |
| `${PROXMOX_HOST_IP}` (Proxmox) | `${PROXMOX_HOST_IP}` |
| `${HOME_ASSISTANT_IP}` (Home Assistant) | `${HOME_ASSISTANT_IP}` |
| `LXC ${LXC_ID}`, `container ${LXC_ID}` | `LXC ${LXC_ID}` |
| `subvol-${LXC_ID}-disk-0` | `subvol-${LXC_ID}-disk-0` |

Files excluded: `.env`, `webdav_users.json`, `*.sqlite3`, `_archive_*`

### Template Documentation

The template includes AI-optimized setup documentation:

- `SETUP.md` - Phased setup guide for AI agents
- `HANDOFF_PROMPT.md` - Initial prompt for Claude Code to begin setup
- `docs/WorldModel/WorldModel.example.json` - Example personal context schema

---

## Quick Health Checks

```bash
docker ps --filter name=webchat-app --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker ps --filter name=webdav-server --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Check vault mount inside container:

```bash
docker exec webchat-app ls /app/vault/obsidian-vault
```
