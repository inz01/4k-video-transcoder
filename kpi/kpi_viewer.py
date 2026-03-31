#!/usr/bin/env python3
"""
KPI Viewer — reads metrics/jobs.jsonl and displays performance analytics.
Usage:
    python kpi_viewer.py                  # summary table
    python kpi_viewer.py --preset 1080p   # filter by preset
    python kpi_viewer.py --json           # raw JSON output
    python kpi_viewer.py --csv            # CSV export
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

METRICS_FILE = os.path.join("metrics", "jobs.jsonl")

COLS = [
    ("job_id",                    "Job ID",                  20),
    ("timestamp",                 "Timestamp (UTC)",         26),
    ("preset",                    "Preset",                   9),
    ("status",                    "Status",                  10),
    ("queue_wait_seconds",        "Queue Wait (s)",          14),
    ("processing_time_seconds",   "Proc. Time (s)",          14),
    ("latency_seconds",           "Latency (s)",             12),
    ("cpu_usage_percent_before",  "CPU Before (%)",          14),
    ("cpu_usage_percent_after",   "CPU After (%)",           13),
    ("throughput_jobs_per_min",   "Throughput (j/min)",      19),
]


def load_metrics(preset_filter: Optional[str] = None, metrics_file: str = METRICS_FILE) -> List[Dict[str, Any]]:
    if not os.path.exists(metrics_file):
        print(f"[ERROR] Metrics file not found: {metrics_file}")
        sys.exit(1)

    records = []
    with open(metrics_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if preset_filter and record.get("preset") != preset_filter:
                    continue
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping malformed line: {e}")
    return records


def fmt(value: Any, width: int) -> str:
    s = str(value) if value is not None else "N/A"
    if len(s) > width:
        s = s[: width - 1] + "…"
    return s.ljust(width)


def print_table(records: List[Dict[str, Any]]) -> None:
    header = " | ".join(fmt(label, w) for _, label, w in COLS)
    sep = "-+-".join("-" * w for _, _, w in COLS)
    print(header)
    print(sep)
    for r in records:
        row = " | ".join(fmt(r.get(key, "N/A"), w) for key, _, w in COLS)
        print(row)


def print_summary(records: List[Dict[str, Any]]) -> None:
    completed = [r for r in records if r.get("status") == "completed"]
    failed = [r for r in records if r.get("status") == "failed"]

    print("\n" + "=" * 80)
    print("  4K VIDEO TRANSCODER — KPI SUMMARY")
    print("=" * 80)
    print(f"  Total jobs      : {len(records)}")
    print(f"  Completed       : {len(completed)}")
    print(f"  Failed          : {len(failed)}")

    if completed:
        proc_times = [r["processing_time_seconds"] for r in completed if "processing_time_seconds" in r]
        latencies = [r["latency_seconds"] for r in completed if "latency_seconds" in r]
        throughputs = [r["throughput_jobs_per_min"] for r in completed if "throughput_jobs_per_min" in r]
        cpu_before = [r["cpu_usage_percent_before"] for r in completed if "cpu_usage_percent_before" in r]
        cpu_after = [r["cpu_usage_percent_after"] for r in completed if "cpu_usage_percent_after" in r]
        queue_waits = [r["queue_wait_seconds"] for r in completed if "queue_wait_seconds" in r]

        print()
        print("  ── Processing Time (seconds) ──────────────────────────────────────────────")
        print(f"     Min     : {min(proc_times):.3f}s")
        print(f"     Max     : {max(proc_times):.3f}s")
        print(f"     Average : {sum(proc_times)/len(proc_times):.3f}s")

        print()
        print("  ── End-to-End Latency (seconds) ───────────────────────────────────────────")
        print(f"     Min     : {min(latencies):.3f}s")
        print(f"     Max     : {max(latencies):.3f}s")
        print(f"     Average : {sum(latencies)/len(latencies):.3f}s")

        print()
        print("  ── Queue Wait Time (seconds) ──────────────────────────────────────────────")
        print(f"     Min     : {min(queue_waits):.3f}s")
        print(f"     Max     : {max(queue_waits):.3f}s")
        print(f"     Average : {sum(queue_waits)/len(queue_waits):.3f}s")

        print()
        print("  ── Throughput (jobs/minute) ────────────────────────────────────────────────")
        print(f"     Min     : {min(throughputs):.4f}")
        print(f"     Max     : {max(throughputs):.4f}")
        print(f"     Average : {sum(throughputs)/len(throughputs):.4f}")

        print()
        print("  ── CPU Usage (%) ───────────────────────────────────────────────────────────")
        if cpu_before:
            print(f"     Avg Before : {sum(cpu_before)/len(cpu_before):.1f}%")
        if cpu_after:
            print(f"     Avg After  : {sum(cpu_after)/len(cpu_after):.1f}%")

        print()
        print("  ── Per-Preset Breakdown ────────────────────────────────────────────────────")
        presets: Dict[str, List[float]] = {}
        for r in completed:
            p = r.get("preset", "unknown")
            presets.setdefault(p, []).append(r.get("processing_time_seconds", 0))
        for p, times in sorted(presets.items()):
            print(f"     {p:<12} : {len(times)} job(s), avg {sum(times)/len(times):.3f}s")

    print("=" * 80 + "\n")


def export_csv(records: List[Dict[str, Any]], output_path: str = "metrics/kpi_export.csv") -> None:
    if not records:
        print("[WARN] No records to export.")
        return
    keys = list(records[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"[OK] CSV exported to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="4K Video Transcoder — KPI Viewer")
    parser.add_argument("--preset", help="Filter by preset (e.g. 1080p, 720p, 4k)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--csv", action="store_true", help="Export to CSV")
    parser.add_argument("--file", default=METRICS_FILE, help="Path to jobs.jsonl")
    args = parser.parse_args()

    metrics_file = args.file
    records = load_metrics(preset_filter=args.preset, metrics_file=metrics_file)

    if not records:
        print("[INFO] No matching records found.")
        return

    if args.json:
        print(json.dumps(records, indent=2))
        return

    if args.csv:
        export_csv(records)
        return

    print_summary(records)
    print_table(records)
    print()


if __name__ == "__main__":
    main()
