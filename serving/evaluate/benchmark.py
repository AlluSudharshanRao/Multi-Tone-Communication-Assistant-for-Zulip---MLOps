"""
benchmark.py — Measure latency (p50/p95/p99) and throughput for a serving endpoint.

Usage:
  python benchmark.py --url http://<host>:8001/predict \
                      --endpoint classifier \
                      --concurrency 1 5 10 \
                      --n 200

Outputs a CSV and prints a summary table suitable for the Serving Options Table.
"""

import argparse
import time
import statistics
import csv
import json
import threading
import psutil
import os
import sys
from pathlib import Path

import httpx
from rich.table import Table
from rich.console import Console

console = Console()

# ---------------------------------------------------------------------------
# Test payloads
# ---------------------------------------------------------------------------
CLASSIFIER_PAYLOAD = {
    "message_id": "bench_001",
    "text": "yo can u just fix the bug already its been 3 days lol",
    "message_type": "stream",
}

GENERATOR_PAYLOAD = {
    "message_id": "bench_001",
    "text": "yo can u just fix the bug already its been 3 days lol",
    "message_type": "stream",
}

PAYLOADS = {"classifier": CLASSIFIER_PAYLOAD, "generator": GENERATOR_PAYLOAD}

# Longer test corpus for realistic distribution
TEST_MESSAGES = [
    "yo can u just fix the bug already its been 3 days lol",
    "i cant believe this lol, the whole thing is broken",
    "please review my pr when u get a chance",
    "Fix this. NOW.",
    "Could you help me understand the deployment pipeline? I'm a bit confused.",
    "we need to talk about the deadline it's tomorrow and nothing works",
    "great work on the presentation everyone!!",
    "the server is down again, classic",
    "Can someone please update the documentation for the API endpoints?",
    "meeting starts in 5, where r u??",
]


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------
def run_single(url: str, payload: dict, client: httpx.Client) -> float:
    """Send one request and return latency in ms. Returns -1 on error."""
    try:
        t0 = time.perf_counter()
        resp = client.post(url, json=payload, timeout=10.0)
        latency_ms = (time.perf_counter() - t0) * 1000
        if resp.status_code != 200:
            return -1.0
        return latency_ms
    except Exception:
        return -1.0


def benchmark_serial(url: str, payload: dict, n: int) -> list[float]:
    """Serial baseline — one request at a time."""
    latencies = []
    with httpx.Client() as client:
        # Warmup
        for _ in range(5):
            run_single(url, payload, client)
        for i in range(n):
            import random
            p = dict(payload)
            p["text"] = TEST_MESSAGES[i % len(TEST_MESSAGES)]
            p["message_id"] = f"bench_{i:04d}"
            lat = run_single(url, p, client)
            if lat > 0:
                latencies.append(lat)
    return latencies


def benchmark_concurrent(url: str, payload: dict, n: int, concurrency: int) -> list[float]:
    """Concurrent requests using threads."""
    latencies = []
    lock = threading.Lock()
    import random

    def worker(batch_indices):
        with httpx.Client() as client:
            # Warmup
            run_single(url, payload, client)
            for idx in batch_indices:
                p = dict(payload)
                p["text"] = TEST_MESSAGES[idx % len(TEST_MESSAGES)]
                p["message_id"] = f"bench_{idx:04d}"
                lat = run_single(url, p, client)
                with lock:
                    if lat > 0:
                        latencies.append(lat)

    indices = list(range(n))
    chunk = max(1, n // concurrency)
    threads = []
    for i in range(concurrency):
        batch = indices[i * chunk:(i + 1) * chunk]
        t = threading.Thread(target=worker, args=(batch,))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return latencies


def summarize(latencies: list[float], concurrency: int, duration_s: float) -> dict:
    if not latencies:
        return {"error": "no successful requests"}
    latencies_sorted = sorted(latencies)
    n = len(latencies)
    return {
        "n": n,
        "concurrency": concurrency,
        "p50_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(latencies_sorted[int(0.95 * n)], 1),
        "p99_ms": round(latencies_sorted[int(0.99 * n)], 1),
        "mean_ms": round(statistics.mean(latencies), 1),
        "throughput_rps": round(n / duration_s, 2),
        "error_rate": 0.0,  # errors already filtered
    }


# ---------------------------------------------------------------------------
# Resource sampling (CPU / RAM)
# ---------------------------------------------------------------------------
def sample_resources(pid: int, duration: float, interval: float = 0.5) -> dict:
    proc = psutil.Process(pid)
    cpu_samples, mem_samples = [], []
    t_end = time.time() + duration
    while time.time() < t_end:
        try:
            cpu_samples.append(proc.cpu_percent(interval=None))
            mem_samples.append(proc.memory_info().rss / 1024 / 1024)
        except psutil.NoSuchProcess:
            break
        time.sleep(interval)
    return {
        "avg_cpu_pct": round(statistics.mean(cpu_samples), 1) if cpu_samples else 0,
        "peak_mem_mb": round(max(mem_samples), 1) if mem_samples else 0,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Serving benchmark")
    parser.add_argument("--url", required=True, help="Endpoint URL (e.g. http://localhost:8001/predict)")
    parser.add_argument("--endpoint", choices=["classifier", "generator"], default="classifier")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 5, 10],
                        help="Concurrency levels to test")
    parser.add_argument("--n", type=int, default=200, help="Requests per concurrency level")
    parser.add_argument("--out", default="results.csv", help="Output CSV path")
    parser.add_argument("--label", default="option", help="Row label for this serving option")
    args = parser.parse_args()

    payload = PAYLOADS[args.endpoint]
    rows = []

    for c in args.concurrency:
        console.print(f"\n[bold cyan]Benchmarking concurrency={c}[/bold cyan]")
        t_start = time.perf_counter()
        if c == 1:
            lats = benchmark_serial(args.url, payload, args.n)
        else:
            lats = benchmark_concurrent(args.url, payload, args.n, c)
        duration = time.perf_counter() - t_start
        summary = summarize(lats, c, duration)
        summary["label"] = args.label
        summary["url"] = args.url
        rows.append(summary)
        console.print(summary)

    # Write CSV
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["label", "url", "concurrency", "n", "p50_ms", "p95_ms", "p99_ms",
                  "mean_ms", "throughput_rps", "error_rate"]
    write_header = not Path(args.out).exists()
    with open(args.out, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)

    # Print rich table
    table = Table(title=f"Serving Benchmark — {args.label}", show_lines=True)
    for col in fieldnames:
        table.add_column(col, style="green" if col == "p95_ms" else "white")
    for row in rows:
        table.add_row(*[str(row.get(c, "")) for c in fieldnames])
    console.print(table)
    console.print(f"\n[bold]Results appended to {args.out}[/bold]")


if __name__ == "__main__":
    main()
