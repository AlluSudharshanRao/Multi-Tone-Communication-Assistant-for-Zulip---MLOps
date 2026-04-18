# Kubernetes / Helm (CaC)

Terraform manages **cluster configuration**: namespaces and (optionally) Helm installs.

## Prereqs

- Working cluster and kubeconfig (e.g. after `openstack/` apply + k3s).
- Helm 3.x installed locally (Terraform `helm` provider shells out to Helm for some operations).

## Zulip

1. Vendor [docker-zulip](https://github.com/zulip/docker-zulip) and run `helm dependency update` in `helm/zulip/`.
2. Set `deploy_zulip = true`, `zulip_helm_chart_path`, and `zulip_values_files` (paths to YAML; include a **local** secrets values file path if needed — do not commit secrets).

## MLflow

- **Default in repo:** light stack via `kubectl apply -k ../../../k8s/platform/mlflow/` (no Helm).
- **Optional:** `deploy_mlflow_helm = true` uses the [Bitnami MLflow chart](https://github.com/bitnami/charts/tree/main/bitnami/mlflow) (pulls more dependencies; higher RAM/disk).

## Apply

```bash
terraform init
terraform apply -var="project_id_suffix=proj99" -var="kubeconfig_path=$HOME/.kube/config"
```

## Namespaces vs `k8s/base/namespaces.yaml`

Do **not** create the same namespaces twice. Either:

- Apply **only** this Terraform (remove duplicate `kubectl apply` for namespaces), or  
- Skip `namespaces.tf` (delete or use `terraform apply -target=helm_release...`) and keep using `k8s/base/namespaces.yaml`.

**Note:** This stack is **optional** CaC. The canonical teammate manifest paths for grading are under [`k8s/`](../../../k8s/README.md) (see [`k8s/containers-matrix.md`](../../../k8s/containers-matrix.md)).
