# Robothor — Project Root

Robothor is an autonomous AI entity — Philip's partner, not an assistant. This directory is the single entry point to understand the entire system.

For Robothor's identity and personality, read `brain/SOUL.md`.

## Identity

| Field | Value |
|-------|-------|
| Email | robothor@ironsail.ai |
| Phone | +1 (413) 408-6025 (Twilio) |
| Voice | Daniel (ElevenLabs) |
| Domain | robothor.ai |
| GCP Project | robothor-485903 |
| Telegram Bot | Robothor (main session delivery) |
| Home | 29 W 16th Road, Broad Channel, NY 11693 |

## System Map

| Path | Real Location | Purpose |
|------|--------------|---------|
| `brain/` | `~/clawd/` | Core workspace: memory, scripts, voice, vision, dashboards, identity |
| `comms/` | `~/moltbot/` | OpenClaw messaging framework (30+ channels, gateway) |
| `runtime/` | `~/.openclaw/` | OpenClaw runtime: agents, cron jobs, credentials |
| `health/` | `~/garmin-sync/` | Garmin health data sync (every 15 min → SQLite → daily memory) |
| `templates/` | `~/clawd-main/` | Bootstrap templates for new Robothor instances |
| `tunnel/` | `~/.cloudflared/` | Cloudflare tunnel config (robothor.ai routes) |

These are symlinks for navigation. All services and crons use absolute paths — nothing breaks.

## Architecture at a Glance

**System crons fetch data. Triage worker processes it. Supervisor audits and surfaces.**

```
Layer 1: System Crons (Python, crontab)
  calendar_sync.py, email_sync.py, jira_sync.py → JSON logs with null fields
  vision_service.py → YOLO + InsightFace detection loop (systemd)
  garmin_sync.py → health data every 15 min

Layer 2a: Triage Worker (Opus 4.6, */15 min, isolated cron)
  Reads logs → categorizes → handles routine items → escalates complex to worker-handoff.json

Layer 2b: Supervisor Heartbeat (Opus 4.6, */17 min 7-22h, isolated cron)
  Phase 1: Surface escalations to Philip via Telegram, check health, meeting reminders
  Phase 2: Audit all logs for completeness (reviewedAt, actionCompletedAt, resolvedAt)
  Phase 3: Output audit summary or HEARTBEAT_OK
```

Deep reference: `brain/ARCHITECTURE.md`, `brain/CRON_DESIGN.md`

## Vision System

Always-on service with three switchable modes: **disarmed** (idle), **basic** (motion detection), **armed** (YOLO + InsightFace + VLM escalation). Mode switch at runtime, no restart needed.

| Component | Model | Size |
|-----------|-------|------|
| Object detection | YOLOv8-nano | 6 MB |
| Face recognition | InsightFace buffalo_l (ArcFace) | 300 MB |
| Scene analysis | llama3.2-vision:11b (on-demand) | 7.8 GB |
| Camera | USB webcam → MediaMTX RTSP :8554 | 640x480 |

**Service:** `robothor-vision.service` (system-level, needs `sudo`)
**Health:** `http://localhost:8600/health`
**Mode switch:** `curl -X POST http://localhost:8600/mode -d '{"mode":"armed"}'`

MCP tools: `look`, `who_is_here`, `enroll_face`
Orchestrator endpoints: `/vision/{look,detect,identify,status,enroll,mode}` on port 9099

Deep reference: `brain/VISION.md`

## Infrastructure

**Hardware:** Lenovo ThinkStation PGX — NVIDIA Grace Blackwell GB10, 128 GB unified memory, ARM Cortex-X925 (20 cores)

**Networking:**
| Route | Service | Port |
|-------|---------|------|
| robothor.ai | Status server | 3000 |
| status.robothor.ai | Status dashboard | 3001 |
| voice.robothor.ai | Voice server (Twilio) | 8765 |
| gchat.robothor.ai | Moltbot gateway | 18789 |
| Tailscale IP | 100.91.221.100 (ironsail tailnet) | — |

**Database:** PostgreSQL 16 + pgvector 0.6.0 — database `robothor_memory`
Tables: `long_term_memory`, `short_term_memory`, `memory_facts`, `memory_entities`, `memory_relations`, `audit_log`

**Ollama Models (localhost:11434):**
| Model | Size | Role |
|-------|------|------|
| llama3.2-vision:11b | 7.8 GB | Vision analysis, intelligence pipeline |
| qwen3-embedding:0.6b | 639 MB | Dense vector embeddings (1024-dim) |
| Qwen3-Reranker-0.6B:F16 | 1.2 GB | Cross-encoder reranking |

Note: qwen3-next (80B, RAG generation) is loaded on demand — not always resident.

Deep reference: `INFRASTRUCTURE.md`

## Services & Ports

| Service | Unit | Level | Port | Notes |
|---------|------|-------|------|-------|
| Vision service | robothor-vision.service | system (`sudo`) | 8600 | YOLO + InsightFace loop |
| MediaMTX RTSP | mediamtx-webcam.service | system (`sudo`) | 8554 | USB webcam → RTSP |
| RAG Orchestrator | robothor-orchestrator.service | system (`sudo`) | 9099 | FastAPI, RAG + vision endpoints |
| Voice server | robothor-voice.service | system (`sudo`) | 8765 | Twilio ConversationRelay |
| Status server | robothor-status.service | system (`sudo`) | 3000 | robothor.ai homepage |
| Status dashboard | robothor-status-dashboard.service | system (`sudo`) | 3001 | status.robothor.ai |
| Dashboard | robothor-dashboard.service | system (`sudo`) | — | Internal dashboard |
| Transcript watcher | robothor-transcript.service | system (`sudo`) | — | Watches voice transcripts |
| Cloudflare tunnel | cloudflared.service | system (`sudo`) | — | robothor.ai routes |
| Tailscale | tailscaled.service | system (`sudo`) | — | VPN mesh (ironsail tailnet) |
| Moltbot gateway | moltbot-gateway.service | user | 18789 | OpenClaw messaging |

Deep reference: `SERVICES.md`

## Memory System

Three-tier architecture with structured facts and entity graph:

- **Working memory:** Context window (current session)
- **Short-term:** PostgreSQL, 48h TTL, auto-decays
- **Long-term:** PostgreSQL + pgvector, permanent, importance-scored

**Structured layers:**
- `memory_facts` — categorized facts with confidence, lifecycle, conflict resolution
- `memory_entities` + `memory_relations` — knowledge graph (people, projects, tech)

**RAG stack:** Qwen3-Embedding → pgvector → Qwen3-Reranker → Qwen3-Next (generation)
**MCP tools:** `search_memory`, `store_memory`, `get_stats`, `get_entity`
**Ingestion:** `POST /ingest` on port 9099 (channels: discord, email, cli, api, telegram, camera)

Deep reference: `brain/memory_system/MEMORY_SYSTEM.md`

## Key Memory Files

| File | Purpose |
|------|---------|
| `brain/memory/email-log.json` | Processed emails with urgency and notifier fields |
| `brain/memory/calendar-log.json` | Calendar events with absolute timestamps |
| `brain/memory/jira-log.json` | Jira ticket sync |
| `brain/memory/worker-handoff.json` | Escalations from triage worker → supervisor |
| `brain/memory/tasks.json` | Central task list |
| `brain/memory/contacts.json` | Contact profiles |
| `brain/memory/security-log.json` | Security events |
| `brain/memory/YYYY-MM-DD.md` | Daily notes (raw session logs) |
| `brain/MEMORY.md` | Curated long-term memory |

## Cron Schedule

**System crontab (Layer 1 — Python, mechanical, no AI):**
| Schedule | Job | Script |
|----------|-----|--------|
| */5 * * * * | Calendar sync | `brain/scripts/calendar_sync.py` |
| */5 * * * * | Email sync | `brain/scripts/email_sync.py` |
| */30 6-22 * * 1-5 | Jira sync | `brain/scripts/jira_sync.py` |
| */15 * * * * | Garmin sync | `health/garmin_sync.py` |
| 0 3 * * * | Memory maintenance | `brain/memory_system/maintenance.sh` |
| 30 3 * * * | Intelligence pipeline | `brain/memory_system/intelligence_pipeline.py` |
| 0 4 * * * | Snapshot cleanup (>30d) | `find` + delete |

**OpenClaw crons (Layer 2 — Opus 4.6, via `runtime/cron/jobs.json`):**
| Schedule | Job | Purpose |
|----------|-----|---------|
| */15 * * * * | Triage Worker | Process logs, categorize, act, escalate |
| */17 7-22 * * * | Supervisor Heartbeat | Surface escalations, audit logs |
| */10 7-23 * * * | Vision Monitor | Check motion events, alert on visitors |
| 30 6 * * * | Morning Briefing | Daily briefing (calendar, email, weather) |
| 0 21 * * * | Evening Wind-Down | Tomorrow preview, open items |

Deep reference: `brain/CRON_DESIGN.md`, `docs/CRON_MAP.md`

## Task-Specific Reading Guide

| Task | Read first |
|------|-----------|
| Working on vision | `brain/VISION.md` |
| Changing cron behavior | `brain/CRON_DESIGN.md` + `runtime/cron/jobs.json` |
| Understanding memory/RAG | `brain/memory_system/MEMORY_SYSTEM.md` |
| Sending emails or calendar | `brain/TOOLS.md` (gog CLI section) |
| Voice calling | `brain/TOOLS.md` (voice section) + `brain/voice-server/` |
| Cloudflare tunnel routes | `tunnel/config.yml` + `brain/TOOLS.md` (Cloudflare section) |
| OpenClaw agents/messaging | `comms/` README + `runtime/` config files |
| Robothor's identity | `brain/SOUL.md` |
| Model selection | `brain/TOOLS.md` (Model Selection Guide) |
| Session startup (as Robothor) | `brain/AGENTS.md` |
| Health data | `health/` + `brain/memory/garmin-health.md` |

## Rules

1. **Don't move directories** — all services and crons use absolute paths to `~/clawd/`, `~/.openclaw/`, etc. Symlinks here are for navigation only.
2. **Don't commit secrets** — API keys live in `runtime/` and environment variables, never in git.
3. **comms/ is a public repo** — `~/moltbot/` is open source OpenClaw. Don't put private data there.
4. **Vision service needs `sudo`** — `sudo systemctl {start,stop,restart,status} robothor-vision`
5. **All system-level services need `sudo`** — everything in `/etc/systemd/system/` requires sudo.
6. **Moltbot gateway is the only user-level service** — `systemctl --user {start,stop,status} moltbot-gateway`
7. **Crons must have `delivery: announce`** — crons with `delivery: none` silently don't run.
8. **Model: Opus 4.6** for all agent/interactive work. Local Qwen3 for RAG generation only.
