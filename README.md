# 4K Video Transcoder (FastAPI + FFmpeg + Redis + RQ)

This project provides a 4K-capable video transcoding pipeline with:
- FastAPI backend
- Redis queue + RQ worker
- FFmpeg processing
- Real progress tracking
- KPI/performance logging for later analytics
- Existing frontend integrated through `script.js`

## Architecture

User Upload → Frontend UI → FastAPI API → Redis Queue → Worker (FFmpeg) → Output Storage → Download

## Project Structure

```text
.
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── job_queue.py
│   ├── worker.py
│   ├── tasks.py
│   └── logger.py
├── uploads/              # runtime — uploaded source videos
├── outputs/              # runtime — transcoded output videos
├── logs/                 # runtime — app.log
├── metrics/              # runtime — jobs.jsonl, progress_<id>.json, kpi_export.csv
├── index.html
├── script.js
├── styles.css
├── kpi_viewer.py
├── requirements.txt
└── README.md
```

## Prerequisites (Linux)

Install system packages:

```bash
sudo apt update
sudo apt install -y ffmpeg redis-server python3-venv
```

## Python Setup

Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Locally

1. Start Redis:
```bash
redis-server
```

2. Start worker (new terminal):
```bash
source .venv/bin/activate
python -m app.worker
```

3. Start API (new terminal):
```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Open frontend (`index.html`) in browser and use it.

Default API base in frontend:
- `http://127.0.0.1:8000`
- Override by defining `window.API_BASE` before loading `script.js` if needed.

## API Endpoints

- `GET /health`  
  Health check + Redis connectivity

- `POST /upload` (multipart form)
  - `file`: video file
  - `preset`: one of `4k`, `1080p`, `720p`, `480p`
  - returns `job_id`

- `GET /status/{job_id}`  
  Queue/job status from RQ

- `GET /progress/{job_id}`  
  Real progress from worker-written JSON

- `GET /download/{job_id}`  
  Download transcoded file once complete

- `GET /jobs/{job_id}/metrics`  
  KPI/metrics entries for the job

## Preset Mapping

Frontend values map to backend presets:
- `4k-high` / `4k-balanced` → `4k`
- `1080p` → `1080p`
- `720p` → `720p`
- `480p` → `480p`

## KPI & Logging

### App logs
- `logs/app.log`

### Job KPIs (JSON lines)
- `metrics/jobs.jsonl`

Each record includes:
- `job_id`
- `preset`
- `status`
- `queue_wait_seconds`
- `processing_time_seconds`
- `latency_seconds`
- `cpu_usage_percent_before`
- `cpu_usage_percent_after`
- `throughput_jobs_per_min`
- `input_path`, `output_path`
- error details on failure

### Progress files
- `metrics/progress_<job_id>.json`

## DevStack Deployment Plan (After local verification)

Recommended minimal production-style topology:
- VM-1: FastAPI + Redis
- VM-2: Worker (FFmpeg)

High-level:
1. Create private network and attach both VMs
2. Attach floating IP only to VM-1
3. On VM-1 run Redis + API
4. On VM-2 run worker with `REDIS_HOST=<vm1_private_ip>`
5. Open security group ports:
   - 8000 public to VM-1
   - 6379 private/internal only

## Notes

- Ensure FFmpeg and ffprobe are available in `PATH`.
- Start with local stable workflow, then deploy to DevStack.
- For scaling, run additional workers on same/different worker VMs.
