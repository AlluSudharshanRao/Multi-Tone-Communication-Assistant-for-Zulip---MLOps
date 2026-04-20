# Serving (tone classifier + generator)

## Quick start

```bash
cd serving/
docker compose build
docker compose up -d classifier-pytorch generator
```

Benchmarks and smoke tests live under `evaluate/` and `scripts/`.

- **Zulip / bot handoff:** [INTEGRATION_FOR_ZULIP.md](./INTEGRATION_FOR_ZULIP.md) — URLs, timeouts, curl examples.
- **Training -> serving promotion:** `scripts/example_promote_digest.sh` accepts MLflow Registry model URIs (aliases like `@prod`) and updates deployments so artifacts are pulled automatically at startup.

## Training to serving handoff (MLflow)

Runtime supports automatic artifact download from MLflow:

- Classifier:
  - `DUMMY_MODE=false`
  - `CLASSIFIER_MODEL_URI=models:/tone-classifier@prod` (preferred)
  - fallback: `MLFLOW_RUN_ID=<distilbert_run_id>` + `MLFLOW_ARTIFACT_PATH=model`
- Generator (SmolLM2 LoRA):
  - `DUMMY_MODE=false`
  - `GENERATOR_BACKEND=causal`
  - `MODEL_NAME=HuggingFaceTB/SmolLM2-135M-Instruct`
  - `GENERATOR_PEFT_MODEL_URI=models:/tone-generator-lora@prod` (preferred)
  - fallback: `PEFT_MLFLOW_RUN_ID=<lora_run_id>` + `PEFT_MLFLOW_ARTIFACT_PATH=lora_checkpoint`

Both services read `MLFLOW_TRACKING_URI` from env.

## Rubric / ops (serving-owned)

- **Runbook:** [OBSERVABILITY_AND_RELEASE.md](./OBSERVABILITY_AND_RELEASE.md) — metrics, model-output checks, feedback handoff, promotion/rollback triggers, E2E boundary.
- **Dashboards & metrics (team / DevOps — use these only):**  
  - Grafana: [https://grafana.129.114.27.192.nip.io/](https://grafana.129.114.27.192.nip.io/)  
  - Prometheus: [https://prometheus.129.114.27.192.nip.io/](https://prometheus.129.114.27.192.nip.io/)  
  Do not run a separate Grafana or duplicate dashboards for the same cluster; extend the existing dashboards if you need extra panels.
- **Optional local Prometheus (compose profile `monitoring`):** `prometheus.yml` only for laptop/VM demos without cluster access — not a second “source of truth.”
- **Alert rule reference (for DevOps to merge):** `alerts/serving.rules.yml` — not loaded by compose by default.
- **Post-deploy smoke:** `bash scripts/smoke_predict_generate.sh http://127.0.0.1:8001 http://127.0.0.1:8010`
