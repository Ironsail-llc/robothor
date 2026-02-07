# Cron Map — Unified Schedule

All times in America/New_York (ET).

## Timeline

```
Every 5 min    │ Calendar sync (crontab) — brain/scripts/calendar_sync.py
               │ Email sync (crontab) — brain/scripts/email_sync.py

Every 15 min   │ Garmin health sync (crontab) — health/garmin_sync.py
               │ Triage Worker (OpenClaw) — process logs, categorize, act, escalate

Every 17 min   │ Supervisor Heartbeat (OpenClaw, 7-22h) — surface escalations, audit logs
  (7 AM-10 PM) │

Every 10 min   │ Vision Monitor (OpenClaw, 7-23h) — check motion events, alert visitors
  (7 AM-11 PM) │

Every 30 min   │ Jira sync (crontab, 6-22h M-F) — brain/scripts/jira_sync.py
  (M-F only)   │

03:00 AM       │ Memory maintenance (crontab) — brain/memory_system/maintenance.sh
               │   TTL expiry, archival, stats

03:30 AM       │ Intelligence pipeline (crontab) — brain/memory_system/intelligence_pipeline.py
               │   Llama 3.2 Vision fact extraction from logs

04:00 AM       │ Snapshot cleanup (crontab) — delete vision snapshots > 30 days

06:30 AM       │ Morning Briefing (OpenClaw) — calendar, email, weather, news → Telegram

21:00          │ Evening Wind-Down (OpenClaw) — tomorrow preview, open items → Telegram

Sunday 04:15   │ SSD backup (crontab) — ~/robothor/scripts/backup-ssd.sh
               │   rsync all dirs + pg_dump + crontab + model list
```

## System Crontab (crontab -l)

```crontab
# Garmin health sync
*/15 * * * * /home/philip/garmin-sync/venv/bin/python /home/philip/garmin-sync/garmin_sync.py >> /home/philip/garmin-sync/sync.log 2>&1

# Memory maintenance
0 3 * * * /home/philip/clawd/memory_system/maintenance.sh

# Intelligence pipeline
30 3 * * * cd /home/philip/clawd/memory_system && ./venv/bin/python intelligence_pipeline.py >> logs/intelligence.log 2>&1

# Calendar sync
*/5 * * * * cd /home/philip/clawd && /home/philip/clawd/memory_system/venv/bin/python scripts/calendar_sync.py >> memory_system/logs/calendar-sync.log 2>&1

# Email sync
*/5 * * * * cd /home/philip/clawd && /home/philip/clawd/memory_system/venv/bin/python scripts/email_sync.py >> memory_system/logs/email-sync.log 2>&1

# Jira sync
*/30 6-22 * * 1-5 cd /home/philip/clawd && /home/philip/clawd/memory_system/venv/bin/python scripts/jira_sync.py >> memory_system/logs/jira-sync.log 2>&1

# Snapshot cleanup
0 4 * * * find /home/philip/clawd/memory/snapshots -name '*.jpg' -mtime +30 -delete && find /home/philip/clawd/memory/snapshots -type d -empty -delete

# Weekly SSD backup - Sunday at 4:15 AM
15 4 * * 0 /home/philip/robothor/scripts/backup-ssd.sh
```

## OpenClaw Cron Jobs (runtime/cron/jobs.json)

| ID | Name | Schedule | Session | Delivery |
|----|------|----------|---------|----------|
| a1b2...0001 | Triage Worker | */15 * * * * | isolated | none |
| b7e3...0001 | Supervisor Heartbeat | */17 7-22 * * * | isolated | announce → telegram |
| vision...0001 | Vision Monitor | */10 7-23 * * * | isolated | announce → telegram |
| 282b...b829 | Morning Briefing | 30 6 * * * | isolated | announce → telegram |
| 88db...dca0 | Evening Wind-Down | 0 21 * * * | isolated | announce → telegram |

### One-Shot Jobs (deleteAfterRun)

| Name | Scheduled | Status |
|------|-----------|--------|
| SMS Status Check | 2026-02-10 15:00 UTC | enabled |
| Build SMS Receiving Webhook | 2026-02-15 15:00 UTC | disabled |
| Reminder: Ask Dad to Feed the Eel | 2026-02-21 14:00 UTC | enabled |

## Notes

- Triage Worker uses `delivery: none` — runs silently, no Telegram output
- Supervisor Heartbeat outputs to Telegram but suppresses HEARTBEAT_OK
- Vision Monitor only alerts on noteworthy events (visitors, deliveries, anomalies)
- Morning Briefing and Evening Wind-Down always deliver to Telegram
- All OpenClaw crons use `agentId: main` and `wakeMode: next-heartbeat`
- All OpenClaw crons use Opus 4.6 for processing
