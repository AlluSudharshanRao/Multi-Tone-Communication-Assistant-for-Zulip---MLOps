# Zulip Data Quality Monitoring

This is a practical monitoring structure for the data layer in your repository:

- `data/ingest`: source corpus creation and split generation
- `data/generator`: live traffic simulation
- `data/batch`: batch dataset assembly from raw data, online logs, and feedback
- `data/online`: feature extraction and online logging
- `data/retrain_trigger`: retraining policy based on quality and drift proxies

## Architecture

```text
monitoring/
  data_quality/
    src/zulip_data_quality_monitoring/
    config/data_quality.yaml
    reports/
```

## What it measures

- Schema presence and allowed columns
- Null rates and duplicate rates
- Label validity and class balance
- Text-length quality and synthetic-data share
- Batch dataset freshness and manifest consistency
- Online traffic volume, failure rate, and rewrite-style coverage
- Feedback approval, correction, and training usability rates
- Simple drift signals between reference train data and current datasets

## Prometheus and Grafana

This package now supports live observability:

- `zulip-data-quality-exporter` scans MinIO and exposes Prometheus metrics on `/metrics`
- Prometheus scrapes the exporter pod
- Grafana dashboard JSON is provisioned under the existing `MLOps` folder
- Prometheus rules can alert on low approval, high online error rate, and drift

Main metric families:

- `data_quality_raw_*`
- `data_quality_batch_*`
- `data_quality_online_*`
- `data_quality_feedback_*`
- `data_quality_drift_psi`
- `data_quality_exporter_last_success_timestamp`

## Run

```bash
cd /Users/hardikamarwani/Documents/Codex/2026-04-23-write-me-a-proper-structure-of/zulip_data_quality_monitoring
python -m venv .venv
source .venv/bin/activate
pip install -e .
zulip-data-quality --config config/data_quality.yaml
```

To run the exporter locally instead:

```bash
zulip-data-quality-exporter --config config/data_quality.yaml
```

## Output

The command writes:

- `reports/data_quality_report.json`
- `reports/data_quality_report.md`

This monitoring code is built specifically around that layout.
