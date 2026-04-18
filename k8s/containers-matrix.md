# Container inventory (team + platform)

Each row is one **runnable container image** (or one Helm/chart bundle where noted). Training, serving, and data owners maintain Dockerfile / Compose links; DevOps provides the **equivalent Kubernetes manifest** path in this repo. **Deploying** those workloads on Chameleon is optional until the team integrates images and secrets; the manifests alone satisfy the “corresponding K8s manifest” requirement.

| Role | Container / workload | Purpose | Dockerfile or Compose | Kubernetes manifest (this repo) | Notes |
|------|----------------------|---------|------------------------|-----------------------------------|--------|
| **Platform** | `mlflow` (custom Deployment) | Experiment tracking UI + API | Image + args in manifest ([upstream](https://github.com/mlflow/mlflow)) | [`platform/mlflow/`](platform/mlflow/) | Primary path; optional Bitnami via [`../infra/terraform/k8s-apps/`](../infra/terraform/k8s-apps/) |
| **Platform** | MinIO (`minio/minio`) | S3-compatible object store | [MinIO image](https://hub.docker.com/r/minio/minio) | [`platform/minio/`](platform/minio/) | Credentials: `minio-root` Secret (Ansible) |
| **Platform** | Prometheus + Grafana | Metrics + dashboards | Images in manifests | [`platform/observability/`](platform/observability/) | |
| **Platform** | Zulip + PostgreSQL, Redis, RabbitMQ, Memcached | Team chat product | App: [zulip/zulip](https://github.com/zulip/zulip); chart: [docker-zulip](https://github.com/zulip/docker-zulip) | [`zulip/values-chameleon.yaml`](zulip/values-chameleon.yaml), [`zulip/values-secret.yaml.example`](zulip/values-secret.yaml.example), deploy [`../infra/ansible/playbooks/deploy_zulip.yml`](../infra/ansible/playbooks/deploy_zulip.yml) | |
| **Serving** | `tone-classifier` (PyTorch / ONNX / quantized) | Classifier API | [Dockerfile](https://github.com/rithwik0908/mlops-serving/blob/main/serving/classifier/Dockerfile) | [`inference/classifier-pytorch-deployment.yaml`](inference/classifier-pytorch-deployment.yaml), [`inference/classifier-onnx-deployment.yaml`](inference/classifier-onnx-deployment.yaml), [`inference/classifier-quantized-deployment.yaml`](inference/classifier-quantized-deployment.yaml) | Same image; `SERVING_BACKEND` selects backend |
| **Serving** | `tone-generator` | LLM rewrite API | [Dockerfile](https://github.com/rithwik0908/mlops-serving/blob/main/serving/generator/Dockerfile) | [`inference/generator-deployment.yaml`](inference/generator-deployment.yaml) | |
| **Training** | `classifier-training` | Fine-tune classifier | Teammate repo (Dockerfile path in Job comments) | [`training/classifier-training-job.yaml`](training/classifier-training-job.yaml) | Image: `ghcr.io/proj15/classifier-training:latest` — align tag with your registry |
| **Training** | `generator-training` | Fine-tune generator | Teammate repo | [`training/generator-training-job.yaml`](training/generator-training-job.yaml) | Image: `ghcr.io/proj15/generator-training:latest` |
| **Data** | `ingest` | Load data → MinIO | [`data/ingest/Dockerfile`](https://github.com/Hard-Hustler/Zulip_Chat_Feature/blob/main/data/ingest/Dockerfile) | [`data/data-ingest-job.yaml`](data/data-ingest-job.yaml) | Part of [`docker-compose.yml`](https://github.com/Hard-Hustler/Zulip_Chat_Feature/blob/main/docker-compose.yml); Job |
| **Data** | `online` | HTTP `/rewrite` service | [`data/online/Dockerfile`](https://github.com/Hard-Hustler/Zulip_Chat_Feature/blob/main/data/online/Dockerfile) | [`data/data-online-deployment.yaml`](data/data-online-deployment.yaml), [`data/data-online-service.yaml`](data/data-online-service.yaml) | Deployment + ClusterIP |
| **Data** | `generator` | Calls `online`, writes to MinIO | [`data/generator/Dockerfile`](https://github.com/Hard-Hustler/Zulip_Chat_Feature/blob/main/data/generator/Dockerfile) | [`data/data-generator-deployment.yaml`](data/data-generator-deployment.yaml) | `REWRITE_URL` → in-cluster `data-online` Service |
| **Data** | `batch` | Batch pipeline | [`data/batch/Dockerfile`](https://github.com/Hard-Hustler/Zulip_Chat_Feature/blob/main/data/batch/Dockerfile) | [`data/data-batch-job.yaml`](data/data-batch-job.yaml) | Compose `profiles: batch` → apply Job when needed |
| **Platform (optional)** | Sealed Secrets controller | Git-safe encrypted secrets | [Upstream image](https://github.com/bitnami-labs/sealed-secrets) | [`addons/sealed-secrets/`](addons/sealed-secrets/) | Extra-credit / bonus path |

**Apply bundles**

- All inference Deployments: `kubectl apply -k k8s/inference/`
- Data stack (optional deploy): `kubectl apply -k k8s/data/` (copy `minio-root` Secret into `ml-data` first; bucket `zulip-rewriter` on platform MinIO)
- Namespaces: `kubectl apply -f k8s/base/namespaces.yaml`

**Maintenance:** Replace placeholder `ghcr.io/proj15/...` image names with your team’s registry paths when images are published; add permanent Dockerfile links in the table for training/data rows when repos are final.
