---
title: Getting Started Guide
last_verified: 2026-01-11
verified_by: Gemini
applies_to: User Onboarding
---

# Getting Started with WebAppChat

Welcome to your self-hosted AI workspace. WebAppChat is designed to be your primary interface for interacting with LLMs while maintaining deep integration with your Obsidian vault and personal automations.

## 🚀 Accessing the Application

The application is accessible via two primary routes:

1.  **Production (Web):** [https://your-domain.com](https://your-domain.com) (Protected by Cloudflare Tunnel)
2.  **Local (LAN):** http://${LXC_HOST_IP}:5000 (Direct access within your home network)

### Authentication
Upon arrival, you will be prompted to log in. Use your configured credentials to access the chat interface. If you need to manage your user account or API keys, navigate to the **Settings** cog in the sidebar.

---

## 💬 Models & Capabilities

WebAppChat provides access to a wide range of "Personas" and models. You can switch models mid-conversation using the dropdown selector.

### Cloud Models (API Driven)
*   **GPT-4o-mini:** Fast, cheap, and excellent for basic reasoning and quick captures.
*   **Claude 3.5 Sonnet:** The gold standard for coding, structured data analysis, and long-form writing.

### Local Models (GPU Accelerated)
*   **Ollama (Local):** Runs directly on your Proxmox server's GPU. Ideal for privacy-sensitive data and offline-first interactions.

### CLI Proxies (Subscription Based)
These models leverage your existing CLI subscriptions to provide "unlimited" or higher-tier reasoning:
*   **Claude Code CLI:** Uses your Claude Max subscription via a local proxy (Port 9876).
*   **Codex CLI:** Uses ChatGPT Plus/Pro capabilities via proxy (Port 9877).
*   **Gemini CLI:** Accesses Google's latest models via the free-tier proxy (Port 9878).

---

## 🗂️ The Vault Structure (PARA)

Your notes are organized according to the **PARA** method. The AI is trained to respect these boundaries:

*   **00-Inbox/**: Default landing spot for all new captures. Treat this as your "processing queue."
*   **10-Projects/**: Active, time-bound efforts (e.g., 10-Projects/Active/Kitchen-Reno).
*   **20-Areas/**: Ongoing responsibilities with no end date (e.g., 20-Areas/Homelab).
*   **30-Assets/**: Tracking physical items, pets, or property (e.g., 30-Assets/Vehicles).
*   **60-Calendar/**: Daily notes (60-Calendar/Daily/) and meeting logs.
*   **90-Meta/**: System files, including Templates/ and Attachments/.

---

## 🛠️ Common Workflows

### 1. Daily Journaling & Tasks
To add a task, simply type: *"Add Check garden to my daily list."* The AI will automatically locate today's note in 60-Calendar/Daily/ and append the item under the ## Tasks section.

### 2. Quick Captures (Inbox)
For ephemeral thoughts or web snippets, say: *"Save this to my inbox: [Content]"*. The system creates a new timestamped file in 00-Inbox/ for later sorting.

### 3. Voice Interaction
Click the **Microphone** icon to use voice-to-text (OpenAI Whisper). The system is optimized for "Kitchen Mode" hands-free use.

### 4. RAG Search (Knowledge Retrieval)
Ask: *"What were my notes on the RX 580 setup?"* The system will perform a semantic search across your entire vault and provide an answer with citations.

---

## 📂 WebDAV: Mapping your Vault

To manage your notes visually in Obsidian or your File Explorer, map the WebDAV share:

*   **URL:** https://your-domain.com/webdav (or http://${LXC_HOST_IP}:8080 locally)
*   **Windows:** Right-click "This PC" -> "Map Network Drive". Enter the URL and your WebDAV credentials.
*   **Mac:** In Finder, Cmd+K (Connect to Server) and enter the URL.

*Note: Credentials for WebDAV are managed in webdav_users.json and are separate from your web app login.*
