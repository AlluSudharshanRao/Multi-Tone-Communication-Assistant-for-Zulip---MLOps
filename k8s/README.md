# Kubernetes manifests (Chameleon / k3s)

Namespaces are defined in [`base/namespaces.yaml`](base/namespaces.yaml). Apply that once before role-specific workloads.

| Path | Namespace | Role |
|------|-----------|------|
| [`platform/mlflow/`](platform/mlflow/) | `ml-platform` | DevOps — MLflow |
| [`platform/minio/`](platform/minio/) | `ml-platform` | DevOps — MinIO |
| [`platform/observability/`](platform/observability/) | `monitoring` | DevOps — Prometheus / Grafana / Alertmanager (rules + HPA path in `inference/base`) |
| [`zulip/`](zulip/) | `zulip` | Product — Helm values + docs (install via Ansible) |
| [`inference/`](inference/) | `ml-serving` | Serving — tiered **staging / canary / prod** classifier + generator (`base/` + `overlays/`) + optional ONNX/quantized [`backends/`](inference/backends/); see [`inference/README.md`](inference/README.md) |
| [`training/`](training/) | `ml-training` | Training — Jobs |
| [`data/`](data/) | `ml-data` | Data — ingest/batch Jobs, online + generator Deployments (`kubectl apply -k k8s/data/`) |
| [`integration/`](integration/) | `ml-serving` | Zulip webhook **bridge** → `tone-generator-prod` (`kubectl apply -k k8s/integration/`) |
| [`addons/sealed-secrets/`](addons/sealed-secrets/) | `kube-system` / `ml-platform` (demo) | Optional — Sealed Secrets controller + demo |

**Team container ↔ manifest table:** [`containers-matrix.md`](containers-matrix.md).

**ML integration (build images + apply data / inference / training):** [`ML_INTEGRATION.md`](ML_INTEGRATION.md) and Ansible [`../infra/ansible/playbooks/deploy_ml_workloads.yml`](../infra/ansible/playbooks/deploy_ml_workloads.yml).
