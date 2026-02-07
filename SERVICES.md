# Services — Operational Reference

## System-Level Services (need `sudo`)

All managed via `sudo systemctl {start,stop,restart,status} <unit>`.
Logs: `journalctl -u <unit> -f`

| Unit | Port | Working Dir | Description |
|------|------|-------------|-------------|
| robothor-vision.service | 8600 | brain/memory_system | YOLO + InsightFace detection loop |
| mediamtx-webcam.service | 8554 | — | USB webcam → RTSP stream |
| robothor-orchestrator.service | 9099 | brain/memory_system | FastAPI RAG orchestrator + vision endpoints |
| robothor-voice.service | 8765 | brain/voice-server | Twilio ConversationRelay voice |
| robothor-status.service | 3000 | brain/robothor-status | robothor.ai homepage |
| robothor-status-dashboard.service | 3001 | brain/robothor-status-dashboard | status.robothor.ai dashboard |
| robothor-dashboard.service | — | brain/dashboard | Internal dashboard |
| robothor-transcript.service | — | brain/memory_system | Voice transcript watcher |
| cloudflared.service | — | — | Cloudflare tunnel (robothor.ai) |
| tailscaled.service | — | — | Tailscale VPN (ironsail tailnet) |

## User-Level Service

Managed via `systemctl --user {start,stop,restart,status} <unit>`.
Logs: `journalctl --user -u <unit> -f`

| Unit | Port | Description |
|------|------|-------------|
| moltbot-gateway.service | 18789 | OpenClaw messaging gateway |

## Health Checks

```bash
# Vision service
curl -s http://localhost:8600/health | jq .

# RAG orchestrator
curl -s http://localhost:9099/health | jq .

# Status server
curl -s http://localhost:3000 > /dev/null && echo "OK"

# Status dashboard
curl -s http://localhost:3001 > /dev/null && echo "OK"

# MediaMTX RTSP (test frame capture)
ffmpeg -rtsp_transport tcp -i rtsp://localhost:8554/webcam -frames:v 1 -y /tmp/test.jpg 2>/dev/null && echo "OK"

# Moltbot gateway
curl -s http://localhost:18789/health 2>/dev/null || echo "No health endpoint — check systemctl"

# Cloudflare tunnel
curl -s https://robothor.ai > /dev/null && echo "OK"

# Tailscale
tailscale status | head -3

# Ollama
curl -s http://localhost:11434/api/tags | jq '.models[].name'

# PostgreSQL
psql -d robothor_memory -c "SELECT count(*) FROM long_term_memory;" 2>/dev/null
```

## System Crontab

View: `crontab -l`

| Schedule | Job | Log |
|----------|-----|-----|
| */5 * * * * | Calendar sync | memory_system/logs/calendar-sync.log |
| */5 * * * * | Email sync | memory_system/logs/email-sync.log |
| */30 6-22 * * 1-5 | Jira sync (M-F work hours) | memory_system/logs/jira-sync.log |
| */15 * * * * | Garmin health sync | ~/garmin-sync/sync.log |
| 0 3 * * * | Memory maintenance (TTL, archival) | memory_system/logs/maintenance.log |
| 30 3 * * * | Intelligence pipeline (Llama 3.2) | memory_system/logs/intelligence.log |
| 0 4 * * * | Snapshot cleanup (>30 days) | — |

## OpenClaw Cron Jobs

View: `cat ~/.openclaw/cron/jobs.json`

| Schedule | Job | Delivery |
|----------|-----|----------|
| */15 * * * * | Triage Worker | none (silent) |
| */17 7-22 * * * | Supervisor Heartbeat | announce → telegram |
| */10 7-23 * * * | Vision Monitor | announce → telegram |
| 30 6 * * * | Morning Briefing | announce → telegram |
| 0 21 * * * | Evening Wind-Down | announce → telegram |

One-shot jobs (auto-delete after run):
- SMS Status Check (2026-02-10)
- Build SMS Receiving Webhook (disabled, pending)
- Reminder: Ask Dad to Feed the Eel (2026-02-21)

## Startup Order After Reboot

Most services are enabled and start automatically. If anything fails:

```bash
# 1. System services (auto-start, but verify)
sudo systemctl status cloudflared tailscaled mediamtx-webcam
sudo systemctl status robothor-orchestrator robothor-vision
sudo systemctl status robothor-status robothor-status-dashboard
sudo systemctl status robothor-voice robothor-dashboard robothor-transcript

# 2. User service
systemctl --user status moltbot-gateway

# 3. If orchestrator didn't start (depends on ollama + postgres + docker)
sudo systemctl restart robothor-orchestrator

# 4. If moltbot gateway is down
systemctl --user restart moltbot-gateway
```
