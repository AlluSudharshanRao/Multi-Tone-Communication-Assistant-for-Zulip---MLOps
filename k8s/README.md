# Kubernetes Manifests

This directory contains the cluster workloads applied by Ansible and, when needed, direct `kubectl apply -k`.

## Layout

| Path | Namespace | Purpose |
|------|-----------|---------|
| `base/` | cluster-wide | namespace definitions |
| `secrets/` | mixed | centralized SealedSecret manifests for shared runtime secrets |
| `platform/mlflow/` | `ml-platform` | MLflow |
| `platform/minio/` | `ml-platform` | MinIO API and console |
| `platform/observability/` | `monitoring` | Prometheus, Grafana, Alertmanager |
| `platform/backups/` | mixed | CronJobs that back up PVC-backed state to Chameleon object storage |
| `zulip/` | `zulip` | Zulip Helm values and secret template |
| `data/` | `ml-data` | ingest, batch, online, and generator data workloads |
| `training/` | `ml-training` | classifier training, generator training, register bundle |
| `inference/` | `ml-serving` | classifier and generator deployments, overlays, ingress |
| `integration/` | `ml-serving` | Zulip bridge deployment and ingress |
| `addons/sealed-secrets/` | varies | optional sealed secrets controller |

## Notes

- Floating-IP-based hostnames are rewritten on the VM during Ansible deploy.
- `ml-serving` uses tiered inference:
  - `staging`
  - `canary`
  - `prod`
- The tone generator source file used by the cluster is mounted from a ConfigMap generated in `k8s/inference/base/`.

## Typical apply paths

- Platform: handled by `deploy_platform.yml`
- Zulip: handled by `deploy_zulip.yml`
- ML workloads: handled by `deploy_ml_workloads.yml`

Direct use is still possible for debugging:

```bash
kubectl apply -k k8s/platform/mlflow/
kubectl apply -k k8s/platform/minio/
kubectl apply -k k8s/platform/observability/
kubectl apply -k k8s/inference/
kubectl apply -k k8s/integration/
kubectl apply -k k8s/training/
kubectl apply -k k8s/training/register-bundle/
kubectl apply -k k8s/data/
```
