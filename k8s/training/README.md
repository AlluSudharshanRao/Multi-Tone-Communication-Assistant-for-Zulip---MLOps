# Training → Serving wiring (end-to-end)

This repo supports an end-to-end path where a **training run registers a model in MLflow Model Registry**, and the **serving tier loads the model by alias** (no manual copying of artifacts into the serving container).

## What is wired

- Training logs metrics + artifacts to MLflow (`ml-platform`).
- `register_and_alias_latest.py` registers the latest successful run(s) and updates aliases like `canary` / `prod`.
- Serving loads the classifier model via `CLASSIFIER_MODEL_URI=models:/tone-classifier@prod` (production tier) or `@canary` (canary tier).
- Zulip user flow uses `zulip-bridge` → `tone-generator-prod` → `classifier-pytorch-prod`, so the UI hits the model-backed path.

## How to run the end-to-end update

Run these on the cluster VM (or any machine with working `kubectl` for the cluster).

### 1) Run classifier training (produces a new MLflow run)

```bash
kubectl delete job -n ml-training classifier-training --ignore-not-found
kubectl apply -f k8s/training/classifier-training-job.yaml
kubectl logs -n ml-training -l job-name=classifier-training -f
```

### 2) Register + alias the latest successful model run

```bash
kubectl delete job -n ml-training register-and-alias-latest --ignore-not-found
kubectl apply -f k8s/training/register-and-alias-latest-job.yaml
kubectl logs -n ml-training -l job-name=register-and-alias-latest -f
```

### 3) Restart serving to pick up the new alias

The production classifier deployment is configured to download from:

- `models:/tone-classifier@prod`

Restarting the deployment forces a re-resolve and re-download:

```bash
kubectl rollout restart -n ml-serving deployment/classifier-pytorch-prod
kubectl rollout status  -n ml-serving deployment/classifier-pytorch-prod --timeout=600s
```

## Troubleshooting

- **Job fails: secret `minio-root` not found in `ml-training`**  
  Ensure you ran `infra/ansible/playbooks/deploy_ml_workloads.yml` after `deploy_platform.yml`. That playbook replicates `minio-root` into both `ml-data` and `ml-training`.

- **Serving fails to load model URI**  
  Confirm MLflow has Model Registry enabled and the alias exists. You can test in the MLflow UI.

