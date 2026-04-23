from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from prometheus_client import Gauge, start_http_server

from zulip_data_quality_monitoring.config import load_config
from zulip_data_quality_monitoring.metrics import (
    class_distribution,
    duplicate_rate,
    estimated_formality,
    invalid_label_rate,
    null_rate,
    psi,
    ratio,
)
from zulip_data_quality_monitoring.storage import MinioStore


EXPORTER_LAST_SUCCESS = Gauge("data_quality_exporter_last_success_timestamp", "Unix timestamp of the last successful exporter refresh.")
EXPORTER_UP = Gauge("data_quality_exporter_up", "Whether the data quality exporter successfully refreshed on the last run.")
RAW_ROWS = Gauge("data_quality_raw_rows", "Row count in raw dataset split.", ["split", "version"])
RAW_NULL_TEXT_RATE = Gauge("data_quality_raw_null_text_rate", "Null text rate in the raw dataset.", ["version"])
RAW_DUPLICATE_TEXT_RATE = Gauge("data_quality_raw_duplicate_text_rate", "Duplicate text rate in the raw dataset.", ["version"])
RAW_INVALID_LABEL_RATE = Gauge("data_quality_raw_invalid_label_rate", "Invalid label rate in the raw dataset.", ["version"])
RAW_SYNTHETIC_RATE = Gauge("data_quality_raw_synthetic_rate", "Synthetic row rate in the raw dataset.", ["version"])
RAW_LABEL_RATIO = Gauge("data_quality_raw_label_ratio", "Class distribution ratio in the raw dataset.", ["version", "label"])
BATCH_ROWS = Gauge("data_quality_batch_rows", "Row count in batch dataset split.", ["split", "batch_version"])
BATCH_DUPLICATE_TEXT_RATE = Gauge("data_quality_batch_duplicate_text_rate", "Duplicate text rate in the batch train dataset.", ["batch_version"])
BATCH_NULL_TEXT_RATE = Gauge("data_quality_batch_null_text_rate", "Null text rate in the batch train dataset.", ["batch_version"])
BATCH_FEEDBACK_APPROVAL_RATE = Gauge("data_quality_batch_feedback_approval_rate", "Feedback approval rate captured in batch manifest.", ["batch_version"])
BATCH_FEEDBACK_ROWS_MERGED = Gauge("data_quality_batch_feedback_rows_merged", "Feedback rows merged into batch training data.", ["batch_version"])
BATCH_ONLINE_LOG_ROWS = Gauge("data_quality_batch_online_log_rows", "Online log rows merged into batch training data.", ["batch_version"])
ONLINE_EVENTS = Gauge("data_quality_online_events", "Number of online log events scanned.")
ONLINE_LOG_FILES = Gauge("data_quality_online_log_files", "Number of online log object files scanned.")
ONLINE_ERROR_RATE = Gauge("data_quality_online_error_rate", "Fraction of online events with failed requests.")
ONLINE_STYLE_RATIO = Gauge("data_quality_online_style_ratio", "Observed distribution of rewrite styles in online logs.", ["style"])
FEEDBACK_RECENT_ROWS = Gauge("data_quality_feedback_recent_rows", "Recent feedback rows within lookback window.", ["lookback_days"])
FEEDBACK_APPROVAL_RATE = Gauge("data_quality_feedback_approval_rate", "Approval rate from recent feedback records.", ["lookback_days"])
FEEDBACK_CORRECTION_RATE = Gauge("data_quality_feedback_correction_rate", "Correction/edit rate from recent feedback records.", ["lookback_days"])
FEEDBACK_PREFERRED_TEXT_RATE = Gauge("data_quality_feedback_preferred_text_rate", "Rate of feedback rows with preferred_text present.", ["lookback_days"])
FEEDBACK_TONE_RATIO = Gauge("data_quality_feedback_tone_ratio", "Distribution of shown tones in recent feedback.", ["lookback_days", "tone"])
DRIFT_PSI = Gauge("data_quality_drift_psi", "Population Stability Index between raw train and batch train.", ["feature", "raw_version", "batch_version"])


def _read_feedback_frame(store: MinioStore, lookback_days: int) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)
    rows = []
    for key in store.list_keys("feedback/"):
        parts = key.split("/")
        if len(parts) < 3 or not key.endswith(".json"):
            continue
        try:
            day = datetime.strptime(parts[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if day >= cutoff:
            rows.append(store.read_json(key))
    return pd.DataFrame(rows)


def _read_online_frame(store: MinioStore) -> pd.DataFrame:
    rows: list[dict] = []
    for key in store.list_keys("online_logs/"):
        payload = store.read_json(key)
        if isinstance(payload, list):
            rows.extend(payload)
    return pd.DataFrame(rows)


def refresh_metrics(config_path: str) -> None:
    config = load_config(config_path)
    store = MinioStore(config.storage)
    raw_version = config.dataset.raw_version
    batch_version = config.dataset.batch_version
    lookback = str(config.dataset.lookback_days)

    train = store.read_parquet(f"raw/{raw_version}/train.parquet")
    val = store.read_parquet(f"raw/{raw_version}/val.parquet")
    test = store.read_parquet(f"raw/{raw_version}/test.parquet")
    raw_full = pd.concat([train, val, test], ignore_index=True)

    RAW_ROWS.labels(split="train", version=raw_version).set(len(train))
    RAW_ROWS.labels(split="val", version=raw_version).set(len(val))
    RAW_ROWS.labels(split="test", version=raw_version).set(len(test))
    RAW_NULL_TEXT_RATE.labels(version=raw_version).set(null_rate(raw_full["text"]))
    RAW_DUPLICATE_TEXT_RATE.labels(version=raw_version).set(duplicate_rate(raw_full["text"]))
    RAW_INVALID_LABEL_RATE.labels(version=raw_version).set(invalid_label_rate(raw_full["binary_label"]))
    synthetic = raw_full["synthetic"].fillna(False).sum() if "synthetic" in raw_full.columns else 0
    RAW_SYNTHETIC_RATE.labels(version=raw_version).set(ratio(float(synthetic), float(len(raw_full))))
    for label, value in class_distribution(raw_full["binary_label"]).items():
        RAW_LABEL_RATIO.labels(version=raw_version, label=label).set(value)

    batch_train = store.read_parquet(f"batch/{batch_version}/train.parquet")
    batch_test = store.read_parquet(f"batch/{batch_version}/test.parquet")
    batch_manifest = store.read_json(f"batch/{batch_version}/manifest.json")

    BATCH_ROWS.labels(split="train", batch_version=batch_version).set(len(batch_train))
    BATCH_ROWS.labels(split="test", batch_version=batch_version).set(len(batch_test))
    BATCH_DUPLICATE_TEXT_RATE.labels(batch_version=batch_version).set(duplicate_rate(batch_train["text"]))
    BATCH_NULL_TEXT_RATE.labels(batch_version=batch_version).set(null_rate(batch_train["text"]))
    BATCH_FEEDBACK_APPROVAL_RATE.labels(batch_version=batch_version).set(float(batch_manifest.get("feedback_approval_rate") or 0.0))
    BATCH_FEEDBACK_ROWS_MERGED.labels(batch_version=batch_version).set(float(batch_manifest.get("feedback_rows_merged") or 0.0))
    BATCH_ONLINE_LOG_ROWS.labels(batch_version=batch_version).set(float(batch_manifest.get("online_log_rows") or 0.0))

    online = _read_online_frame(store)
    ONLINE_EVENTS.set(len(online))
    ONLINE_LOG_FILES.set(len(store.list_keys("online_logs/")))
    if online.empty:
        ONLINE_ERROR_RATE.set(0.0)
    else:
        statuses = online["http_status"].fillna(0)
        ONLINE_ERROR_RATE.set(ratio(float((statuses == 0).sum() + (statuses >= 500).sum()), float(len(online))))
        rewrite_styles = online["input"].apply(lambda x: x.get("rewrite_style") if isinstance(x, dict) else "unknown")
        for style, value in rewrite_styles.value_counts(normalize=True).round(4).to_dict().items():
            ONLINE_STYLE_RATIO.labels(style=str(style)).set(float(value))

    feedback = _read_feedback_frame(store, config.dataset.lookback_days)
    FEEDBACK_RECENT_ROWS.labels(lookback_days=lookback).set(len(feedback))
    if feedback.empty:
        FEEDBACK_APPROVAL_RATE.labels(lookback_days=lookback).set(0.0)
        FEEDBACK_CORRECTION_RATE.labels(lookback_days=lookback).set(0.0)
        FEEDBACK_PREFERRED_TEXT_RATE.labels(lookback_days=lookback).set(0.0)
    else:
        approvals = feedback["user_action"].isin(["thumbs_up", "selected"])
        corrections = feedback["user_action"].isin(["thumbs_down", "edited"])
        preferred_text = feedback.get("preferred_text", pd.Series(dtype=str)).fillna("").astype(str).str.strip() != ""
        FEEDBACK_APPROVAL_RATE.labels(lookback_days=lookback).set(ratio(float(approvals.sum()), float(len(feedback))))
        FEEDBACK_CORRECTION_RATE.labels(lookback_days=lookback).set(ratio(float(corrections.sum()), float(len(feedback))))
        FEEDBACK_PREFERRED_TEXT_RATE.labels(lookback_days=lookback).set(ratio(float(preferred_text.sum()), float(len(feedback))))
        tone_dist = feedback.get("tone_shown", pd.Series(dtype=str)).fillna("unknown").value_counts(normalize=True).round(4)
        for tone, value in tone_dist.to_dict().items():
            FEEDBACK_TONE_RATIO.labels(lookback_days=lookback, tone=str(tone)).set(float(value))

    ref_word_count = train["text"].fillna("").astype(str).str.split().str.len()
    cur_word_count = batch_train["text"].fillna("").astype(str).str.split().str.len()
    ref_formality = estimated_formality(train["text"])
    cur_formality = estimated_formality(batch_train["text"])
    DRIFT_PSI.labels(feature="word_count", raw_version=raw_version, batch_version=batch_version).set(psi(ref_word_count, cur_word_count))
    DRIFT_PSI.labels(feature="estimated_formality", raw_version=raw_version, batch_version=batch_version).set(psi(ref_formality, cur_formality))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Prometheus exporter for data quality metrics.")
    parser.add_argument("--config", required=True, help="Path to YAML config.")
    parser.add_argument("--port", type=int, default=9108, help="Metrics port.")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Refresh interval.")
    args = parser.parse_args()

    start_http_server(args.port)
    while True:
        try:
            refresh_metrics(args.config)
            EXPORTER_UP.set(1)
            EXPORTER_LAST_SUCCESS.set(time.time())
        except Exception:
            EXPORTER_UP.set(0)
        time.sleep(args.interval_seconds)
