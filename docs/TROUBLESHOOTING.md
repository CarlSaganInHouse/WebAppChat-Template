---
title: Troubleshooting Guide
last_verified: 2026-01-16
verified_by: Claude
applies_to: Proxmox/LXC/Docker Stack
---

# Troubleshooting Guide

This guide provides solutions for common issues in the WebAppChat ecosystem.

## 🛑 Critical Safety Warning
**Never perform file operations directly on the Proxmox host** (/rpool/data/subvol-500...) while the container is running. This leads to file handle staleness and permission "ghosts."
*   **Correct Way:** SSH into the LXC container (500) or use `pct exec ${LXC_ID} -- bash`.

---

## 🔌 Connection & Auth Issues

### "I can't reach the app at your-domain.com"
1.  **Check Cloudflare Tunnel:**
    From Proxmox Host: `systemctl status cloudflared`.
2.  **Check LXC Status:**
    From Proxmox Host: `pct status 500`. If stopped, run `pct start 500`.
3.  **Check Docker Stack:**
    Inside LXC: `docker ps`. Ensure `webchat-app` is "Up".

### "WebDAV password keeps failing"
*   WebDAV uses independent credentials.
*   **Fix:** Run `python3 scripts/generate_webdav_credentials.py <name>` inside the LXC, then `docker restart webdav-server`.

---

## 🧠 Model & Proxy Failures

### "Claude/Codex CLI not responding"
The CLI proxies run as `systemd` services inside LXC ${LXC_ID}.
*   **Diagnosis:**
    ```bash
    # Inside LXC ${LXC_ID}
    systemctl status claude-proxy  # Port 9876
    systemctl status codex-proxy   # Port 9877
    systemctl status gemini-proxy  # Port 9878
    ```
*   **Fix:** `systemctl restart <service-name>`.

### "Ollama (Local) is slow or failing"
*   **Check GPU Acceleration:** Run `radeontop` on the Proxmox host. If usage is 0% during a local query, Ollama has fallen back to CPU.
*   **Fix:** `systemctl restart ollama` on the Proxmox host.

---

## 🛠️ Integration Issues

### Microsoft To Do Sync failing
*   **Symptoms:** "Task-List.md" isn't updating or shows OAuth errors.
*   **Fix:** Navigate to the Web UI /settings page and click **"Re-authenticate Microsoft To Do"**. This refreshes the Graph API token.

### API "Budget Exceeded" or 429 Errors
*   Check your OpenAI/Anthropic usage dashboards.
*   **Fix:** Update your `MAX_CHAT_COST` in .env or check if a "Tool Loop" has gone infinite (check `app.log`).

---

## 📝 Data & File Issues

### "AI can't see my new notes"
*   **RAG Sync Delay:** New notes aren't instant. Check the status: `GET /api/rag/rag-sync-status`.
*   **Forced Sync:** Click "Sync Vault" in the UI or run:
    ```bash
    docker exec webchat-app python3 scripts/manage.py sync-rag
    ```

### Database Locked (`sqlite3.OperationalError: database is locked`)
*   Happens when multiple processes try to write to `chats.sqlite3` simultaneously.
*   **Fix:**
    1. `docker restart webchat-app` (to clear stale locks).
    2. Ensure cron jobs are not overlapping (check `crontab -l`).

---

## 🔧 Tool Calling Issues

### "LLM outputs JSON instead of calling tools"
The model is outputting tool parameters as text rather than making actual tool calls.

**Symptoms:**
- Response shows `{"path":"..."}`  or similar JSON
- No actual vault/task operation occurs
- User has to repeat the request

**Causes & Fixes:**
1. **Streaming mode active**: `/ask-stream` doesn't support tool calling. Use `/ask` endpoint (agentic mode).
2. **Chat mode selected**: Tool calling is disabled in chat mode. Switch to agentic mode.
3. **Intent guard not triggering**: Check if `REQUIRE_TOOL_FOR_READS=true` in `.env` and restart.

### "LLM says 'I'll check...' before acting"
The model outputs anticipatory narration alongside tool calls.

**Cause:** The RESPONSE STYLE prompt guidance isn't fully suppressing narration, or narration appears in the post-tool response.

**Mitigations (applied in order):**
1. **RESPONSE STYLE prompt**: Instructs model to suppress narration when making tool calls
2. **OpenAI**: `tool_choice="required"` forces tool calls when intent is detected
3. **Anthropic**: Retry mechanism triggers on missing tool calls
4. **Post-tool response clamp**: After tool execution, a system message tells the model to respond with the answer only

If issues persist:
- Check logs for `[GUARD]` messages indicating retry attempts
- Verify `AGENT_MODE` setting (autonomous vs structured) - both modes now have RESPONSE STYLE guidance
- The post-tool clamp message is: "Tools have executed. Respond with the answer only."

### "Tool call verification failing"
Write operations failing verification despite appearing to succeed.

**Fix:** Check `VERIFY_VAULT_WRITES`, `VERIFICATION_MAX_RETRIES`, and `VERIFICATION_STRICT_MODE` in `.env`. See CONFIGURATION.md for details.

---

## 🔍 Diagnosis Commands

| Task | Command | Context |
| :--- | :--- | :--- |
| **Real-time Logs** | `docker logs -f webchat-app` | LXC ${LXC_ID} |
| **RAG Sync Logs** | `tail -f logs/rag_sync.log` | Repo Root |
| **LXC Health** | `pct list` | Proxmox Host |
| **Disk Space** | `df -h` | LXC ${LXC_ID} |
| **Check Guard Activity** | `docker logs webchat-app 2>&1 \| grep GUARD` | LXC ${LXC_ID} |

### Resetting the Environment
If the app is completely wedged:
```bash
# Inside LXC ${LXC_ID}
cd /root/WebAppChat
docker compose down
docker compose up -d
```
