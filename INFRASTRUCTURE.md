# Infrastructure

## Hardware

**Lenovo ThinkStation PGX (DGX Spark)**
- CPU: NVIDIA Grace (ARM Cortex-X925), 20 cores, aarch64
- GPU: NVIDIA Blackwell GB10 (integrated)
- Memory: 128 GB unified (CPU + GPU shared)
- OS: Ubuntu 24.04, Linux 6.14.0-1015-nvidia
- Location: 29 W 16th Road, Broad Channel, NY 11693

## Networking

### Cloudflare Tunnel

Domain: `robothor.ai`
Tunnel ID: `2c15ab71-d540-4308-840d-0b3a564c3e7a`
Service: `cloudflared.service` (system-level, auto-starts)
Config: `tunnel/config.yml`

| Hostname | Backend | Purpose |
|----------|---------|---------|
| robothor.ai | localhost:3000 | Status server (homepage) |
| status.robothor.ai | localhost:3001 | Status dashboard |
| voice.robothor.ai | localhost:8765 | Twilio voice server |
| gchat.robothor.ai | localhost:18789 | Google Chat webhook (moltbot) |
| * (catch-all) | http_status:404 | — |

Note: The live Cloudflare config may have additional routes (privacy.robothor.ai, dashboard.robothor.ai) managed via API — `tunnel/config.yml` is the local copy and may lag.

### Tailscale

| Field | Value |
|-------|-------|
| IP | 100.91.221.100 |
| Hostname | thinkstationpgx-9c59 |
| Tailnet | ironsail |
| Service | tailscaled.service (system-level) |

## Database

**PostgreSQL 16 + pgvector 0.6.0**

Database: `robothor_memory`
User: `philip` (local peer auth) + `postgres` (legacy tables)

| Table | Owner | Purpose |
|-------|-------|---------|
| long_term_memory | postgres | Permanent memories with embeddings |
| short_term_memory | postgres | 48h TTL working memories |
| memory_facts | philip | Structured facts (categorized, confidence-scored) |
| memory_entities | philip | Knowledge graph nodes (people, projects, tech) |
| memory_relations | philip | Knowledge graph edges |
| audit_log | postgres | System audit trail |

Embeddings: 1024-dim vectors via Qwen3-Embedding, indexed with pgvector ivfflat.

## Ollama (localhost:11434)

| Model | Params | Quant | Size | Role |
|-------|--------|-------|------|------|
| llama3.2-vision:11b | 11B | — | 7.8 GB | Vision analysis, intelligence pipeline |
| qwen3-embedding:0.6b | 595M | Q8_0 | 639 MB | Dense embeddings (always loaded) |
| Qwen3-Reranker-0.6B:F16 | ~600M | F16 | 1.2 GB | Cross-encoder reranking (always loaded) |

**Loaded on demand (not always resident):**
- qwen3-next:latest (79.7B, Q4_K_M, ~50 GB VRAM) — RAG generation only

Ollama version: v0.15.5-rc2

## Vision Stack

| Component | Detail |
|-----------|--------|
| Camera | USB webcam at /dev/video0 |
| RTSP server | MediaMTX at rtsp://localhost:8554/webcam |
| Resolution | 640x480 @ 30fps H.264 |
| Object detection | YOLOv8-nano (~6 MB) |
| Face recognition | InsightFace buffalo_l ArcFace (~300 MB) |
| VLM | llama3.2-vision:11b via Ollama (on-demand) |
| Face match threshold | cosine similarity > 0.45 |
| Snapshots | brain/memory/snapshots/ (30-day retention) |
| Face data | brain/memory/faces/enrolled_faces.json |
| Service | robothor-vision.service (system-level) |
| Health | http://localhost:8600/health |

## GCP

| Field | Value |
|-------|-------|
| Project | robothor-485903 (Project #152250299895) |
| Service account | moltbot-chat@robothor-485903.iam.gserviceaccount.com |
| Key file | ~/.moltbot/googlechat-service-account.json |
| Services | Google Chat, NotebookLM Enterprise |

## RAG Orchestrator (port 9099)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| /health | GET | Component status |
| /query | POST | RAG query (question + profile) |
| /v1/chat/completions | POST | OpenAI-compatible chat |
| /profiles | GET | List RAG profiles |
| /stats | GET | Memory statistics |
| /ingest | POST | Cross-channel ingestion |
| /vision/* | GET/POST | Vision service proxy endpoints |

**RAG profiles:** fast, general, research, expert, heavy, code

Start: `brain/memory_system/start_rag.sh`
Now managed by: `robothor-orchestrator.service` (auto-starts)
