#!/usr/bin/env python3
"""
kpi_compare.py — KPI Comparison: Local vs Cloud (OpenStack DevStack)
=====================================================================
Gathers performance metrics from both a locally-run and a cloud-deployed
instance of the 4K Video Transcoder, then visualises the comparison.

Modes:
  1. Existing data  — compare metrics already recorded on both environments
  2. Live test      — upload a video to both, wait for completion, then compare

Usage:
    # Compare existing metrics (reads from API or local file):
    python kpi_compare.py

    # Run fresh test jobs on both environments first:
    python kpi_compare.py --run-tests --video videos/sample.mp4

    # Custom API URLs:
    python kpi_compare.py --local-url http://127.0.0.1:8000 \\
                          --cloud-url http://172.24.4.59:8000

    # Use local metrics files instead of API:
    python kpi_compare.py --local-file metrics/jobs.jsonl \\
                          --cloud-file /tmp/cloud_jobs.jsonl

    # Save charts to a specific directory:
    python kpi_compare.py --output kpi_report/

    # Skip chart generation (terminal table only):
    python kpi_compare.py --no-charts
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ── Optional dependencies ─────────────────────────────────────────────────────
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import matplotlib
    matplotlib.use("Agg")          # non-interactive backend (no display needed)
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ── Palette ───────────────────────────────────────────────────────────────────
LOCAL_COLOR  = "#2196F3"   # blue
CLOUD_COLOR  = "#FF9800"   # orange
LOCAL_LIGHT  = "#90CAF9"
CLOUD_LIGHT  = "#FFCC80"

PRESETS_ORDER = ["480p", "720p", "1080p", "4k"]

# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def check_health(base_url: str, timeout: int = 6) -> Tuple[bool, str]:
    """Return (is_healthy, redis_status)."""
    if not HAS_REQUESTS:
        return False, "requests not installed"
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/health", timeout=timeout)
        data = resp.json()
        return data.get("status") == "ok", data.get("redis", "unknown")
    except Exception as exc:
        return False, str(exc)


def fetch_metrics_api(base_url: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """Fetch all metrics via GET /metrics."""
    if not HAS_REQUESTS:
        return []
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/metrics", timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("records", [])
    except Exception as exc:
        print(f"  [WARN] Could not fetch metrics from {base_url}: {exc}")
        return []


def load_metrics_file(path: str) -> List[Dict[str, Any]]:
    """Load metrics from a local jobs.jsonl file."""
    if not os.path.exists(path):
        print(f"  [WARN] File not found: {path}")
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def upload_and_wait(
    base_url: str,
    video_path: str,
    preset: str,
    poll_interval: int = 3,
    timeout: int = 360,
) -> Optional[Dict[str, Any]]:
    """Upload a video, poll until done, return the metrics record."""
    if not HAS_REQUESTS:
        print("  [ERROR] requests library required for --run-tests")
        return None
    try:
        with open(video_path, "rb") as fh:
            resp = requests.post(
                f"{base_url.rstrip('/')}/upload",
                files={"file": fh},
                data={"preset": preset},
                timeout=60,
            )
        resp.raise_for_status()
        job_id = resp.json()["job_id"]
        print(f"    Queued  job={job_id[:8]}  preset={preset}")
    except Exception as exc:
        print(f"    [ERROR] Upload failed: {exc}")
        return None

    # Poll progress
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            prog = requests.get(
                f"{base_url.rstrip('/')}/progress/{job_id}", timeout=10
            ).json()
            pct    = prog.get("progress", 0)
            status = prog.get("status", "")
            print(f"    Progress {pct:5.1f}%  [{status}]", end="\r")
            if status in ("completed", "failed"):
                print()
                break
        except Exception:
            pass
        time.sleep(poll_interval)
    else:
        print(f"\n    [WARN] Timed out waiting for job {job_id[:8]}")
        return None

    # Fetch metrics record
    try:
        mresp = requests.get(
            f"{base_url.rstrip('/')}/jobs/{job_id}/metrics", timeout=10
        )
        if mresp.status_code == 200:
            recs = mresp.json().get("metrics", [])
            return recs[0] if recs else None
    except Exception:
        pass
    return None


def avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def field_avg(records: List[Dict], field: str) -> float:
    vals = [r[field] for r in records if field in r and r[field] is not None]
    return avg(vals)


def completed(records: List[Dict]) -> List[Dict]:
    return [r for r in records if r.get("status") == "completed"]


def by_preset(records: List[Dict]) -> Dict[str, List[Dict]]:
    groups: Dict[str, List[Dict]] = {}
    for r in completed(records):
        groups.setdefault(r.get("preset", "unknown"), []).append(r)
    return groups


# ─────────────────────────────────────────────────────────────────────────────
# Terminal output
# ─────────────────────────────────────────────────────────────────────────────

def _w(s: Any, w: int) -> str:
    s = str(s) if s is not None else "N/A"
    return s[:w].ljust(w)


def print_comparison_table(
    local_recs: List[Dict],
    cloud_recs: List[Dict],
    local_label: str = "Local",
    cloud_label: str = "Cloud",
) -> None:
    lc = completed(local_recs)
    cc = completed(cloud_recs)

    METRICS = [
        ("processing_time_seconds",  "Avg Processing Time (s)",    False),
        ("latency_seconds",          "Avg End-to-End Latency (s)", False),
        ("queue_wait_seconds",       "Avg Queue Wait (s)",         False),
        ("throughput_jobs_per_min",  "Avg Throughput (jobs/min)",  True),
        ("cpu_usage_percent_before", "Avg CPU Before (%)",         False),
        ("cpu_usage_percent_after",  "Avg CPU After (%)",          False),
    ]

    SEP = "=" * 82
    sep = "-" * 82

    print()
    print(SEP)
    print("  4K VIDEO TRANSCODER — KPI COMPARISON: LOCAL vs CLOUD (OpenStack DevStack)")
    print(SEP)
    print(f"  Generated : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()
    print(f"  {'Environment':<22} {'Total Jobs':>10}  {'Completed':>10}  {'Failed':>7}")
    print(f"  {'-'*22} {'-'*10}  {'-'*10}  {'-'*7}")
    print(f"  {local_label:<22} {len(local_recs):>10}  {len(lc):>10}  {len(local_recs)-len(lc):>7}")
    print(f"  {cloud_label:<22} {len(cloud_recs):>10}  {len(cc):>10}  {len(cloud_recs)-len(cc):>7}")
    print()
    print(sep)
    print(f"  {'Metric':<36} {local_label:>14}  {cloud_label:>14}  {'Winner':>10}")
    print(f"  {'-'*36} {'-'*14}  {'-'*14}  {'-'*10}")

    for field, label, higher_better in METRICS:
        l_avg = field_avg(lc, field) if lc else None
        c_avg = field_avg(cc, field) if cc else None
        l_str = f"{l_avg:.3f}" if l_avg is not None else "N/A"
        c_str = f"{c_avg:.3f}" if c_avg is not None else "N/A"

        if l_avg is not None and c_avg is not None and l_avg != c_avg:
            if higher_better:
                winner = local_label if l_avg > c_avg else cloud_label
            else:
                winner = local_label if l_avg < c_avg else cloud_label
        else:
            winner = "Tie" if (l_avg is not None and c_avg is not None) else "N/A"

        print(f"  {label:<36} {l_str:>14}  {c_str:>14}  {winner:>10}")

    print()
    print(sep)
    print(f"  Per-Preset Breakdown")
    print(sep)
    print(f"  {'Preset':<8} {'Env':<8} {'Jobs':>5}  {'Proc(s)':>9}  {'Lat(s)':>8}  {'Tput(j/m)':>10}  {'CPU%':>6}")
    print(f"  {'-'*8} {'-'*8} {'-'*5}  {'-'*9}  {'-'*8}  {'-'*10}  {'-'*6}")

    all_presets = sorted(
        set(list(by_preset(local_recs).keys()) + list(by_preset(cloud_recs).keys())),
        key=lambda p: PRESETS_ORDER.index(p) if p in PRESETS_ORDER else 99,
    )

    for preset in all_presets:
        for env_lbl, recs in [(local_label[:7], by_preset(local_recs)), (cloud_label[:7], by_preset(cloud_recs))]:
            grp = recs.get(preset, [])
            if not grp:
                continue
            ap = field_avg(grp, "processing_time_seconds")
            al = field_avg(grp, "latency_seconds")
            at = field_avg(grp, "throughput_jobs_per_min")
            ac = field_avg(grp, "cpu_usage_percent_after")
            print(f"  {preset:<8} {env_lbl:<8} {len(grp):>5}  {ap:>9.3f}  {al:>8.3f}  {at:>10.4f}  {ac:>6.1f}")

    print(SEP)
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Charts
# ─────────────────────────────────────────────────────────────────────────────

def _annotate_bars(ax, bars):
    for bar in bars:
        h = bar.get_height()
        if h > 0.001:
            ax.annotate(
                f"{h:.2f}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                fontsize=8.5,
            )


def chart_metric_by_preset(
    local_recs: List[Dict],
    cloud_recs: List[Dict],
    field: str,
    title: str,
    ylabel: str,
    output_path: str,
    higher_is_better: bool = False,
) -> None:
    lbp = by_preset(local_recs)
    cbp = by_preset(cloud_recs)
    presets = sorted(
        set(list(lbp.keys()) + list(cbp.keys())),
        key=lambda p: PRESETS_ORDER.index(p) if p in PRESETS_ORDER else 99,
    )
    if not presets:
        return

    l_vals = [field_avg(lbp.get(p, []), field) for p in presets]
    c_vals = [field_avg(cbp.get(p, []), field) for p in presets]

    x = np.arange(len(presets))
    w = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    b_l = ax.bar(x - w / 2, l_vals, w, label="Local",            color=LOCAL_COLOR, alpha=0.88)
    b_c = ax.bar(x + w / 2, c_vals, w, label="Cloud (DevStack)", color=CLOUD_COLOR, alpha=0.88)
    _annotate_bars(ax, b_l)
    _annotate_bars(ax, b_c)

    # Winner badge
    for i, (lv, cv) in enumerate(zip(l_vals, c_vals)):
        if lv > 0 and cv > 0:
            if higher_is_better:
                win_color = LOCAL_COLOR if lv >= cv else CLOUD_COLOR
                badge = "L✓" if lv >= cv else "C✓"
            else:
                win_color = LOCAL_COLOR if lv <= cv else CLOUD_COLOR
                badge = "L✓" if lv <= cv else "C✓"
            ax.text(x[i], max(lv, cv) * 1.10, badge,
                    ha="center", fontsize=10, color=win_color, fontweight="bold")

    ax.set_title(title, fontsize=13, fontweight="bold", pad=14)
    ax.set_xlabel("Preset", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(presets, fontsize=11)
    ax.legend(fontsize=11)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_ylim(bottom=0)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [CHART] {os.path.basename(output_path)}")


def chart_cpu(
    local_recs: List[Dict],
    cloud_recs: List[Dict],
    output_path: str,
) -> None:
    lc = completed(local_recs)
    cc = completed(cloud_recs)

    categories = ["Local\nBefore", "Local\nAfter", "Cloud\nBefore", "Cloud\nAfter"]
    values = [
        field_avg(lc, "cpu_usage_percent_before"),
        field_avg(lc, "cpu_usage_percent_after"),
        field_avg(cc, "cpu_usage_percent_before"),
        field_avg(cc, "cpu_usage_percent_after"),
    ]
    colors = [LOCAL_LIGHT, LOCAL_COLOR, CLOUD_LIGHT, CLOUD_COLOR]

    fig, ax = plt.subplots(figsize=(9, 6))
    bars = ax.bar(categories, values, color=colors, edgecolor="white", linewidth=1.2)
    for bar in bars:
        h = bar.get_height()
        ax.annotate(f"{h:.1f}%",
                    xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", fontsize=11, fontweight="bold")

    ax.set_title("CPU Usage: Before vs After Transcoding — Local vs Cloud",
                 fontsize=13, fontweight="bold", pad=14)
    ax.set_ylabel("CPU Usage (%)", fontsize=11)
    ax.set_ylim(0, max(values) * 1.3 if any(v > 0 for v in values) else 100)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    local_patch = mpatches.Patch(color=LOCAL_COLOR, label="Local")
    cloud_patch = mpatches.Patch(color=CLOUD_COLOR, label="Cloud (DevStack)")
    ax.legend(handles=[local_patch, cloud_patch], fontsize=11)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [CHART] {os.path.basename(output_path)}")


def chart_summary_overview(
    local_recs: List[Dict],
    cloud_recs: List[Dict],
    output_path: str,
) -> None:
    """Multi-panel summary: 4 key metrics side-by-side."""
    lc = completed(local_recs)
    cc = completed(cloud_recs)

    panels = [
        ("processing_time_seconds",  "Avg Processing Time (s)",    False),
        ("latency_seconds",          "Avg End-to-End Latency (s)", False),
        ("throughput_jobs_per_min",  "Avg Throughput (jobs/min)",  True),
        ("queue_wait_seconds",       "Avg Queue Wait (s)",         False),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(
        "KPI Summary: Local vs Cloud (OpenStack DevStack)\nAll Presets Combined",
        fontsize=14, fontweight="bold", y=1.01,
    )
    axes = axes.flatten()

    for ax, (field, label, higher_better) in zip(axes, panels):
        lbp = by_preset(local_recs)
        cbp = by_preset(cloud_recs)
        presets = sorted(
            set(list(lbp.keys()) + list(cbp.keys())),
            key=lambda p: PRESETS_ORDER.index(p) if p in PRESETS_ORDER else 99,
        )
        if not presets:
            ax.set_visible(False)
            continue

        l_vals = [field_avg(lbp.get(p, []), field) for p in presets]
        c_vals = [field_avg(cbp.get(p, []), field) for p in presets]
        x = np.arange(len(presets))
        w = 0.35

        b_l = ax.bar(x - w / 2, l_vals, w, label="Local",            color=LOCAL_COLOR, alpha=0.88)
        b_c = ax.bar(x + w / 2, c_vals, w, label="Cloud (DevStack)", color=CLOUD_COLOR, alpha=0.88)
        _annotate_bars(ax, b_l)
        _annotate_bars(ax, b_c)

        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(presets, fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        ax.set_ylim(bottom=0)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [CHART] {os.path.basename(output_path)}")


def chart_job_timeline(
    local_recs: List[Dict],
    cloud_recs: List[Dict],
    output_path: str,
) -> None:
    """Processing time over job sequence (scatter)."""
    lc = completed(local_recs)
    cc = completed(cloud_recs)

    if not lc and not cc:
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    if lc:
        l_times = [r.get("processing_time_seconds", 0) for r in lc]
        ax.scatter(range(len(l_times)), l_times, color=LOCAL_COLOR, label="Local",
                   s=80, zorder=3, alpha=0.85)
        ax.plot(range(len(l_times)), l_times, color=LOCAL_COLOR, alpha=0.4, linewidth=1)

    if cc:
        c_times = [r.get("processing_time_seconds", 0) for r in cc]
        ax.scatter(range(len(c_times)), c_times, color=CLOUD_COLOR, label="Cloud (DevStack)",
                   s=80, zorder=3, alpha=0.85, marker="s")
        ax.plot(range(len(c_times)), c_times, color=CLOUD_COLOR, alpha=0.4, linewidth=1)

    ax.set_title("Processing Time per Job — Local vs Cloud",
                 fontsize=13, fontweight="bold", pad=14)
    ax.set_xlabel("Job Sequence", fontsize=11)
    ax.set_ylabel("Processing Time (s)", fontsize=11)
    ax.legend(fontsize=11)
    ax.grid(alpha=0.3, linestyle="--")
    ax.set_ylim(bottom=0)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [CHART] {os.path.basename(output_path)}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="KPI Comparison: Local vs Cloud (OpenStack DevStack)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--local-url",  default="http://127.0.0.1:8000",
                        help="Local API base URL (default: http://127.0.0.1:8000)")
    parser.add_argument("--cloud-url",  default="http://172.24.4.59:8000",
                        help="Cloud API base URL (default: http://172.24.4.59:8000)")
    parser.add_argument("--local-file", default=None,
                        help="Path to local jobs.jsonl (bypasses API)")
    parser.add_argument("--cloud-file", default=None,
                        help="Path to cloud jobs.jsonl (bypasses API)")
    parser.add_argument("--run-tests",  action="store_true",
                        help="Run fresh test jobs on both environments before comparing")
    parser.add_argument("--video",      default=None,
                        help="Video file to upload when using --run-tests")
    parser.add_argument("--presets",    default="720p,1080p",
                        help="Comma-separated presets for --run-tests (default: 720p,1080p)")
    parser.add_argument("--output",     default="kpi_report",
                        help="Output directory for charts (default: kpi_report/)")
    parser.add_argument("--no-charts",  action="store_true",
                        help="Skip chart generation (terminal table only)")
    args = parser.parse_args()

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print("  4K VIDEO TRANSCODER — KPI COMPARISON TOOL")
    print("=" * 62)
    print(f"  Local  API : {args.local_url}")
    print(f"  Cloud  API : {args.cloud_url}")
    if not args.no_charts:
        print(f"  Charts     : {args.output}/")
    print()

    if not HAS_REQUESTS:
        print("[WARN] 'requests' not installed — API fetching disabled.")
        print("       Install: pip install requests")
        print("       Use --local-file / --cloud-file to load data from files.\n")

    # ── Health checks ─────────────────────────────────────────────────────────
    print("── Health Checks ────────────────────────────────────────────")
    local_ok, local_redis = check_health(args.local_url)
    cloud_ok, cloud_redis = check_health(args.cloud_url)
    print(f"  Local  ({args.local_url}): {'✓ OK' if local_ok else '✗ UNREACHABLE'}  redis={local_redis}")
    print(f"  Cloud  ({args.cloud_url}): {'✓ OK' if cloud_ok else '✗ UNREACHABLE'}  redis={cloud_redis}")
    print()

    # ── Optional: run fresh test jobs ─────────────────────────────────────────
    if args.run_tests:
        if not args.video:
            print("[ERROR] --video <path> is required with --run-tests")
            sys.exit(1)
        if not os.path.exists(args.video):
            print(f"[ERROR] Video not found: {args.video}")
            sys.exit(1)

        test_presets = [p.strip() for p in args.presets.split(",") if p.strip()]
        print(f"── Running Test Jobs (presets: {', '.join(test_presets)}) ──────────────────")

        for env_label, base_url, healthy in [
            ("Local", args.local_url, local_ok),
            ("Cloud", args.cloud_url, cloud_ok),
        ]:
            if not healthy:
                print(f"  [{env_label}] Skipping — API unreachable")
                continue
            print(f"  [{env_label}] Uploading {len(test_presets)} job(s)...")
            for preset in test_presets:
                result = upload_and_wait(base_url, args.video, preset)
                if result:
                    pt = result.get("processing_time_seconds", "?")
                    print(f"    ✓ {preset}: processing_time={pt}s")
                else:
                    print(f"    ✗ {preset}: failed or timed out")
        print()

    # ── Load metrics ──────────────────────────────────────────────────────────
    print("── Loading Metrics ──────────────────────────────────────────")

    # Local
    if args.local_file:
        local_recs = load_metrics_file(args.local_file)
        print(f"  Local  : {len(local_recs)} records  (file: {args.local_file})")
    elif local_ok:
        local_recs = fetch_metrics_api(args.local_url)
        print(f"  Local  : {len(local_recs)} records  (API)")
    else:
        fallback = "metrics/jobs.jsonl"
        local_recs = load_metrics_file(fallback)
        print(f"  Local  : {len(local_recs)} records  (fallback file: {fallback})")

    # Cloud
    if args.cloud_file:
        cloud_recs = load_metrics_file(args.cloud_file)
        print(f"  Cloud  : {len(cloud_recs)} records  (file: {args.cloud_file})")
    elif cloud_ok:
        cloud_recs = fetch_metrics_api(args.cloud_url)
        print(f"  Cloud  : {len(cloud_recs)} records  (API)")
    else:
        print(f"  Cloud  : 0 records  (API unreachable, no file specified)")
        cloud_recs = []

    print()

    if not local_recs and not cloud_recs:
        print("[ERROR] No metrics data available from either environment.")
        print("        Run the app, submit some jobs, then re-run this tool.")
        print("        Or use --run-tests --video <path> to generate data automatically.")
        sys.exit(1)

    # ── Terminal comparison table ─────────────────────────────────────────────
    print_comparison_table(local_recs, cloud_recs)

    # ── Charts ────────────────────────────────────────────────────────────────
    if args.no_charts:
        print("[INFO] Chart generation skipped (--no-charts).")
        return

    if not HAS_MATPLOTLIB:
        print("[WARN] matplotlib/numpy not installed — skipping charts.")
        print("       Install: pip install matplotlib numpy")
        return

    os.makedirs(args.output, exist_ok=True)
    print(f"── Generating Charts → {args.output}/ ───────────────────────")

    out = lambda name: os.path.join(args.output, name)

    chart_summary_overview(local_recs, cloud_recs,
                           out("01_summary_overview.png"))

    chart_metric_by_preset(local_recs, cloud_recs,
                           "processing_time_seconds",
                           "Processing Time by Preset — Local vs Cloud",
                           "Processing Time (s)",
                           out("02_processing_time.png"),
                           higher_is_better=False)

    chart_metric_by_preset(local_recs, cloud_recs,
                           "latency_seconds",
                           "End-to-End Latency by Preset — Local vs Cloud",
                           "Latency (s)",
                           out("03_latency.png"),
                           higher_is_better=False)

    chart_metric_by_preset(local_recs, cloud_recs,
                           "throughput_jobs_per_min",
                           "Throughput by Preset — Local vs Cloud",
                           "Throughput (jobs/min)",
                           out("04_throughput.png"),
                           higher_is_better=True)

    chart_metric_by_preset(local_recs, cloud_recs,
                           "queue_wait_seconds",
                           "Queue Wait Time by Preset — Local vs Cloud",
                           "Queue Wait (s)",
                           out("05_queue_wait.png"),
                           higher_is_better=False)

    chart_cpu(local_recs, cloud_recs,
              out("06_cpu_usage.png"))

    chart_job_timeline(local_recs, cloud_recs,
                       out("07_job_timeline.png"))

    print()
    print(f"  All charts saved to: {os.path.abspath(args.output)}/")
    print()


if __name__ == "__main__":
    main()
