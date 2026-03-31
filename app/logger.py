import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

LOG_DIR = "logs"
METRICS_DIR = "metrics"
APP_LOG_FILE = os.path.join(LOG_DIR, "app.log")
JOBS_METRICS_FILE = os.path.join(METRICS_DIR, "jobs.jsonl")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(METRICS_DIR, exist_ok=True)

logging.basicConfig(
    filename=APP_LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("video-transcoder")


def log_info(message: str) -> None:
    logger.info(message)


def log_error(message: str) -> None:
    logger.error(message)


def write_job_metric(payload: Dict[str, Any]) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **payload,
    }
    with open(JOBS_METRICS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
