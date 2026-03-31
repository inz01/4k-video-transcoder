# 4K Video Transcoder — User Manual

**Stack:** Python · FastAPI · FFmpeg · Redis · RQ · psutil  
**Platform:** Linux (tested on Ubuntu 22.04 / 24.04)  
**Purpose:** Upload videos, transcode to 4K/1080p/720p/480p via FFmpeg, track real-time progress, and record KPI performance metrics.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Installation & Setup](#3-installation--setup)
4. [Starting the Application](#4-starting-the-application)
5. [Using the Web UI](#5-using-the-web-ui)
6. [API Reference](#6-api-reference)
7. [Testing with curl](#7-testing-with-curl)
8. [KPI Metrics & Viewer](#8-kpi-metrics--viewer)
9. [Project File Structure](#9-project-file-structure)
10. [OpenStack DevStack Deployment](#10-openstack-devstack-deployment)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (index.html + script.js)                               │
│  - Upload video file                                            │
│  - Select preset (4K / 1080p / 720p / 480p)                    │
│  - Poll real-time progress                                      │
│  - Download transcoded output                                   │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP (multipart/form-data)
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Backend  (app/main.py)  — port 8000                    │
│  POST /upload  →  enqueue job to Redis                          │
│  GET  /status/{id}  →  RQ job status                           │
│  GET  /progress/{id}  →  real FFmpeg progress %                 │
│  GET  /download/{id}  →  serve output file                      │
│  GET  /jobs/{id}/metrics  →  KPI data                          │
│  GET  /health  →  liveness check                                │
└────────────────────┬────────────────────────────────────────────┘
                     │ RQ enqueue
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Redis Queue  (transcode queue)  — port 6379                    │
└────────────────────┬────────────────────────────────────────────┘
                     │ job dequeue
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  RQ Worker  (app/worker.py)                                     │
│  - Calls app/tasks.py → transcode_video()                       │
│  - Runs FFmpeg subprocess with -progress pipe:1                 │
│  - Writes progress to metrics/progress_<id>.json                │
│  - Writes KPI record to metrics/jobs.jsonl                      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
              outputs/<id>_output.mp4
```

---

## 2. Prerequisites

### System packages

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg redis-server python3-venv python3-pip curl
```

Verify:

```bash
ffmpeg -version
ffprobe -version
redis-cli ping        # should return PONG
python3 --version     # 3.9+
```

---

## 3. Installation & Setup

### Option A — Automated (recommended)

```bash
bash setup.sh
```

This script will:
- Install system packages (ffmpeg, redis-server, python3-venv)
- Create `.venv` Python virtual environment
- Install all pip dependencies from `requirements.txt`
- Create runtime directories (`uploads/`, `outputs/`, `logs/`, `metrics/`)
- Start Redis if not already running
- Write `.env` configuration file
- Generate `start_api.sh` and `start_worker.sh` convenience scripts

---

### Option B — Manual

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create runtime directories
mkdir -p uploads outputs logs metrics

# 4. Start Redis
sudo systemctl start redis-server
# OR
redis-server --daemonize yes --logfile redis.log
```

---

## 4. Starting the Application

Open **three separate terminals** in the project directory.

### Terminal 1 — Redis (if not running via systemd)

```bash
redis-server --daemonize yes --logfile redis.log
redis-cli ping    # verify: PONG
```

### Terminal 2 — Worker

```bash
source .venv/bin/activate
python -m app.worker
```

Expected output:
```
*** Listening on transcode...
```

Or use the generated script:
```bash
bash start_worker.sh
```

### Terminal 3 — API Server

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Or use the generated script:
```bash
bash start_api.sh
```

### Verify everything is running

```bash
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok","redis":"connected"}
```

---

## 5. Using the Web UI

1. Open `index.html` in your browser (double-click or `xdg-open index.html`)
2. Click **Choose Video File** and select a video
3. Select a **Transcoding Preset**:
   - `4K High` / `4K Balanced` → 3840×2160, CRF 18, slow preset
   - `1080p` → 1920×1080, CRF 23, medium preset
   - `720p` → 1280×720, CRF 28, fast preset
   - `480p` → 854×480, CRF 30, fast preset
4. Click **Start Transcoding**
5. Watch the real-time progress bar update
6. Click **Download Video** when complete

> **Note:** The API base URL is set to `http://127.0.0.1:8000` by default.  
> For OpenStack deployment, set `window.API_BASE = "http://<VM1_IP>:8000"` before loading `script.js`.

---

## 6. API Reference

### `GET /health`

Check API and Redis connectivity.

```bash
curl http://127.0.0.1:8000/health
```

Response:
```json
{"status": "ok", "redis": "connected"}
```

---

### `POST /upload`

Upload a video file and queue a transcoding job.

**Form fields:**
- `file` (required) — video file (multipart)
- `preset` (optional, default `1080p`) — one of: `4k`, `1080p`, `720p`, `480p`

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "file=@/path/to/video.mp4" \
  -F "preset=1080p"
```

Response:
```json
{"job_id": "abc123...", "status": "queued", "preset": "1080p"}
```

---

### `GET /status/{job_id}`

Get the RQ job status.

```bash
curl http://127.0.0.1:8000/status/<job_id>
```

Response:
```json
{"job_id": "abc123...", "status": "finished", "result": {"status": "completed", "output": "outputs/abc123_output.mp4"}}
```

Possible status values: `queued`, `started`, `finished`, `failed`, `deferred`, `scheduled`

---

### `GET /progress/{job_id}`

Get real-time FFmpeg transcoding progress.

```bash
curl http://127.0.0.1:8000/progress/<job_id>
```

Response:
```json
{"job_id": "abc123...", "progress": 67.4, "status": "processing", "updated_at": 1711234567.89}
```

---

### `GET /download/{job_id}`

Download the transcoded output file.

```bash
curl -O -J http://127.0.0.1:8000/download/<job_id>
# OR
wget http://127.0.0.1:8000/download/<job_id>
```

Returns the MP4 file as a binary download.

---

### `GET /jobs/{job_id}/metrics`

Retrieve KPI metrics for a specific job.

```bash
curl http://127.0.0.1:8000/jobs/<job_id>/metrics
```

Response:
```json
{
  "job_id": "abc123...",
  "metrics": [{
    "timestamp": "2026-03-24T09:10:19Z",
    "job_id": "abc123...",
    "preset": "1080p",
    "status": "completed",
    "queue_wait_seconds": 0.038,
    "processing_time_seconds": 3.723,
    "latency_seconds": 4.046,
    "cpu_usage_percent_before": 100.0,
    "cpu_usage_percent_after": 68.8,
    "throughput_jobs_per_min": 16.12
  }]
}
```

---

## 7. Testing with curl

### Full end-to-end test

```bash
# Step 1: Upload and get job_id
JOB=$(curl -s -X POST http://127.0.0.1:8000/upload \
  -F "file=@videos/sample_video_1093662-hd_1920_1080_30fps.mp4" \
  -F "preset=720p")
echo $JOB
JOB_ID=$(echo $JOB | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# Step 2: Poll progress until done
while true; do
  PROG=$(curl -s http://127.0.0.1:8000/progress/$JOB_ID)
  echo $PROG
  STATUS=$(echo $PROG | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  if [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]]; then break; fi
  sleep 2
done

# Step 3: Check final status
curl -s http://127.0.0.1:8000/status/$JOB_ID | python3 -m json.tool

# Step 4: Download output
curl -O -J http://127.0.0.1:8000/download/$JOB_ID

# Step 5: View KPI metrics
curl -s http://127.0.0.1:8000/jobs/$JOB_ID/metrics | python3 -m json.tool
```

### Edge case tests

```bash
# Missing file → expect HTTP 422
curl -s -X POST http://127.0.0.1:8000/upload -F "preset=1080p"

# Invalid job_id → expect HTTP 404
curl -s http://127.0.0.1:8000/status/invalid-id-000
curl -s http://127.0.0.1:8000/download/invalid-id-000
curl -s http://127.0.0.1:8000/jobs/invalid-id-000/metrics

# Unknown job_id progress → returns 0% gracefully
curl -s http://127.0.0.1:8000/progress/invalid-id-000
```

---

## 8. KPI Metrics & Viewer

### Metrics files

| File | Description |
|------|-------------|
| `metrics/jobs.jsonl` | One JSON record per job (append-only) |
| `metrics/progress_<id>.json` | Live progress for each job |
| `metrics/kpi_export.csv` | CSV export (generated on demand) |
| `logs/app.log` | Application log (INFO/ERROR) |
| `worker.log` | RQ worker output |
| `api.log` | Uvicorn API output |

### KPI fields per job

| Field | Description |
|-------|-------------|
| `processing_time_seconds` | FFmpeg wall-clock duration |
| `latency_seconds` | Upload → result end-to-end time |
| `queue_wait_seconds` | Time spent waiting in Redis queue |
| `cpu_usage_percent_before` | CPU % sampled before FFmpeg starts |
| `cpu_usage_percent_after` | CPU % sampled after FFmpeg finishes |
| `throughput_jobs_per_min` | `60 / processing_time` |

### Using kpi_viewer.py

```bash
source .venv/bin/activate

# Show full KPI summary table
python kpi_viewer.py

# Filter by preset
python kpi_viewer.py --preset 720p
python kpi_viewer.py --preset 1080p
python kpi_viewer.py --preset 4k

# Export to CSV
python kpi_viewer.py --csv

# Use a custom metrics file
python kpi_viewer.py --file /path/to/custom/jobs.jsonl

# Combine options
python kpi_viewer.py --preset 1080p --csv
```

### Sample KPI output

```
================================================================================
  4K VIDEO TRANSCODER — KPI SUMMARY
================================================================================
  Total jobs      : 4
  Completed       : 3
  Failed          : 1

  ── Processing Time (seconds) ──────────────────────────────────────────────
     Min     : 1.132s
     Max     : 6.275s
     Average : 3.710s

  ── Throughput (jobs/minute) ────────────────────────────────────────────────
     Min     : 9.5615
     Max     : 53.0234
     Average : 26.2338

  ── Per-Preset Breakdown ────────────────────────────────────────────────────
     1080p        : 1 job(s), avg 3.723s
     480p         : 1 job(s), avg 1.132s
     720p         : 1 job(s), avg 6.275s
================================================================================
```

### KPI comparison table (for OpenStack demo)

Run the same video on different configurations and record:

| Setup | Preset | Processing Time | Throughput (j/min) |
|-------|--------|----------------|-------------------|
| Local | 1080p  | 3.7s           | 16.1              |
| VM-1 worker | 720p | ~90s      | ~0.67             |
| VM-1 + VM-2 workers | 720p | ~55s | ~1.09          |

---

## 9. Project File Structure

```
4k-video-transcoder/
├── app/
│   ├── __init__.py          # Python package marker
│   ├── main.py              # FastAPI application + all endpoints
│   ├── job_queue.py         # Redis connection + RQ queue setup
│   ├── worker.py            # RQ worker entry point
│   ├── tasks.py             # FFmpeg transcoding logic + KPI logging
│   └── logger.py            # Structured logging to logs/app.log
├── uploads/                 # Uploaded source videos (runtime)
├── outputs/                 # Transcoded output videos (runtime)
├── logs/
│   └── app.log              # Application log
├── metrics/
│   ├── jobs.jsonl           # KPI records (JSON lines)
│   ├── kpi_export.csv       # CSV export (generated by kpi_viewer.py)
│   └── progress_<id>.json   # Per-job real-time progress
├── videos/                  # Sample test videos
├── index.html               # Web UI
├── script.js                # Frontend logic (API calls, progress polling)
├── styles.css               # UI styles
├── kpi_viewer.py            # CLI KPI analytics tool
├── requirements.txt         # Pinned Python dependencies
├── setup.sh                 # Automated setup script
├── start_api.sh             # Generated: start API server
├── start_worker.sh          # Generated: start RQ worker
├── .env                     # Environment configuration
├── README.md                # Quick-start reference
├── MANUAL.md                # This file
└── TODO.md                  # Development task tracker
```

---

## 10. OpenStack DevStack Deployment

### Topology

```
Internet
    │
    ▼
[VM-1: API + Redis]  ←──── private network ────→  [VM-2: Worker]
  - FastAPI :8000                                    - RQ Worker
  - Redis   :6379 (internal only)                   - FFmpeg
  - Floating IP (public)                            - No public IP needed
```

### VM-1 Setup (API + Redis)

```bash
# SSH into VM-1
ssh ubuntu@<VM1_FLOATING_IP>

# Clone repo
git clone <your-repo-url>
cd 4k-video-transcoder

# Run setup
bash setup.sh

# Start Redis (already done by setup.sh)
# Start API
bash start_api.sh &
```

### VM-2 Setup (Worker)

```bash
# SSH into VM-2
ssh ubuntu@<VM2_PRIVATE_IP>

# Clone repo
git clone <your-repo-url>
cd 4k-video-transcoder

# Run setup (installs ffmpeg + venv + deps)
bash setup.sh

# Edit .env to point to VM-1's Redis
sed -i "s/REDIS_HOST=localhost/REDIS_HOST=<VM1_PRIVATE_IP>/" .env

# Start worker
bash start_worker.sh &
```

### OpenStack Security Groups

| Rule | Direction | Port | Source |
|------|-----------|------|--------|
| API  | Ingress   | 8000 | 0.0.0.0/0 |
| Redis | Ingress  | 6379 | VM-2 private IP only |
| SSH  | Ingress   | 22   | your IP |

### Scale workers horizontally

```bash
# On VM-2 (or VM-3), start additional workers:
bash start_worker.sh &
bash start_worker.sh &
# Each worker picks jobs from the same Redis queue
```

---

## 11. Troubleshooting

### Redis not responding

```bash
redis-cli ping
# If no PONG:
sudo systemctl restart redis-server
# OR
redis-server --daemonize yes --logfile redis.log
```

### Worker not picking up jobs

```bash
# Check worker is running
ps aux | grep "app.worker"

# Check Redis queue
redis-cli llen rq:queue:transcode

# Restart worker
source .venv/bin/activate
python -m app.worker
```

### FFmpeg not found

```bash
which ffmpeg
which ffprobe
# If missing:
sudo apt-get install -y ffmpeg
```

### API returns 500 on upload

```bash
# Check API log
tail -50 api.log
tail -50 logs/app.log

# Check worker log
tail -50 worker.log
```

### Progress stuck at 0%

```bash
# Check if worker is running and processing
tail -f worker.log

# Check progress file
ls metrics/progress_*.json
cat metrics/progress_<job_id>.json
```

### View all KPI records raw

```bash
cat metrics/jobs.jsonl | python3 -m json.tool
# OR line by line:
while IFS= read -r line; do echo "$line" | python3 -m json.tool; echo "---"; done < metrics/jobs.jsonl
```

### Reset all data (clean slate)

```bash
rm -rf uploads/* outputs/* metrics/* logs/*
redis-cli flushdb
