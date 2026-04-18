# Container inventory (team + platform)

Each row is one **runnable container image** (or one Helm/chart bundle where noted). Training, serving, and data owners maintain Dockerfile / Compose links; DevOps provides the **equivalent Kubernetes manifest** path in this repo. **Deploying** those workloads on Chameleon is optional until the team integrates images and secrets; the manifests alone satisfy the “corresponding K8s manifest” requirement.

| Role | Container / workload | Purpose | Dockerfile or Compose | Kubernetes manifest (this repo) | Notes |
|------|----------------------|---------|------------------------|-----------------------------------|--------|
| **Platform** | `mlflow` (custom Deployment) | Experiment tracking UI + API | Image + args in manifest ([upstream](https://github.com/mlflow/mlflow)) | [`platform/mlflow/`](platform/mlflow/) | Primary path; optional Bitnami via [`../infra/terraform/k8s-apps/`](../infra/terraform/k8s-apps/) |
| **Platform** | MinIO (`minio/minio`) | S3-compatible object store | [MinIO image](https://hub.docker.com/r/minio/minio) | [`platform/minio/`](platform/minio/) | Credentials: `minio-root` Secret (Ansible) |
| **Platform** | Prometheus + Grafana | Metrics + dashboards | Images in manifests | [`platform/observability/`](platform/observability/) | |
| **Platform** | Zulip + PostgreSQL, Redis, RabbitMQ, Memcached | Team chat product | App: [zulip/zulip](https://github.com/zulip/zulip); chart: [docker-zulip](https://github.com/zulip/docker-zulip) | [`zulip/values-chameleon.yaml`](zulip/values-chameleon.yaml), [`zulip/values-secret.yaml.example`](zulip/values-secret.yaml.example), deploy [`../infra/ansible/playbooks/deploy_zulip.yml`](../infra/ansible/playbooks/deploy_zulip.yml) | |
| **Serving** | `tone-classifier` (PyTorch / ONNX / quantized) | Classifier API | [`serving/classifier/Dockerfile`](../serving/classifier/Dockerfile) (built by [`.github/workflows/build-push-ml-images.yml`](../.github/workflows/build-push-ml-images.yml)) | [`inference/classifier-pytorch-deployment.yaml`](inference/classifier-pytorch-deployment.yaml), [`inference/classifier-onnx-deployment.yaml`](inference/classifier-onnx-deployment.yaml), [`inference/classifier-quantized-deployment.yaml`](inference/classifier-quantized-deployment.yaml) | Image: `ghcr.io/<lowercase_github_owner>/mlops-serving-classifier:latest`; `SERVING_BACKEND` selects backend |
| **Serving** | `tone-generator` | LLM rewrite API | [`serving/generator/Dockerfile`](../serving/generator/Dockerfile) | [`inference/generator-deployment.yaml`](inference/generator-deployment.yaml) | Image: `ghcr.io/<lowercase_github_owner>/mlops-serving-generator:latest` |
| **Training** | `classifier-training` | Fine-tune classifier | [`training_proj15-main/training/Dockerfile`](../training_proj15-main/training/Dockerfile) | [`training/classifier-training-job.yaml`](training/classifier-training-job.yaml) | Image: `ghcr.io/<lowercase_github_owner>/mlops-training-classifier:latest` |
| **Training** | `generator-training` | Fine-tune generator | [`training_proj15-main/training/Dockerfile.llm`](../training_proj15-main/training/Dockerfile.llm) | [`training/generator-training-job.yaml`](training/generator-training-job.yaml) | Image: `ghcr.io/<lowercase_github_owner>/mlops-training-generator:latest` |
| **Data** | `ingest` | Load data → MinIO | [`data/ingest/Dockerfile`](../data/ingest/Dockerfile) | [`data/data-ingest-job.yaml`](data/data-ingest-job.yaml) | Image: `ghcr.io/<lowercase_github_owner>/mlops-data-ingest:latest`; see repo root [`docker-compose.yml`](../docker-compose.yml) |
| **Data** | `online` | HTTP `/rewrite` service | [`data/online/Dockerfile`](../data/online/Dockerfile) | [`data/data-online-deployment.yaml`](data/data-online-deployment.yaml), [`data/data-online-service.yaml`](data/data-online-service.yaml) | Image: `ghcr.io/<lowercase_github_owner>/mlops-data-online:latest` |
| **Data** | `generator` | Calls `online`, writes to MinIO | [`data/generator/Dockerfile`](../data/generator/Dockerfile) | [`data/data-generator-deployment.yaml`](data/data-generator-deployment.yaml) | Image: `ghcr.io/<lowercase_github_owner>/mlops-data-generator:latest`; `REWRITE_URL` → `data-online` Service |
| **Data** | `batch` | Batch pipeline | [`data/batch/Dockerfile`](../data/batch/Dockerfile) | [`data/data-batch-job.yaml`](data/data-batch-job.yaml) | Image: `ghcr.io/<lowercase_github_owner>/mlops-data-batch:latest` |
| **Platform (optional)** | Sealed Secrets controller | Git-safe encrypted secrets | [Upstream image](https://github.com/bitnami-labs/sealed-secrets) | [`addons/sealed-secrets/`](addons/sealed-secrets/) | Extra-credit / bonus path |

**Apply bundles**

- All inference Deployments: `kubectl apply -k k8s/inference/`
- Training Jobs: `kubectl apply -k k8s/training/`
- Data stack (optional deploy): `kubectl apply -k k8s/data/` (copy `minio-root` Secret into `ml-data` first; bucket `zulip-rewriter` on platform MinIO)
- Namespaces: `kubectl apply -f k8s/base/namespaces.yaml`

**Maintenance:** CI pushes `ghcr.io/<lowercase_github_owner>/mlops-*` (see [`.github/workflows/build-push-ml-images.yml`](../.github/workflows/build-push-ml-images.yml)). Manifests default to `ghcr.io/allusudharshanrao/mlops-*`; forks should replace that owner or adjust the workflow. Integration runbook: [`ML_INTEGRATION.md`](ML_INTEGRATION.md).
