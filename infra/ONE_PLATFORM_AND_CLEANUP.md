# One platform policy and Chameleon cleanup

This document is the **team agreement** for the integrated MLOps stack: a single shared **MLflow**, **MinIO**, and **Prometheus/Grafana/Alertmanager** on the course cluster, plus a checklist to remove duplicate or abandoned resources before submission.

---

## Canonical platform components

| Component | Kubernetes namespace | Declared in repo | Applied by |
|-----------|----------------------|------------------|------------|
| MLflow | `ml-platform` | [`k8s/platform/mlflow/`](../k8s/platform/mlflow/) | `deploy_platform.yml` |
| MinIO | `ml-platform` | [`k8s/platform/minio/`](../k8s/platform/minio/) | `deploy_platform.yml` |
| Prometheus + Grafana + Alertmanager | `monitoring` | [`k8s/platform/observability/`](../k8s/platform/observability/) | `deploy_platform.yml` |
| Namespaces for Zulip + ML roles | (see table below) | [`k8s/base/namespaces.yaml`](../k8s/base/namespaces.yaml) | `deploy_platform.yml` (same apply step) |

**Rule:** Do not run a second MLflow instance, second MinIO deployment for the same purpose, or a parallel “course monitoring” stack unless the team documents an exceptional technical reason (rubric: avoid duplicate role-owned stacks).

---

## Who runs which Ansible playbook (order matters)

Run from `infra/ansible/` with your `inventory.ini` (see [`README.md`](ansible/README.md)).

| Order | Playbook | What it does | Depends on |
|-------|----------|----------------|--------------|
| 1 | [`playbooks/k3s_install.yml`](ansible/playbooks/k3s_install.yml) | Installs k3s, kubeconfig for `cc` | Terraform VM reachable |
| 2 | [`playbooks/deploy_platform.yml`](ansible/playbooks/deploy_platform.yml) | Copies `k8s/` to `/opt/mlops_project/k8s/` on the VM; `kubectl apply` **namespaces**, **MLflow**, **MinIO**, **Prometheus/Grafana/Alertmanager**; bootstraps `minio-root` and `grafana-admin` Secrets if missing | k3s installed |
| 3 | [`playbooks/deploy_zulip.yml`](ansible/playbooks/deploy_zulip.yml) | Helm install/upgrade **Zulip** (docker-zulip chart) | Step 2 (so `values-chameleon.yaml` exists on VM); VM-local `values-secret.yaml` |
| 4 | [`playbooks/deploy_ml_workloads.yml`](ansible/playbooks/deploy_ml_workloads.yml) | Replicates `minio-root` into `ml-data`; `kubectl apply -k` for **`k8s/data/`**, **`k8s/inference/`**, **`k8s/training/`** | Step 2 (**MinIO** and namespaces must exist) |

**DevOps owner:** Communicate this sequence in standups so Training/Serving/Data do not `helm install` their own MLflow or stand up ad hoc MinIO on the same VM.

**Optional:** [`playbooks/install_sealed_secrets_controller.yml`](ansible/playbooks/install_sealed_secrets_controller.yml) and Sealed Secrets demo under [`k8s/addons/sealed-secrets/`](../k8s/addons/sealed-secrets/) — does not replace the platform stack above.

---

## Namespaces expected on the integrated cluster

Declared in [`k8s/base/namespaces.yaml`](../k8s/base/namespaces.yaml):

| Namespace | Purpose |
|-----------|---------|
| `zulip` | Zulip Helm release |
| `ml-platform` | MLflow, MinIO |
| `monitoring` | Prometheus, Grafana, Alertmanager |
| `ml-data` | Data workloads (ingest, online, batch, …) |
| `ml-serving` | Classifier + generator inference |
| `ml-training` | Training Jobs |

Stray namespaces (e.g. old experiments named `test-*`, duplicate `mlflow`) should be removed or merged into this layout during cleanup.

---

## Optional Terraform Kubernetes apps — do not duplicate

The directory [`infra/terraform/k8s-apps/`](terraform/k8s-apps/) can install **additional** Helm releases (including an optional Bitnami MLflow). The **default course path** in this repo is **Ansible + Kustomize** via `deploy_platform.yml`.

- If the team uses **`deploy_platform.yml`**, keep Terraform’s **`deploy_mlflow_helm`** (or equivalent) **off** unless you intentionally replace the Kustomize MLflow and have a migration plan.
- Running **both** Ansible MLflow and Terraform Bitnami MLflow yields duplicate tracking stores and confuses grading (“which MLflow is canonical?”).

---

## Chameleon cleanup checklist (OpenStack + cluster)

Execute with your project’s **OpenStack** credentials and **`kubectl`** against the team cluster. Adjust names to what you actually created during silo work.

### OpenStack (Horizon or CLI)

- [ ] **Security groups:** List rules; delete unused groups not attached to the current VM or load balancers. Keep one clear group for the integration VM (SSH 22, HTTP 80, HTTPS 443 as required).
- [ ] **Floating IPs:** Release FIPs no longer attached to an active server.
- [ ] **Volumes / snapshots:** Delete orphaned volumes from old VM deletes if you do not need them.
- [ ] **Key pairs / rules:** Remove only what is truly abandoned; do not delete keys still in `terraform.tfvars`.

### MinIO (via console or `mc`)

- [ ] List buckets; remove **test** or **duplicate** buckets if the team agreed on a single naming scheme (see [`k8s/ML_INTEGRATION.md`](../k8s/ML_INTEGRATION.md) for `zulip-rewriter` vs training bucket alignment).
- [ ] Do **not** delete buckets that still hold the only copy of production-emulation or training data unless Data confirms.

### Kubernetes

```bash
# Namespaces (expect the six in namespaces.yaml plus kube-* and default)
kubectl get ns

# Helm releases (expect one Zulip release; no duplicate mlflow)
helm list -A

# Obvious duplicates: old release in wrong namespace, second mlflow, etc.
# helm uninstall <release> -n <namespace>   # only after team confirms
```

- [ ] Remove **duplicate Helm releases** for the same app (e.g. two Zulip installs, experimental `mlflow-foo`).
- [ ] Delete abandoned **test Deployments/Jobs** in `ml-data`, `ml-serving`, `ml-training` that are not part of the integrated demo.
- [ ] Confirm **one** MLflow UI resolves (`mlflow.<fip>.nip.io` or your Ingress) and **one** MinIO console.

### Evidence for graders

After cleanup, capture:

- Screenshot or `kubectl get ns` / `helm list -A` / OpenStack resource list showing **no duplicate** platform stacks.
- One paragraph in your write-up: **canonical** MLflow URI, MinIO endpoint, and Grafana URL.

---

## Related docs

- [`infra/ansible/README.md`](ansible/README.md) — inventory, UTF-8 notes, full playbook sequence.
- [`GETTING_STARTED.md`](../GETTING_STARTED.md) — TLS, Zulip values, verification curls.
- [`k8s/ML_INTEGRATION.md`](../k8s/ML_INTEGRATION.md) — GHCR images, MinIO buckets, applying ML manifests.
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — layer diagram.
