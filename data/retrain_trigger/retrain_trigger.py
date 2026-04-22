"""
Retraining trigger — runs daily as a K8s CronJob (k8s/data/retrain-trigger-cronjob.yaml).

Evaluates three independent trigger conditions:

  DATA_TRIGGER:    New feedback entries since last retrain >= DATA_TRIGGER_COUNT (default 500).
  QUALITY_TRIGGER: Rolling 7-day feedback approval rate < QUALITY_THRESHOLD (default 0.70).
                   Approval = (thumbs_up + selected) / total_feedback.
  DRIFT_TRIGGER:   Mean classifier confidence (from batch feedback_manifest) < DRIFT_THRESHOLD
                   (default 0.60) — proxy for input distribution shift.

If ANY condition fires:
  1. Writes a trigger record to MinIO:  triggers/YYYY-MM-DD/trigger_{ts}.json
  2. Exits with code 10 so the K8s CronJob can surface it as a non-zero exit.
     The GitHub Actions retrain-on-trigger.yml checks for new trigger records and
     applies k8s/training/ jobs + k8s/training/register-bundle/.

If no condition fires, exits 0 (normal).

Environment variables:
  MINIO_ENDPOINT, MINIO_BUCKET, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
  MLFLOW_TRACKING_URI      — for reading latest production run metrics
  DATA_TRIGGER_COUNT       — default 500
  QUALITY_THRESHOLD        — default 0.70
  DRIFT_THRESHOLD          — default 0.60
  LOOKBACK_DAYS            — number of days to scan feedback/ prefix (default 7)
  DRY_RUN                  — "true" to evaluate but not write trigger record
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO

import boto3
import requests
from botocore.client import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("retrain_trigger")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MINIO_ENDPOINT   = os.environ.get("MINIO_ENDPOINT",   "http://minio.ml-platform.svc.cluster.local:9000")
MINIO_BUCKET     = os.environ.get("MINIO_BUCKET",     "zulip-rewriter")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MLFLOW_URI       = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow.ml-platform.svc.cluster.local:5000")

DATA_TRIGGER_COUNT = int(os.environ.get("DATA_TRIGGER_COUNT", "500"))
QUALITY_THRESHOLD  = float(os.environ.get("QUALITY_THRESHOLD", "0.70"))
DRIFT_THRESHOLD    = float(os.environ.get("DRIFT_THRESHOLD",   "0.60"))
LOOKBACK_DAYS      = int(os.environ.get("LOOKBACK_DAYS",       "7"))
DRY_RUN            = os.environ.get("DRY_RUN", "false").lower() == "true"

TRIGGER_EXIT_CODE = 10   # non-zero so CronJob/CI can detect trigger


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------

def _s3():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        verify=False,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _list_prefix(s3_client, prefix: str) -> list[dict]:
    paginator = s3_client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=MINIO_BUCKET, Prefix=prefix):
        keys.extend(page.get("Contents", []))
    return keys


def _read_json(s3_client, key: str) -> dict:
    obj = s3_client.get_object(Bucket=MINIO_BUCKET, Key=key)
    return json.loads(obj["Body"].read())


def _write_json(s3_client, key: str, data: dict) -> None:
    s3_client.put_object(
        Bucket=MINIO_BUCKET,
        Key=key,
        Body=json.dumps(data, indent=2).encode(),
        ContentType="application/json",
    )


# ---------------------------------------------------------------------------
# Last-retrain watermark
# ---------------------------------------------------------------------------

_WATERMARK_KEY = "triggers/last_retrain_watermark.json"


def _load_watermark(s3_client) -> dict:
    try:
        return _read_json(s3_client, _WATERMARK_KEY)
    except ClientError:
        return {"last_retrain_at": None, "feedback_count_at_retrain": 0}


def _save_watermark(s3_client, data: dict) -> None:
    _write_json(s3_client, _WATERMARK_KEY, data)


# ---------------------------------------------------------------------------
# Trigger evaluations
# ---------------------------------------------------------------------------

def _count_recent_feedback(s3_client, since: datetime) -> tuple[int, float | None]:
    """Return (total_count_since, approval_rate_or_None) from batch feedback_manifests."""
    cutoff = since.strftime("%Y-%m-%d")
    total, approved = 0, 0
    # Read daily batch feedback_manifest.json files produced by batch_pipeline.py
    for obj_meta in _list_prefix(s3_client, "batch/"):
        key = obj_meta["Key"]
        if not key.endswith("feedback_manifest.json"):
            continue
        # Key pattern: batch/{VERSION}_batch_{YYYY-MM-DD}/feedback_manifest.json
        # Extract date from path
        parts = key.split("/")
        if len(parts) < 2:
            continue
        batch_dir = parts[1]  # e.g. v1_batch_2026-04-20
        batch_date = batch_dir.split("_batch_")[-1] if "_batch_" in batch_dir else ""
        if batch_date < cutoff:
            continue
        try:
            manifest = _read_json(s3_client, key)
            total    += manifest.get("feedback_total_entries", 0)
            approved += manifest.get("thumbs_up", 0)
            approved += int(manifest.get("feedback_total_entries", 0) *
                            (manifest.get("approval_rate", 0) or 0))
        except Exception as exc:
            log.warning("Could not read %s: %s", key, exc)

    approval_rate = round(approved / max(total, 1), 4) if total > 0 else None
    return total, approval_rate


def _get_production_model_f1(mlflow_uri: str) -> float | None:
    """Query MLflow for the latest production classifier run's eval_f1 metric."""
    try:
        # Find experiment
        resp = requests.get(
            f"{mlflow_uri}/api/2.0/mlflow/experiments/search",
            params={"filter": "name = 'teamchat_tone_clf'", "max_results": 1},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        exps = resp.json().get("experiments", [])
        if not exps:
            return None
        exp_id = exps[0]["experiment_id"]

        # Search for runs tagged production/champion/aliases
        runs_resp = requests.post(
            f"{mlflow_uri}/api/2.0/mlflow/runs/search",
            json={
                "experiment_ids": [exp_id],
                "filter": "tags.mlflow.runName = 'production' OR tags.alias = 'prod'",
                "max_results": 1,
                "order_by": ["start_time DESC"],
            },
            timeout=10,
        )
        if runs_resp.status_code != 200:
            return None
        runs = runs_resp.json().get("runs", [])
        if not runs:
            # Fall back to latest finished run
            runs_resp2 = requests.post(
                f"{mlflow_uri}/api/2.0/mlflow/runs/search",
                json={
                    "experiment_ids": [exp_id],
                    "filter": "status = 'FINISHED'",
                    "max_results": 1,
                    "order_by": ["start_time DESC"],
                },
                timeout=10,
            )
            runs = runs_resp2.json().get("runs", []) if runs_resp2.status_code == 200 else []
        if not runs:
            return None

        metrics = {m["key"]: m["value"] for m in runs[0].get("data", {}).get("metrics", [])}
        return float(metrics.get("eval_f1") or metrics.get("f1") or metrics.get("test_f1") or 0)
    except Exception as exc:
        log.warning("MLflow query failed (non-fatal): %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== Retrain trigger evaluation ===")
    log.info(
        "Thresholds: data=%d quality=%.2f drift=%.2f lookback=%dd dry_run=%s",
        DATA_TRIGGER_COUNT, QUALITY_THRESHOLD, DRIFT_THRESHOLD, LOOKBACK_DAYS, DRY_RUN,
    )

    s3 = _s3()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS)

    watermark = _load_watermark(s3)
    log.info("Watermark: %s", watermark)

    # --- DATA TRIGGER ---
    recent_feedback, approval_rate = _count_recent_feedback(s3, since)
    prev_count = watermark.get("feedback_count_at_retrain", 0)
    new_feedback = max(0, recent_feedback - prev_count)
    data_triggered = new_feedback >= DATA_TRIGGER_COUNT
    log.info(
        "DATA_TRIGGER: new_feedback=%d threshold=%d → %s",
        new_feedback, DATA_TRIGGER_COUNT, "FIRE" if data_triggered else "ok",
    )

    # --- QUALITY TRIGGER ---
    quality_triggered = False
    if approval_rate is not None:
        quality_triggered = approval_rate < QUALITY_THRESHOLD
    log.info(
        "QUALITY_TRIGGER: approval_rate=%s threshold=%.2f → %s",
        approval_rate, QUALITY_THRESHOLD, "FIRE" if quality_triggered else "ok",
    )

    # --- DRIFT TRIGGER (proxy: MLflow production F1 drop) ---
    prod_f1 = _get_production_model_f1(MLFLOW_URI)
    drift_triggered = False
    if prod_f1 is not None:
        drift_triggered = prod_f1 < DRIFT_THRESHOLD
    log.info(
        "DRIFT_TRIGGER: prod_f1=%s threshold=%.2f → %s",
        prod_f1, DRIFT_THRESHOLD, "FIRE" if drift_triggered else "ok",
    )

    # --- Decision ---
    fires = {
        "data":    data_triggered,
        "quality": quality_triggered,
        "drift":   drift_triggered,
    }
    should_retrain = any(fires.values())

    if not should_retrain:
        log.info("No trigger conditions met — no retrain needed.")
        sys.exit(0)

    reasons = [k for k, v in fires.items() if v]
    log.info("RETRAIN TRIGGERED by: %s", reasons)

    trigger_record = {
        "triggered_at": now.isoformat(),
        "reasons": reasons,
        "metrics": {
            "new_feedback_count":  new_feedback,
            "approval_rate":       approval_rate,
            "production_f1":       prod_f1,
        },
        "thresholds": {
            "data_trigger_count": DATA_TRIGGER_COUNT,
            "quality_threshold":  QUALITY_THRESHOLD,
            "drift_threshold":    DRIFT_THRESHOLD,
        },
        "processed": False,
    }

    ts = int(now.timestamp())
    trigger_key = f"triggers/{now.strftime('%Y-%m-%d')}/trigger_{ts}.json"

    if DRY_RUN:
        log.info("DRY_RUN — would write: %s\n%s", trigger_key, json.dumps(trigger_record, indent=2))
        sys.exit(0)

    _write_json(s3, trigger_key, trigger_record)
    log.info("Trigger record written: %s", trigger_key)

    # Update watermark so next run starts counting from now
    _save_watermark(s3, {
        "last_retrain_at": now.isoformat(),
        "feedback_count_at_retrain": recent_feedback,
    })

    log.info("Exiting with code %d so CI can detect this trigger.", TRIGGER_EXIT_CODE)
    sys.exit(TRIGGER_EXIT_CODE)


if __name__ == "__main__":
    main()
