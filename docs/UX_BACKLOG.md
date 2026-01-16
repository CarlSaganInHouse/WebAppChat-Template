---
title: UX Backlog
created: 2026-01-14
type: product-audit
applies_to: templates/, static/style.css
---

# UX Backlog: Personal Speed & Low Friction Audit

This document contains a prioritized backlog of UX improvements for WebAppChat, audited against the workflows defined in [GETTING_STARTED.md](GETTING_STARTED.md) and features in [API.md](API.md).

---

## Top Tasks (Inferred from Personal Workflows)

Based on GETTING_STARTED.md, the primary user tasks are:

| Task | Workflow Reference | Frequency |
|------|-------------------|-----------|
| **Quick Capture** | "Save this to my inbox" - 00-Inbox/ | High (multiple daily) |
| **Voice Interaction** | Kitchen Mode hands-free | High (daily) |
| **Daily Journaling** | Add tasks to 60-Calendar/Daily/ | High (daily) |
| **Chat/RAG Recall** | "What were my notes on...?" | Medium (several weekly) |
| **Model Switching** | Switch mid-conversation | Medium |
| **Reviewing Past Chats** | Search, tags, archive | Low-Medium |
| **RAG Sync** | Sync Obsidian vault | Low (periodic) |

---

## Heuristic Audit Summary

### Navigation / Information Architecture
- **Good:** Sidebar with search, tags, archive toggle
- **Issue:** No command palette for power users
- **Issue:** Settings drawer requires click to expand; no persistent status
- **Issue:** Right panel collapsed by default; RAG status hidden

### Empty States & Onboarding
- **Issue:** No first-run welcome or onboarding
- **Issue:** Empty chat list shows nothing helpful
- **Issue:** No guidance on PARA structure or voice setup

### Feedback & Error Recovery
- **Good:** Toast notifications for actions
- **Good:** Voice error handling with user-friendly messages
- **Issue:** RAG sync status not visible from main chat view
- **Issue:** No indicator when CLI proxies (Claude Code, Codex, Gemini) are unavailable

### Visibility of System Status
- **Good:** Voice button shows recording state
- **Good:** Budget bar in settings drawer
- **Good:** Agentic/Chat mode toggle visible
- **Issue:** No persistent voice-enabled indicator
- **Issue:** No RAG sync status in topbar
- **Issue:** No provider availability indicators

### Power-User Affordances
- **Good:** Keyboard shortcuts (Ctrl+K search, Ctrl+N new, Ctrl+\ voice)
- **Good:** Shortcuts help modal (Ctrl+/)
- **Issue:** No command palette (Ctrl+P style)
- **Issue:** No quick-action bar for common tasks

### Accessibility Basics
- **Good:** aria-labels on main navigation elements
- **Good:** role attributes on key regions
- **Issue:** Some muted text (#858585) may have contrast issues on dark background
- **Issue:** Focus ring visibility could be improved
- **Issue:** No skip-to-content link

---

## Prioritized Backlog

### Quick Wins (2 hours or less)

#### QW-1: Add Welcome Empty State to Chat List
**Why it matters:** New users see blank chat list with no guidance. Per GETTING_STARTED, users need to understand quick captures, voice, and PARA structure.

**Builds on:** `GET /chats` returns empty array for new users

**UI Change:**
- When `chatList` is empty, show:
  ```
  Welcome to WebAppChat!

  + New Chat (Ctrl+N)

  Quick actions:
  - Voice capture (Ctrl+\)
  - Save to Inbox (inbox button)

  Your vault uses PARA:
  00-Inbox | 10-Projects | 20-Areas | 60-Calendar
  ```

**Files:**
- `templates/index.html` (~line 68, chatList rendering)
- `static/style.css` (add `.empty-state-welcome` styles)

**Risks:** None - display-only change

---

#### QW-2: Add RAG Sync Status Badge to Topbar
**Why it matters:** Per GETTING_STARTED workflow "RAG Search", users need to know if vault is synced. Currently hidden in collapsed right panel.

**Builds on:** `GET /rag-sync-status` endpoint

**UI Change:**
- Add small badge next to model selector: `RAG: Synced 15m ago` or `RAG: Syncing...`
- Click opens right panel to RAG section
- Badge color: green (synced <30m), yellow (stale), red (error)

**Files:**
- `templates/index.html` (topbar-minimal section ~line 73)
- `static/style.css` (`.rag-status-badge` styles)

**Risks:** Additional API call on page load; cache status client-side

---

#### QW-3: Improve Voice Button Disabled State Messaging
**Why it matters:** Kitchen Mode workflow depends on voice. If unsupported, user needs clear guidance.

**Builds on:** Voice button already has disabled state (`voiceBtn.disabled = true`)

**UI Change:**
- Change tooltip from "Voice not supported" to "Voice requires Chrome/Edge. Using Safari?"
- Add small info icon (?) that shows browser compatibility on hover

**Files:**
- `templates/index.html` (~line 1365-1372, voice button setup)
- `static/style.css` (`.voice-btn.disabled` tooltip styles)

**Risks:** None

---

#### QW-4: Add Focus Visible Outline for Keyboard Navigation
**Why it matters:** Accessibility - keyboard users need visible focus indicators.

**Builds on:** Existing keyboard shortcuts in SHORTCUTS object

**UI Change:**
- Add `:focus-visible` styles with high-contrast outline
- Ensure all interactive elements have visible focus ring

**Files:**
- `static/style.css` (add global `:focus-visible` rule)

**Risks:** None

---

#### QW-5: Add Skip-to-Content Link
**Why it matters:** Accessibility - screen reader and keyboard users need quick navigation.

**UI Change:**
- Add visually hidden link at top of body: "Skip to chat"
- Link targets `#chat-log`
- Visible on focus

**Files:**
- `templates/index.html` (after `<body>` tag)
- `static/style.css` (`.skip-link` styles)

**Risks:** None

---

#### QW-6: Show Provider Status Indicators for CLI Models
**Why it matters:** CLI proxies (Claude Code, Codex, Gemini CLI) depend on external processes. Per API.md, they return 503 if unavailable.

**Builds on:** Model select already groups by provider

**UI Change:**
- Add status dot next to CLI model options in dropdown
- Green = proxy responding, Red = unavailable
- Check `/voice/status` pattern for implementation

**Files:**
- `templates/index.html` (~line 374, modelSelect population)
- Add health check fetch on page load

**Risks:** Need to create lightweight health endpoints for CLI proxies (or use existing if available)

---

### Medium Priority (2 days or less)

#### M-1: Implement Command Palette (Ctrl+P)
**Why it matters:** Power users (per keyboard shortcuts) need fast access to all actions without mouse. Critical for Quick Capture workflow speed.

**Builds on:** Existing SHORTCUTS object, all API endpoints

**UI Change:**
- Modal overlay with search input
- Fuzzy search across:
  - Actions: New chat, Save to Inbox, Voice, Sync RAG, Export
  - Recent chats (from `GET /chats`)
  - Settings toggles
  - Tags (from `GET /tags`)
- Keyboard navigation (arrow keys, enter to select)

**Files:**
- `templates/index.html` (add modal markup, command palette JS)
- `static/style.css` (`.command-palette` styles)

**Risks:** Adds ~200 lines of JS; test fuzzy matching performance

---

#### M-2: Persistent System Status Bar
**Why it matters:** Multiple workflows depend on knowing system state (voice enabled, RAG synced, mode active).

**Builds on:** `GET /voice/status`, `GET /rag-sync-status`, `GET /models`

**UI Change:**
- Thin bar below topbar showing:
  - Voice: On/Off (click toggles)
  - RAG: Synced/Stale/Error (click opens sync)
  - Mode: Agentic/Chat (already exists, move here)
  - Ollama: Loaded/Offline (from `GET /ollama-status`)
- Collapsible to just icons on mobile

**Files:**
- `templates/index.html` (new `.status-bar` element)
- `static/style.css` (status bar styles, responsive)

**Risks:** Multiple API calls; implement with Promise.all and cache

---

#### M-3: Quick Capture Floating Action Button (Mobile)
**Why it matters:** Kitchen Mode workflow - hands-free capture. Current inbox button buried in composer.

**Builds on:** `POST /save-to-inbox`

**UI Change:**
- Floating action button (FAB) in bottom-right on mobile
- Tap opens mini-modal:
  - Voice record button (large, centered)
  - "Save to Inbox" action
  - Auto-dismiss after save
- Desktop: FAB hidden, existing buttons sufficient

**Files:**
- `templates/index.html` (add FAB markup)
- `static/style.css` (`.quick-capture-fab`, mobile media query)

**Risks:** Z-index conflicts; test on actual mobile devices

---

#### M-4: Onboarding Tour for New Users
**Why it matters:** GETTING_STARTED lists multiple capabilities that new users won't discover. First-run experience matters for self-hosted personal tools.

**Builds on:** Could use localStorage flag `onboarding.completed`

**UI Change:**
- First visit (no chats): show modal with:
  1. "Welcome to your AI workspace"
  2. Voice capture demo (if supported)
  3. PARA structure quick guide
  4. RAG search example
- "Skip" and "Next" buttons
- Mark completed in localStorage

**Files:**
- `templates/index.html` (onboarding modal markup and JS)
- `static/style.css` (`.onboarding-modal` styles)

**Risks:** Must be skippable; don't block returning users

---

#### M-5: Inline RAG Citations with Preview
**Why it matters:** RAG Search workflow returns citations. Currently shown in drawer; could be inline.

**Builds on:** `POST /ask` returns `citations` array with `snippet`, `obsidian_link`

**UI Change:**
- Show citation badges inline after RAG responses: `[1] [2] [3]`
- Hover shows snippet preview tooltip
- Click opens citation drawer (existing)
- Badge style: small pill with source icon

**Files:**
- `templates/index.html` (message rendering, ~appendMessage function)
- `static/style.css` (`.citation-badge`, tooltip styles)

**Risks:** Performance if many citations; limit to first 5 inline

---

#### M-6: Improved Error Recovery for Budget Exceeded
**Why it matters:** Per API.md, 402 error when budget exceeded. User needs clear recovery path.

**Builds on:** `POST /chat/<cid>/budget`, budget display in settings drawer

**UI Change:**
- When 402 error received:
  - Toast: "Budget exceeded for this chat"
  - Auto-open settings drawer to budget section
  - Highlight budget input with error state
  - Show "Increase budget" button inline

**Files:**
- `templates/index.html` (error handling in ask/stream handlers)
- `static/style.css` (`.budget-error` highlight styles)

**Risks:** None

---

### Big Bets (2 weeks or less)

#### B-1: Full Keyboard-Driven Interface Mode
**Why it matters:** Power users need mouse-free operation. Current shortcuts are partial.

**Builds on:** Existing SHORTCUTS, command palette (M-1)

**UI Change:**
- Vim-like mode toggle (press `Esc` twice)
- Navigation:
  - `j/k`: Navigate chat list
  - `Enter`: Open selected chat
  - `/`: Focus search
  - `g g`: Go to top of chat
  - `G`: Go to bottom
  - `i`: Focus composer (insert mode)
- Visual mode indicators
- Help overlay for keybindings

**Files:**
- `templates/index.html` (keyboard mode handler, ~500 lines)
- `static/style.css` (mode indicators, selection highlighting)

**Risks:** Conflicts with text input; must have clear mode distinction

---

#### B-2: Voice-First Kitchen Mode
**Why it matters:** GETTING_STARTED explicitly mentions "Kitchen Mode" hands-free use. Current voice is supplementary, not primary.

**Builds on:** Voice endpoints, `?focus=voice` URL parameter (already exists!)

**UI Change:**
- New route: `/?mode=kitchen` or `/kitchen`
- Simplified UI:
  - Large microphone button (center screen)
  - Last response displayed prominently
  - Audio playback of responses (TTS)
  - Minimal visual clutter
  - "Back to full UI" link
- Auto-save captures to inbox
- Wake word consideration (future)

**Files:**
- `templates/kitchen.html` (new template)
- `static/kitchen.css` (dedicated styles)
- Or: conditional rendering in `index.html` based on mode param

**Risks:**
- Requires TTS integration testing
- Mobile wake-lock for screen-on
- Audio feedback design decisions

---

#### B-3: Progressive Web App (PWA) with Offline Quick Capture
**Why it matters:** Self-hosted app should work offline for quick captures. Personal tool resilience.

**Builds on:** Current web app, `POST /save-to-inbox`

**UI Change:**
- Add manifest.json for installability
- Service worker for:
  - Offline page shell
  - Queue captures when offline
  - Sync when back online
- Install prompt on mobile
- Badge for pending sync items

**Files:**
- `static/manifest.json` (new)
- `static/service-worker.js` (new)
- `templates/index.html` (SW registration, install prompt)

**Risks:**
- Cache invalidation complexity
- Offline queue must handle conflicts
- Requires HTTPS (already have via Cloudflare)

---

#### B-4: Natural Language Command Parser
**Why it matters:** Quick Capture and Daily Journaling workflows use natural language ("Add X to my daily list"). Could work from any input.

**Builds on:** `POST /obsidian/append-daily`, `POST /save-to-inbox`

**UI Change:**
- Detect command patterns in composer:
  - "Add X to my daily tasks" -> Direct append, no LLM
  - "Save to inbox: X" -> Direct save, no LLM
  - "Search vault for X" -> RAG query shortcut
- Show detected action as chip above composer
- User can confirm (Enter) or cancel (Esc)
- Falls back to normal chat if no pattern

**Files:**
- `templates/index.html` (pattern detection in form submit handler)
- `static/style.css` (`.detected-action-chip` styles)

**Risks:**
- Pattern matching false positives
- User expectation management
- May conflict with actual AI tool calling

---

#### B-5: Dashboard View for Daily Review
**Why it matters:** Reviewing past chats is a listed workflow. Current list view doesn't surface insights.

**Builds on:** `GET /analytics/*` endpoints, `GET /chats`

**UI Change:**
- New route: `/dashboard` or toggle in sidebar
- Shows:
  - Today's activity summary
  - Recent captures (inbox items)
  - Active projects (from tags)
  - Spending overview
  - RAG health status
  - Quick actions row
- Widget-based, customizable layout

**Files:**
- `templates/dashboard.html` (new)
- `static/dashboard.css` (new)
- Potentially new API endpoint for aggregated data

**Risks:**
- Significant new surface area
- Dashboard maintenance overhead
- May duplicate analytics panel functionality

---

## Implementation Priority Matrix

| ID | Impact | Effort | Priority Score |
|----|--------|--------|----------------|
| QW-1 | High (onboarding) | Low | 1 |
| QW-2 | Medium (awareness) | Low | 2 |
| QW-4 | Medium (a11y) | Low | 3 |
| QW-5 | Medium (a11y) | Low | 4 |
| M-1 | High (power users) | Medium | 5 |
| M-3 | High (mobile/voice) | Medium | 6 |
| QW-3 | Low | Low | 7 |
| QW-6 | Medium | Medium | 8 |
| M-2 | Medium | Medium | 9 |
| M-4 | Medium | Medium | 10 |
| B-2 | High (core workflow) | High | 11 |
| M-5 | Medium | Medium | 12 |
| M-6 | Low | Low | 13 |
| B-1 | Medium | High | 14 |
| B-3 | Medium | High | 15 |
| B-4 | Medium | High | 16 |
| B-5 | Low | High | 17 |

---

## See Also

- [GETTING_STARTED.md](GETTING_STARTED.md) - User workflows
- [API.md](API.md) - Available endpoints
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development standards
