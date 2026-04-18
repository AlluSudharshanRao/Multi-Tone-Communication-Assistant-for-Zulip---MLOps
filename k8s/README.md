# Kubernetes manifests (Chameleon / k3s)

Namespaces are defined in [`base/namespaces.yaml`](base/namespaces.yaml). Apply that once before role-specific workloads.

| Path | Namespace | Role |
|------|-----------|------|
| [`platform/mlflow/`](platform/mlflow/) | `ml-platform` | DevOps — MLflow |
| [`platform/minio/`](platform/minio/) | `ml-platform` | DevOps — MinIO |
| [`platform/observability/`](platform/observability/) | `monitoring` | DevOps — Prometheus / Grafana |
| [`zulip/`](zulip/) | `zulip` | Product — Helm values + docs (install via Ansible) |
| [`inference/`](inference/) | `ml-serving` | Serving — classifier + generator Deployments |
| [`training/`](training/) | `ml-training` | Training — Jobs |
| [`data/`](data/) | `ml-data` | Data — ingest/batch Jobs, online + generator Deployments (`kubectl apply -k k8s/data/`) |
| [`addons/sealed-secrets/`](addons/sealed-secrets/) | `kube-system` / `ml-platform` (demo) | Optional — Sealed Secrets controller + demo |

**Team container ↔ manifest table:** [`containers-matrix.md`](containers-matrix.md).
