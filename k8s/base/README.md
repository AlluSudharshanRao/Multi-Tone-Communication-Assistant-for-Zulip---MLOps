# Base namespaces

`namespaces.yaml` defines:

| Namespace     | Intended use              |
|---------------|---------------------------|
| `zulip`       | Zulip Helm release        |
| `ml-platform` | MLflow and shared tooling |
| `ml-training` | Training jobs (teammate)  |
| `ml-serving`  | Inference (teammate)      |
| `ml-data`     | Data teammate stack (Jobs + Deployments) |
| `monitoring`  | Prometheus + Grafana      |

If the same namespaces are created with **Terraform** (`infra/terraform/k8s-apps/namespaces.tf`), **do not** also apply this file — pick **one** mechanism to avoid drift.
