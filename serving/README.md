# Serving (tone classifier + generator)

## Quick start

```bash
cd serving/
docker compose build
docker compose up -d classifier-pytorch generator
```

Benchmarks and smoke tests live under `evaluate/` and `scripts/`.

## Rubric / ops (serving-owned)

- **Runbook:** [OBSERVABILITY_AND_RELEASE.md](./OBSERVABILITY_AND_RELEASE.md) — metrics, model-output checks, feedback handoff, promotion/rollback triggers, E2E boundary.
- **Prometheus (compose profile `monitoring`):** `prometheus.yml` + `alerts/serving.rules.yml`.
- **Grafana:** import `grafana/dashboards/serving-overview.json` (choose your Prometheus datasource UID when prompted).
- **Post-deploy smoke:** `bash scripts/smoke_predict_generate.sh http://127.0.0.1:8001 http://127.0.0.1:8010`
