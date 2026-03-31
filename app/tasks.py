import json
import os
import subprocess
import time
from typing import Dict, Tuple

import psutil

from app.logger import log_error, log_info, write_job_metric

METRICS_DIR = "metrics"
OUTPUT_DIR = "outputs"

os.makedirs(METRICS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def progress_file_path(job_id: str) -> str:
    return os.path.join(METRICS_DIR, f"progress_{job_id}.json")


def write_progress(job_id: str, progress: float, status: str = "processing") -> None:
    payload = {
        "job_id": job_id,
        "progress": round(max(0.0, min(progress, 100.0)), 2),
        "status": status,
        "updated_at": time.time(),
    }
    with open(progress_file_path(job_id), "w", encoding="utf-8") as f:
        json.dump(payload, f)


def get_duration_seconds(input_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw = result.stdout.strip()
        if not raw or raw.upper() == "N/A":
            log_info(f"ffprobe returned N/A duration for {input_path}, falling back to 0")
            return 0.0
        return float(raw)
    except (subprocess.CalledProcessError, ValueError) as exc:
        log_error(f"ffprobe duration failed for {input_path}: {exc}")
        return 0.0


def preset_to_params(preset: str) -> Tuple[str, str, str]:
    mapping: Dict[str, Tuple[str, str, str]] = {
        "4k": ("3840:2160", "18", "slow"),
        "1080p": ("1920:1080", "23", "medium"),
        "720p": ("1280:720", "28", "fast"),
        "480p": ("854:480", "30", "fast"),
    }
    return mapping.get(preset, mapping["1080p"])


def transcode_video(
    input_path: str,
    output_path: str,
    job_id: str,
    preset: str = "1080p",
    enqueued_at: float = 0.0,
) -> Dict[str, str]:
    process_start_time = time.time()
    queue_wait_seconds = max(0.0, process_start_time - enqueued_at) if enqueued_at else 0.0

    write_progress(job_id, 0.0, status="processing")
    log_info(f"job={job_id} preset={preset} started input={input_path} output={output_path}")

    cpu_before = psutil.cpu_percent(interval=None)
    duration_seconds = 0.0

    try:
        duration_seconds = get_duration_seconds(input_path)
        scale, crf, ffpreset = preset_to_params(preset)

        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-vf",
            f"scale={scale}",
            "-c:v",
            "libx264",
            "-crf",
            crf,
            "-preset",
            ffpreset,
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-progress",
            "pipe:1",
            "-nostats",
            "-y",
            output_path,
        ]

        ffmpeg_start = time.time()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )

        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if line.startswith("out_time_ms="):
                    raw_val = line.split("=", 1)[1].strip()
                    if raw_val and raw_val.upper() != "N/A":
                        try:
                            out_time_ms = int(raw_val)
                            current_seconds = out_time_ms / 1_000_000
                            progress = (current_seconds / duration_seconds) * 100 if duration_seconds > 0 else 0
                            write_progress(job_id, progress, status="processing")
                        except (ValueError, ZeroDivisionError):
                            pass

        return_code = process.wait()

        # Drain stderr for diagnostics on failure
        stderr_output = ""
        if process.stderr is not None:
            stderr_output = process.stderr.read()
        ffmpeg_end = time.time()

        if return_code != 0:
            raise RuntimeError(f"ffmpeg exited with code {return_code}: {stderr_output[:500]}")

        total_processing_seconds = ffmpeg_end - ffmpeg_start
        cpu_after = psutil.cpu_percent(interval=None)
        throughput_jobs_per_min = 60.0 / total_processing_seconds if total_processing_seconds > 0 else 0.0

        write_progress(job_id, 100.0, status="completed")
        write_job_metric(
            {
                "job_id": job_id,
                "preset": preset,
                "status": "completed",
                "input_path": input_path,
                "output_path": output_path,
                "queue_wait_seconds": round(queue_wait_seconds, 3),
                "processing_time_seconds": round(total_processing_seconds, 3),
                "latency_seconds": round(time.time() - enqueued_at, 3) if enqueued_at else round(total_processing_seconds, 3),
                "cpu_usage_percent_before": cpu_before,
                "cpu_usage_percent_after": cpu_after,
                "throughput_jobs_per_min": round(throughput_jobs_per_min, 4),
            }
        )
        log_info(
            f"job={job_id} completed processing_time={total_processing_seconds:.3f}s "
            f"queue_wait={queue_wait_seconds:.3f}s"
        )
        return {"status": "completed", "output": output_path}

    except Exception as exc:
        write_progress(job_id, 0.0, status="failed")
        write_job_metric(
            {
                "job_id": job_id,
                "preset": preset,
                "status": "failed",
                "input_path": input_path,
                "output_path": output_path,
                "queue_wait_seconds": round(queue_wait_seconds, 3),
                "error": str(exc),
                "duration_seconds": duration_seconds,
            }
        )
        log_error(f"job={job_id} failed error={exc}")
        return {"status": "failed", "error": str(exc)}
