import json
import os
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis
from rq.job import Job

from app.logger import log_error, log_info
from app.job_queue import q, redis_conn
from app.tasks import progress_file_path, transcode_video

app = FastAPI(title="4K Video Transcoder API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
METRICS_DIR = "metrics"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(METRICS_DIR, exist_ok=True)


def sanitize_filename(name: str) -> str:
    return os.path.basename(name).replace(" ", "_")


@app.get("/health")
def health():
    try:
        redis_conn.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "degraded", "redis": str(exc)})


VALID_PRESETS = {"4k", "1080p", "720p", "480p"}


@app.post("/upload")
async def upload_video(file: UploadFile = File(...), preset: str = Form("1080p")):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Invalid file")

    if preset not in VALID_PRESETS:
        raise HTTPException(status_code=400, detail=f"Invalid preset '{preset}'. Must be one of: {', '.join(sorted(VALID_PRESETS))}")

    job_id = str(uuid.uuid4())
    safe_name = sanitize_filename(file.filename)
    ext = os.path.splitext(safe_name)[1].lower() or ".mp4"

    input_path = os.path.join(UPLOAD_DIR, f"{job_id}_{safe_name}")
    output_path = os.path.join(OUTPUT_DIR, f"{job_id}_output{ext}")

    try:
        content = await file.read()
        with open(input_path, "wb") as f:
            f.write(content)

        enqueued_at = time.time()
        job = q.enqueue(
            transcode_video,
            input_path,
            output_path,
            job_id,
            preset,
            enqueued_at,
            job_id=job_id,
            job_timeout=3600,
        )
        log_info(f"job={job_id} queued preset={preset} input={input_path}")
        return {"job_id": job.id, "status": "queued", "preset": preset}
    except Exception as exc:
        log_error(f"job={job_id} upload_failed error={exc}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")


@app.get("/status/{job_id}")
def get_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", "6379"))))
        status = job.get_status()
        status_str = status.value if hasattr(status, "value") else str(status)
        return {
            "job_id": job_id,
            "status": status_str,
            "result": job.result if job.is_finished else None,
        }
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {exc}")


@app.get("/progress/{job_id}")
def get_progress(job_id: str):
    path = progress_file_path(job_id)
    if not os.path.exists(path):
        return {"job_id": job_id, "progress": 0.0, "status": "queued"}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/download/{job_id}")
def download_video(job_id: str):
    candidates = [f for f in os.listdir(OUTPUT_DIR) if f.startswith(f"{job_id}_output")]
    if not candidates:
        raise HTTPException(status_code=404, detail="Output not ready")

    output_file = os.path.join(OUTPUT_DIR, candidates[0])
    return FileResponse(output_file, filename=os.path.basename(output_file))


@app.get("/jobs/{job_id}/metrics")
def get_job_metrics(job_id: str):
    metrics_file = os.path.join(METRICS_DIR, "jobs.jsonl")
    if not os.path.exists(metrics_file):
        raise HTTPException(status_code=404, detail="Metrics file not found")

    matched = []
    with open(metrics_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                if row.get("job_id") == job_id:
                    matched.append(row)
            except json.JSONDecodeError:
                continue

    if not matched:
        raise HTTPException(status_code=404, detail="No metrics found for this job")

    return {"job_id": job_id, "metrics": matched}


@app.get("/metrics")
def get_all_metrics():
    """Return all job metrics records from jobs.jsonl — used by kpi_compare.py."""
    metrics_file = os.path.join(METRICS_DIR, "jobs.jsonl")
    if not os.path.exists(metrics_file):
        return {"records": [], "count": 0}

    records = []
    with open(metrics_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return {"records": records, "count": len(records)}


# ── Serve frontend static files ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend not found")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/config.js")
def serve_config():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.js")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="config.js not found")
    return FileResponse(path, media_type="application/javascript")


@app.get("/script.js")
def serve_script():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "script.js")
    return FileResponse(path, media_type="application/javascript")


@app.get("/styles.css")
def serve_styles():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "styles.css")
    return FileResponse(path, media_type="text/css")
