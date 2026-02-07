# Data Flow

End-to-end flow from external APIs to Philip.

```
┌──────────────────────────────────────────────────────────────┐
│                      EXTERNAL SOURCES                         │
│                                                              │
│  Google Calendar  │  Gmail  │  Jira  │  Garmin  │  Camera    │
└────────┬─────────────┬────────┬─────────┬──────────┬─────────┘
         │             │        │         │          │
         ▼             ▼        ▼         ▼          ▼
┌──────────────────────────────────────────────────────────────┐
│              LAYER 1: SYSTEM CRONS (Python)                   │
│              No AI, no tokens, 100% mechanical                │
│                                                              │
│  calendar_sync.py  email_sync.py  jira_sync.py               │
│       */5 min          */5 min     */30 min M-F               │
│          │                │            │                      │
│          ▼                ▼            ▼                      │
│  calendar-log.json  email-log.json  jira-log.json            │
│  (null notifier fields — needs processing)                    │
│                                                              │
│  garmin_sync.py (*/15 min) → garmin-health.md                │
│  vision_service.py (always-on) → POST /ingest (camera)       │
│  intelligence_pipeline.py (3:30 AM) → fact extraction         │
│  maintenance.sh (3:00 AM) → TTL expiry, archival             │
└──────────────────────────────┬────────────────────────────────┘
                               │
                    logs with null fields
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│         LAYER 2a: TRIAGE WORKER (Opus 4.6, */15 min)          │
│         Isolated session via OpenClaw cron                     │
│                                                              │
│  1. Read email-log, calendar-log, jira-log                    │
│  2. Find entries where categorizedAt = null                   │
│  3. Categorize: urgency, category, actionRequired             │
│  4. Handle routine: mark read, draft reply, dismiss           │
│  5. Escalate complex → worker-handoff.json                    │
│  6. Update: categorizedAt, pendingReviewAt timestamps         │
│                                                              │
│  Output: "Processed 3 emails, escalated 1" or HEARTBEAT_OK   │
└──────────────────────────────┬────────────────────────────────┘
                               │
                    escalations + log updates
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│      LAYER 2b: SUPERVISOR HEARTBEAT (Opus 4.6, */17 min)      │
│      Isolated session via OpenClaw cron (7 AM - 10 PM)        │
│                                                              │
│  Phase 1 — Urgent:                                            │
│    • Read worker-handoff.json for unsurfaced escalations      │
│    • Surface to Philip via Telegram (set surfacedAt)          │
│    • Check healthCheck for API failures                       │
│    • Check calendar for meetings within 20 min                │
│                                                              │
│  Phase 2 — Log Audit:                                         │
│    • Every email entry has reviewedAt?                         │
│    • Pending actions have actionCompletedAt?                  │
│    • Escalations have resolvedAt?                             │
│    • Fix stale entries, handle pending actions                │
│                                                              │
│  Phase 3 — Output:                                            │
│    • Audit summary with counts per source                     │
│    • HEARTBEAT_OK if everything clean                         │
│    • Alert text → delivered to Philip via Telegram             │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                     PHILIP (via Telegram)                      │
│                                                              │
│  Receives: escalation alerts, meeting reminders,              │
│            morning briefings, evening wind-downs,             │
│            vision alerts (unknown persons)                     │
└──────────────────────────────────────────────────────────────┘
```

## Log Entry Lifecycle

Every log entry tracks processing state via notifier fields:

```
null → categorize → act → pendingReviewAt → verify → reviewedAt
```

| Field | null means | timestamp means |
|-------|-----------|-----------------|
| categorizedAt | Needs processing | Triage worker categorized it |
| actionRequired | Needs decision | (string value — what to do) |
| actionCompletedAt | Action pending | Action was taken |
| pendingReviewAt | Not flagged | Awaiting verification |
| reviewedAt | Not verified | Entry complete |

## Escalation Lifecycle

```
worker creates → supervisor surfaces → supervisor resolves
```

| Field | null | timestamp |
|-------|------|-----------|
| surfacedAt | Not shown to Philip | Philip was notified |
| resolvedAt | Not yet acted on | Action completed |

## Memory Ingestion Flow

```
Content (any channel)
    │
    POST /ingest (port 9099)
    │
    ├─ fact_extraction.py → memory_facts (structured)
    ├─ entity_graph.py → memory_entities + memory_relations
    └─ rag.py → long_term_memory (embeddings)
```

Channels: discord, email, cli, api, telegram, camera
