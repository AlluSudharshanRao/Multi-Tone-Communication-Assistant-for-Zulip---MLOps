# MLOps Project - Zulip on Chameleon

This repository tracks my DevOps/platform work for the MLOps course project: provisioning and operating a self-hosted Zulip + platform services stack on Chameleon Cloud using Infrastructure as Code and Configuration as Code.

## Project objective

Build a reproducible deployment pipeline from cloud resources to running Kubernetes workloads:

- Provision OpenStack infrastructure on Chameleon (`KVM@TACC`) with Terraform.
- Configure and operate Kubernetes (k3s) with Ansible.
- Deploy platform services (MLflow, MinIO) and application service (Zulip via Helm).
- Document the full engineering flow, issues, fixes, and operational evidence.

## Current implementation status

- OpenStack VM + networking + floating IP provisioned and reachable.
- k3s installed and verified (default **Traefik** ingress controller).
- **MLflow** in `ml-platform`: Deployment + PVC + ClusterIP Service + **Ingress** (`mlflow.<fip>.nip.io`), TLS via shared secret `chameleon-nip-tls` (self-signed for demos).
- **MinIO** in `ml-platform`: S3-compatible API + web console; **Ingresses** `minio.<fip>.nip.io` and `minio-console.<fip>.nip.io`; credentials in Secret `minio-root` (bootstrapped by `deploy_platform.yml`).
- **Prometheus** + **Grafana** in `monitoring`: PVC-backed TSDB and Grafana data; **Ingress** for Grafana (`grafana.<fip>.nip.io`) and optional public **Ingress** for Prometheus (`prometheus.<fip>.nip.io`) in `k8s/platform/observability/`.
- **Zulip** from `docker-zulip/helm/zulip`: ClusterIP Service + **Ingress** (`zulip.<fip>.nip.io`), same TLS pattern; values in `k8s/zulip/values-chameleon.yaml` include proxy trust (`LOADBALANCER_IPS` / `SETTING_*`) for Traefik.
- Browser access: **HTTPS** on port **443** (OpenStack SG must allow **80** and **443**). Chrome shows “Not secure” for self-signed certs until trusted or replaced with Let’s Encrypt.
- Org creation: **`/new/`** enabled for class demos via `SETTING_OPEN_REALM_CREATION` (see docs); single-use CLI links still work.
- Detailed ops docs: keep under `Docs/` locally (that tree is **not** tracked in Git; see `.gitignore`).

## Repository structure

- [`GETTING_STARTED.md`](GETTING_STARTED.md) — **end-to-end usage**: what is implemented and command-by-command runbook (outside `Docs/`).
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system diagram and IaC/CaC split.
- [`infrastructure-requirements.md`](infrastructure-requirements.md) — **DevOps deliverable**: CPU/memory/PVC table, Chameleon right-sizing evidence template, Zulip vs platform split.
- `Docs/` — milestone PDFs and personal write-ups **local only** (gitignored). The joint **container ↔ manifest** table lives in [`k8s/containers-matrix.md`](k8s/containers-matrix.md).
- `infra/`
  - `terraform/openstack/`: Chameleon infrastructure provisioning (VM/network/FIP).
  - `terraform/k8s-apps/`: optional Terraform-managed k8s app path.
  - `ansible/`: k3s install and app deployment playbooks.
- `k8s/`
  - Kubernetes manifests and Helm value overlays (MLflow, MinIO, Prometheus/Grafana, Zulip, teammate training/serving/data workloads). Index: [`k8s/README.md`](k8s/README.md). **Container ↔ Dockerfile / manifest table:** [`k8s/containers-matrix.md`](k8s/containers-matrix.md).
- `contracts/`
  - Sample request/response artifacts used by project milestones.
- `zulip/`
  - Upstream Zulip source checkout used for product/context reference.

## How this repo is used

1. Provision cloud resources via Terraform.
2. Configure cluster and apply platform workloads via Ansible.
3. Deploy Zulip with Helm values tuned for Chameleon/k3s.
4. Validate runtime with `kubectl` and capture evidence for milestone deliverables.

## Notes

- This is a personal working repository for my DevOps track deliverables.
- Secrets are not committed (`values-secret.yaml`, credentials, private keys are excluded via `.gitignore`).
- For a **public** clone: see [`SECURITY.md`](SECURITY.md). Tracked Ingress YAML may pin **one** team floating IP (`*.nip.io`); replace with **your** IP, TLS SANs, and `SETTING_EXTERNAL_HOST` before apply.

## Before you push (quick check)

From the repo root (Git Bash or similar):

```bash
git grep -i "BEGIN.*PRIVATE KEY" -- infra k8s README.md GETTING_STARTED.md ARCHITECTURE.md SECURITY.md 2>/dev/null || true
git grep -i "application_credential_secret" -- "*.tf" "*.yaml" "*.yml" 2>/dev/null || true
```

Inspect any unexpected hits. Paths like `terraform.tfvars` and `inventory.ini` must stay untracked (see `.gitignore`).
