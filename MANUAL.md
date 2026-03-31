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
Internet / Browser
        │
        ▼  HTTP :8000
┌───────────────────────────┐
│  VM-1: transcoder-api     │  ← Floating IP (public access)
│  - FastAPI      :8000     │
│  - Redis        :6379     │
│  - NFS Server   :2049     │  ← exports uploads/ outputs/ metrics/
└──────────┬────────────────┘
           │ private network (10.10.0.0/24)
           │ NFS mounts (NFSv4)
           ▼
┌───────────────────────────┐
│  VM-2: transcoder-worker  │  ← No public IP
│  - RQ Worker              │
│  - FFmpeg                 │
│  - NFS Client             │  ← mounts uploads/ outputs/ metrics/ from VM-1
└───────────────────────────┘
```

**Why NFS shared storage?**  
The worker on VM-2 needs to read uploaded video files and write transcoded outputs.
Without NFS, VM-2 would look for files in its own local filesystem and fail — uploaded
files only exist on VM-1. NFS mounts VM-1's `uploads/`, `outputs/`, and `metrics/`
directories onto VM-2 at the same paths, making the distributed setup transparent to
the application code.

---

### Phase 1 — Install DevStack (Automated)

Run on the **host machine** (not inside a VM):

```bash
sudo bash devstack_install.sh
```

**What it does:**
1. Checks OS, disk space (≥60 GB), and RAM (≥8 GB)
2. Installs prerequisites (git, python3, curl)
3. Creates the `stack` user required by DevStack
4. Clones DevStack (`stable/2024.2`) from OpenDev
5. Auto-detects host IP and writes `local.conf`
6. Pre-configures MySQL root auth for DevStack compatibility
7. Runs `stack.sh` (takes 20–40 minutes)
8. Verifies the installation

> **Note:** The Ubuntu 22.04 cloud image (`jammy-server-cloudimg-amd64`) is
> automatically downloaded by DevStack via `IMAGE_URLS` in `local.conf`.
> You do **not** need to upload it manually.

---

### Phase 2 — Deploy App to OpenStack (Automated)

```bash
# Source OpenStack credentials first
source /opt/stack/devstack/openrc admin admin

# Run from the project root directory
bash openstack_deploy.sh
```

**What it does:**
1. Verifies OpenStack credentials
2. Checks/uploads the Ubuntu 22.04 image to Glance
3. Creates SSH keypair (`transcoder-key`)
4. Creates private network `transcoder-net` (10.10.0.0/24) + router
5. Creates security groups with all required rules (see table below)
6. Launches VM-1 (`transcoder-api`) with cloud-init that:
   - Installs app, Redis, NFS server
   - Configures Redis for remote access
   - Exports `uploads/`, `outputs/`, `metrics/` via NFS
   - Starts `transcoder-api` systemd service
7. Assigns a floating IP to VM-1
8. Launches VM-2 (`transcoder-worker`) with cloud-init that:
   - Installs app, FFmpeg, NFS client
   - Waits for VM-1 NFS server to be ready
   - Mounts VM-1's shared directories via NFSv4
   - Persists mounts in `/etc/fstab`
   - Starts `transcoder-worker` systemd service
9. Updates `config.js` with the floating IP
10. Verifies NFS mounts on VM-2

---

### Accessing the Application

Once deployment completes (allow ~3 minutes for cloud-init):

| Access Method | URL / Command |
|---------------|---------------|
| **Web UI (browser)** | `http://<FLOATING_IP>:8000/` |
| **Health check** | `curl http://<FLOATING_IP>:8000/health` |
| **SSH into VM-1** | `ssh -i ~/.ssh/transcoder-key ubuntu@<FLOATING_IP>` |
| **SSH into VM-2** | `ssh -i ~/.ssh/transcoder-key -J ubuntu@<FLOATING_IP> ubuntu@<VM2_PRIVATE_IP>` |

> Replace `<FLOATING_IP>` with the floating IP shown at the end of `openstack_deploy.sh`.
> Example: `http://172.24.4.59:8000/`

---

### OpenStack Security Groups

**`transcoder-api-sg`** (VM-1):

| Protocol | Port | Source | Purpose |
|----------|------|--------|---------|
| TCP | 22 | 0.0.0.0/0 | SSH access |
| TCP | 8000 | 0.0.0.0/0 | FastAPI (public) |
| TCP | 6379 | 10.10.0.0/24 | Redis (internal only) |
| TCP | 2049 | 10.10.0.0/24 | NFS server (internal only) |
| UDP | 2049 | 10.10.0.0/24 | NFS server (internal only) |
| TCP | 111 | 10.10.0.0/24 | rpcbind (internal only) |
| ICMP | — | 0.0.0.0/0 | Ping |

**`transcoder-worker-sg`** (VM-2):

| Protocol | Port | Source | Purpose |
|----------|------|--------|---------|
| TCP | 22 | 0.0.0.0/0 | SSH access |
| ICMP | — | 0.0.0.0/0 | Ping |

---

### Manual VM-1 Setup (API + Redis + NFS Server)

```bash
# SSH into VM-1
ssh -i ~/.ssh/transcoder-key ubuntu@<FLOATING_IP>

# Clone repo
git clone https://github.com/inz01/4k-video-transcoder.git
cd 4k-video-transcoder

# Copy VM-1 env config BEFORE setup (enables Redis remote binding)
cp .env.vm1 .env

# Run setup (installs venv, deps, dirs, configures Redis)
bash setup.sh

# Set up NFS server
sudo apt-get install -y nfs-kernel-server
sudo tee /etc/exports <<EOF
/home/ubuntu/4k-video-transcoder/uploads 10.10.0.0/24(rw,sync,no_subtree_check,no_root_squash)
/home/ubuntu/4k-video-transcoder/outputs 10.10.0.0/24(rw,sync,no_subtree_check,no_root_squash)
/home/ubuntu/4k-video-transcoder/metrics 10.10.0.0/24(rw,sync,no_subtree_check,no_root_squash)
EOF
sudo exportfs -ra
sudo systemctl enable --now nfs-kernel-server

# Install and start API systemd service
sudo cp systemd/transcoder-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now transcoder-api

# Verify
sudo systemctl status transcoder-api
curl http://localhost:8000/health
```

---

### Manual VM-2 Setup (Worker + NFS Client)

```bash
# SSH into VM-2 (via VM-1 jump host)
ssh -i ~/.ssh/transcoder-key -J ubuntu@<FLOATING_IP> ubuntu@<VM2_PRIVATE_IP>

# Clone repo
git clone https://github.com/inz01/4k-video-transcoder.git
cd 4k-video-transcoder

# Copy VM-2 env config (points Redis to VM-1)
cp .env.vm2 .env
sed -i "s/<VM1_PRIVATE_IP>/<ACTUAL_VM1_PRIVATE_IP>/" .env

# Run setup (installs venv, deps, dirs)
bash setup.sh

# Set up NFS client
sudo apt-get install -y nfs-common

# Wait for VM-1 NFS to be ready, then mount
sudo mount -t nfs4 <VM1_PRIVATE_IP>:/home/ubuntu/4k-video-transcoder/uploads  /home/ubuntu/4k-video-transcoder/uploads
sudo mount -t nfs4 <VM1_PRIVATE_IP>:/home/ubuntu/4k-video-transcoder/outputs  /home/ubuntu/4k-video-transcoder/outputs
sudo mount -t nfs4 <VM1_PRIVATE_IP>:/home/ubuntu/4k-video-transcoder/metrics  /home/ubuntu/4k-video-transcoder/metrics

# Persist mounts
echo "<VM1_PRIVATE_IP>:/home/ubuntu/4k-video-transcoder/uploads  /home/ubuntu/4k-video-transcoder/uploads  nfs4  defaults,_netdev  0  0" | sudo tee -a /etc/fstab
echo "<VM1_PRIVATE_IP>:/home/ubuntu/4k-video-transcoder/outputs  /home/ubuntu/4k-video-transcoder/outputs  nfs4  defaults,_netdev  0  0" | sudo tee -a /etc/fstab
echo "<VM1_PRIVATE_IP>:/home/ubuntu/4k-video-transcoder/metrics  /home/ubuntu/4k-video-transcoder/metrics  nfs4  defaults,_netdev  0  0" | sudo tee -a /etc/fstab

# Install and start worker systemd service
sudo cp systemd/transcoder-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now transcoder-worker

# Verify
sudo systemctl status transcoder-worker
mount | grep nfs
```

---

### Scale Workers Horizontally

```bash
# Launch additional worker VMs (VM-3, VM-4, etc.) with the same setup as VM-2.
# Each worker connects to the same Redis queue on VM-1 and mounts the same NFS shares.
# No changes to VM-1 or the API are needed.

# On each additional worker VM:
bash start_worker.sh &
# Each worker picks jobs from the same Redis queue on VM-1
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

### NFS mount fails on VM-2

```bash
# Check VM-1 NFS server is running
ssh -i ~/.ssh/transcoder-key ubuntu@<FLOATING_IP> \
    "sudo systemctl status nfs-kernel-server && sudo exportfs -v"

# Check NFS security group rules exist on VM-1
source /opt/stack/devstack/openrc admin admin
openstack security group rule list transcoder-api-sg | grep -E "2049|111"

# Manually retry mount on VM-2
ssh -i ~/.ssh/transcoder-key -J ubuntu@<FLOATING_IP> ubuntu@<VM2_PRIVATE_IP>
showmount -e <VM1_PRIVATE_IP>          # should list 3 exports
sudo mount -t nfs4 <VM1_PRIVATE_IP>:/home/ubuntu/4k-video-transcoder/uploads \
    /home/ubuntu/4k-video-transcoder/uploads
```

### Worker jobs fail with "file not found"

This means NFS mounts are not active on VM-2. The worker cannot read uploaded files.

```bash
# On VM-2 — check mounts
mount | grep nfs
# If empty, remount:
sudo mount -a

# Verify the uploaded file is visible from VM-2
ls /home/ubuntu/4k-video-transcoder/uploads/
# Should show the same files as VM-1's uploads/ directory
```

### Redis connection refused from VM-2

```bash
# On VM-1 — check Redis is listening on all interfaces
redis-cli config get bind
# Should include 0.0.0.0 or the private IP

# If only bound to 127.0.0.1, check .env has REDIS_BIND_ALL=true
cat /home/ubuntu/4k-video-transcoder/.env

# Manually reconfigure Redis
sudo sed -i "s/bind 127.0.0.1/bind 0.0.0.0/" /etc/redis/redis.conf
sudo systemctl restart redis-server

# Verify from VM-2
redis-cli -h <VM1_PRIVATE_IP> -p 6379 ping   # should return PONG
```

### API health check fails after deployment

```bash
# Wait 3–5 minutes for cloud-init to finish, then:
ssh -i ~/.ssh/transcoder-key ubuntu@<FLOATING_IP>
sudo cloud-init status
cat /home/ubuntu/setup.log
sudo systemctl status transcoder-api
curl http://localhost:8000/health
```

### Check cloud-init setup logs

```bash
# VM-1 setup log
ssh -i ~/.ssh/transcoder-key ubuntu@<FLOATING_IP> "cat /home/ubuntu/setup.log"

# VM-2 setup log
ssh -i ~/.ssh/transcoder-key -J ubuntu@<FLOATING_IP> ubuntu@<VM2_PRIVATE_IP> \
    "cat /home/ubuntu/setup.log"
```

### Reset and redeploy VMs

```bash
source /opt/stack/devstack/openrc admin admin

# Delete VMs
openstack server delete transcoder-api transcoder-worker

# Delete floating IPs
openstack floating ip list
openstack floating ip delete <id>

# Re-run deployment
bash openstack_deploy.sh
```

### Reset all data (clean slate)

```bash
rm -rf uploads/* outputs/* metrics/* logs/*
redis-cli flushdb
