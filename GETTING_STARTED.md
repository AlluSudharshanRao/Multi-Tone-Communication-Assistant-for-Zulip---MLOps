# Getting started

This guide describes **what this repository implements** and **how to run it end-to-end** with concrete commands. For a diagram and layer breakdown, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For secret-handling rules, see [`SECURITY.md`](SECURITY.md).

---

## Table of contents

1. [What this project delivers](#1-what-this-project-delivers)
2. [Prerequisites](#2-prerequisites)
3. [Repository layout (operational)](#3-repository-layout-operational)
4. [Local files you must create (never commit)](#4-local-files-you-must-create-never-commit)
5. [Step 1 — Align Kubernetes manifests with your environment](#5-step-1--align-kubernetes-manifests-with-your-environment)
6. [Step 2 — Provision the VM with Terraform](#6-step-2--provision-the-vm-with-terraform)
7. [Step 3 — Ansible inventory](#7-step-3--ansible-inventory)
8. [Step 4 — Install k3s](#8-step-4--install-k3s)
9. [Step 5 — Deploy namespaces, MLflow, MinIO, and observability](#9-step-5--deploy-namespaces-mlflow-minio-and-observability)
10. [Step 6 — TLS Secret for Ingress (Traefik)](#10-step-6--tls-secret-for-ingress-traefik)
11. [Step 7 — Prepare Zulip Helm values (secrets)](#11-step-7--prepare-zulip-helm-values-secrets)
12. [Step 8 — Deploy Zulip with Ansible + Helm](#12-step-8--deploy-zulip-with-ansible--helm)
13. [Step 9 — Verify](#13-step-9--verify)
14. [Operational notes](#14-operational-notes)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. What this project delivers

| Capability | Implementation |
|------------|----------------|
| Cloud VM + networking | Terraform in `infra/terraform/openstack/` |
| Single-node Kubernetes | **k3s** via `infra/ansible/playbooks/k3s_install.yml` |
| Ingress + HTTPS (demo) | k3s default **Traefik**; TLS Secret `chameleon-nip-tls` |
| Experiment tracking | **MLflow** in namespace `ml-platform` (`k8s/platform/mlflow/`) |
| Object storage (S3 API) | **MinIO** in namespace `ml-platform` (`k8s/platform/minio/`) |
| Metrics + dashboards | **Prometheus** + **Grafana** in namespace `monitoring` (`k8s/platform/observability/`) |
| Team chat (base product) | **Zulip** from [docker-zulip](https://github.com/zulip/docker-zulip) Helm chart, values under `k8s/zulip/` |

Traffic flow: **Internet → floating IP :443 → Traefik → Ingress rules → MLflow, MinIO (API + console), Grafana, Prometheus (optional Ingress), and Zulip Services.**

---

## 2. Prerequisites

- **Chameleon Cloud** project, lease/reservation, and an Ubuntu image (e.g. `CC-Ubuntu24.04`) on `KVM@TACC`.
- **OpenStack access**: application credential (recommended) or username/password; see `infra/terraform/openstack/providers.tf` comments.
- **Tools on your workstation** (Linux, WSL2, or macOS recommended):
  - Terraform ≥ 1.x
  - `ansible-core` in a **dedicated Python venv** (avoid broken Conda mixes)
  - `ssh`, `git`
- **OpenStack security groups**: allow **TCP 22** (SSH), **80** and **443** (HTTP/HTTPS for Ingress and ACME if used later).

---

## 3. Repository layout (operational)

| Path | Role |
|------|------|
| `infra/terraform/openstack/` | VM, network, floating IP |
| `infra/ansible/playbooks/k3s_install.yml` | Install k3s |
| `infra/ansible/playbooks/deploy_platform.yml` | Copy `k8s/` to VM; apply namespaces + MLflow + MinIO + Prometheus/Grafana |
| `infra/ansible/playbooks/deploy_zulip.yml` | Helm install/upgrade Zulip on the cluster |
| `k8s/base/namespaces.yaml` | `zulip`, `ml-platform`, teammate namespaces |
| `k8s/platform/mlflow/` | MLflow Deployment, PVC, Service, Ingress (Kustomize) |
| `k8s/platform/minio/` | MinIO Deployment, PVC, Service, API + console Ingresses (Kustomize) |
| `k8s/platform/observability/` | Prometheus + Grafana (PVCs, RBAC, Grafana Ingress) |
| `k8s/zulip/values-chameleon.yaml` | Non-secret Helm overrides (Ingress, storage class, proxy) |
| `k8s/zulip/values-secret.yaml.example` | Template for **local** `values-secret.yaml` (gitignored) |

---

## 4. Local files you must create (never commit)

| File | Purpose |
|------|---------|
| `infra/terraform/openstack/terraform.tfvars` | Real OpenStack IDs, reservation, keypair name (copy from `terraform.tfvars.example`) |
| `infra/ansible/inventory.ini` | VM floating IP + SSH key path (copy from `inventory.example.ini`) |
| `~/values-secret.yaml` **on the VM** | Zulip DB passwords, `SECRETS_secret_key`, `SETTING_EXTERNAL_HOST`, etc. |

These paths are listed in `.gitignore` / `SECURITY.md`. Do not paste credentials into issues or commits.

---

## 5. Step 1 — Align Kubernetes manifests with your environment

Tracked YAML uses a **placeholder floating IP** (e.g. RFC 5737 documentation addresses in examples). Before you apply manifests or generate TLS certs, replace it with **your** Chameleon floating IP everywhere it appears:

- `k8s/zulip/values-chameleon.yaml` — Ingress `host` / TLS `hosts`
- `k8s/platform/mlflow/ingress.yaml` — rules and TLS `hosts`
- `k8s/platform/minio/ingress-api.yaml` and `ingress-console.yaml` — API and console hosts / TLS `hosts`
- `k8s/platform/minio/deployment.yaml` — `MINIO_SERVER_URL` and `MINIO_BROWSER_REDIRECT_URL` (must match those Ingress URLs)
- `k8s/platform/observability/ingress-grafana.yaml` — Grafana host / TLS `hosts`
- `k8s/platform/observability/ingress-prometheus.yaml` — Prometheus host / TLS `hosts` (if used)
- `k8s/platform/observability/deployment-grafana.yaml` — `GF_SERVER_ROOT_URL` (must match Ingress URL)

Use a consistent hostname pattern, e.g.:

- Zulip: `zulip.<YOUR_FLOATING_IP>.nip.io`
- MLflow: `mlflow.<YOUR_FLOATING_IP>.nip.io`
- MinIO API: `minio.<YOUR_FLOATING_IP>.nip.io`
- MinIO console: `minio-console.<YOUR_FLOATING_IP>.nip.io`
- Grafana: `grafana.<YOUR_FLOATING_IP>.nip.io`
- Prometheus (optional): `prometheus.<YOUR_FLOATING_IP>.nip.io`

Commit or keep these edits local according to your policy; **never** commit secrets.

---

## 6. Step 2 — Provision the VM with Terraform

```bash
cd infra/terraform/openstack
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: network_id, key_pair, blazar_reservation_id (if used), etc.
```

Authenticate with **one** of: variables in `terraform.tfvars`, or environment variables. Example for **application credentials** (PowerShell):

```powershell
$env:OS_AUTH_URL = "https://kvm.tacc.chameleoncloud.org:5000/v3"
$env:OS_REGION_NAME = "KVM@TACC"
$env:OS_INTERFACE = "public"
$env:OS_IDENTITY_API_VERSION = "3"
$env:OS_AUTH_TYPE = "v3applicationcredential"
$env:OS_APPLICATION_CREDENTIAL_ID = "<id>"
$env:OS_APPLICATION_CREDENTIAL_SECRET = "<secret>"
$env:TF_VAR_application_credential_id = "<id>"
$env:TF_VAR_application_credential_secret = "<secret>"
```

Equivalent exports work in Bash. Then:

```bash
terraform init
terraform plan
terraform apply
terraform output
# Optional: stub for Ansible inventory
terraform output -raw ansible_inventory_ini
```

Record the **floating IP** from outputs for DNS/nip.io names and `inventory.ini`.

---

## 7. Step 3 — Ansible inventory

From `infra/ansible/`:

```bash
cp inventory.example.ini inventory.ini
```

Edit `inventory.ini`:

```ini
[chameleon]
<YOUR_FLOATING_IP>

[chameleon:vars]
ansible_user=cc
ansible_ssh_private_key_file=~/.ssh/<your-private-key>
```

**WSL note:** if the key lives under `/mnt/c/...`, copy it to `~/.ssh/` and `chmod 600`; OpenSSH often rejects world-readable Windows-mounted keys.

---

## 8. Step 4 — Install k3s

Use a venv with `ansible-core` installed, then:

```bash
cd infra/ansible
ansible-playbook -i inventory.ini playbooks/k3s_install.yml
```

k3s writes kubeconfig to `/etc/rancher/k3s/k3s.yaml` on the VM; the playbook copies it to `/home/cc/.kube/config` for user `cc`.

---

## 9. Step 5 — Deploy namespaces, MLflow, MinIO, and observability

```bash
cd infra/ansible
ansible-playbook -i inventory.ini playbooks/deploy_platform.yml
```

This copies `k8s/` to `/opt/mlops_project/k8s/` on the VM and runs:

- `kubectl apply -f .../k8s/base/namespaces.yaml`
- `kubectl apply -k .../k8s/platform/mlflow/`
- Creates Secret **`minio-root`** in **`ml-platform`** if it does not exist (`root-user=minioadmin`, random `root-password`).
- `kubectl apply -k .../k8s/platform/minio/`
- Creates Secret **`grafana-admin`** in **`monitoring`** if it does not exist (random password).
- `kubectl apply -k .../k8s/platform/observability/`

**MinIO credentials** (after first apply):

```bash
kubectl get secret minio-root -n ml-platform -o jsonpath='{.data.root-user}' | base64 -d && echo
kubectl get secret minio-root -n ml-platform -o jsonpath='{.data.root-password}' | base64 -d && echo
```

**Grafana password** (after first apply):

```bash
kubectl get secret grafana-admin -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d && echo
```

**Idempotency:** if you also create the same namespaces with Terraform (`infra/terraform/k8s-apps/`), use **one** mechanism only to avoid drift.

---

## 10. Step 6 — TLS Secret for Ingress (Traefik)

Ingress manifests reference TLS Secret name **`chameleon-nip-tls`** in namespaces **`zulip`**, **`ml-platform`**, and **`monitoring`**. Create a certificate whose **SAN** includes every public hostname (replace `<YOUR_FLOATING_IP>`):

```bash
# Run on any host with openssl; adjust Subject Alternative Names to match your Ingress hosts.
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=zulip.<YOUR_FLOATING_IP>.nip.io" \
  -addext "subjectAltName=DNS:zulip.<YOUR_FLOATING_IP>.nip.io,DNS:mlflow.<YOUR_FLOATING_IP>.nip.io,DNS:minio.<YOUR_FLOATING_IP>.nip.io,DNS:minio-console.<YOUR_FLOATING_IP>.nip.io,DNS:grafana.<YOUR_FLOATING_IP>.nip.io,DNS:prometheus.<YOUR_FLOATING_IP>.nip.io"
```

Load the Secret (run where `kubectl` uses the cluster kubeconfig, e.g. on the VM as `cc`):

```bash
export KUBECONFIG=$HOME/.kube/config

kubectl create secret tls chameleon-nip-tls -n zulip \
  --cert=tls.crt --key=tls.key --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret tls chameleon-nip-tls -n ml-platform \
  --cert=tls.crt --key=tls.key --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret tls chameleon-nip-tls -n monitoring \
  --cert=tls.crt --key=tls.key --dry-run=client -o yaml | kubectl apply -f -
```

Self-signed certificates will show browser warnings until trusted or replaced (e.g. Let’s Encrypt + cert-manager).

---

## 11. Step 7 — Prepare Zulip Helm values (secrets)

On the **VM** as `cc`:

```bash
git clone --depth 1 https://github.com/zulip/docker-zulip.git ~/docker-zulip

cp ~/docker-zulip/helm/zulip/values-local.yaml.example ~/values-secret.yaml
# Or, after deploy_platform:
# cp /opt/mlops_project/k8s/zulip/values-secret.yaml.example ~/values-secret.yaml

nano ~/values-secret.yaml
```

**Minimum alignment:**

- `SETTING_EXTERNAL_HOST` must **exactly match** the Zulip Ingress host (e.g. `zulip.<YOUR_FLOATING_IP>.nip.io`).
- Set strong values for `SECRETS_secret_key`, database passwords, etc. (quote numeric-looking passwords as YAML strings).
- If Helm merges drop proxy settings, ensure **`LOADBALANCER_IPS`** (e.g. k3s pod CIDR `10.42.0.0/16`) reaches the Zulip pod env — see `k8s/zulip/values-chameleon.yaml` comments.

Never commit `~/values-secret.yaml`.

---

## 12. Step 8 — Deploy Zulip with Ansible + Helm

From your **workstation** (paths below are **on the VM**):

```bash
cd infra/ansible

ansible-playbook -i inventory.ini playbooks/deploy_zulip.yml \
  -e zulip_chart_dir=/home/cc/docker-zulip/helm/zulip \
  -e project_id_suffix=proj99 \
  -e zulip_values_file=/opt/mlops_project/k8s/zulip/values-chameleon.yaml \
  -e zulip_secret_values_file=/home/cc/values-secret.yaml
```

Adjust `zulip_chart_dir` if you cloned docker-zulip elsewhere. The playbook runs `helm dependency update` and `helm upgrade --install`.

**Manual Helm equivalent** (on the VM), after `helm dependency update` inside the chart directory:

```bash
helm upgrade --install zulip-proj99 /home/cc/docker-zulip/helm/zulip \
  --namespace zulip \
  --kubeconfig "$HOME/.kube/config" \
  -f /opt/mlops_project/k8s/zulip/values-chameleon.yaml \
  -f "$HOME/values-secret.yaml"
```

---

## 13. Step 9 — Verify

On the VM (or with `KUBECONFIG` pointing at the cluster):

```bash
kubectl get nodes
kubectl get ns
kubectl get pods,svc,ingress -n ml-platform
kubectl get pods,svc,ingress -n monitoring
kubectl get pods,svc,ingress -n zulip
```

**Smoke tests:**

```bash
curl -skI -H "Host: zulip.<YOUR_FLOATING_IP>.nip.io" "https://<YOUR_FLOATING_IP>/"
curl -skI -H "Host: mlflow.<YOUR_FLOATING_IP>.nip.io" "https://<YOUR_FLOATING_IP>/"
curl -skI -H "Host: grafana.<YOUR_FLOATING_IP>.nip.io" "https://<YOUR_FLOATING_IP>/"
curl -skI -H "Host: minio.<YOUR_FLOATING_IP>.nip.io" "https://<YOUR_FLOATING_IP>/"
curl -skI -H "Host: minio-console.<YOUR_FLOATING_IP>.nip.io" "https://<YOUR_FLOATING_IP>/"
```

**Browser:** `https://zulip.<YOUR_FLOATING_IP>.nip.io/`, `https://mlflow.<YOUR_FLOATING_IP>.nip.io/`, `https://minio-console.<YOUR_FLOATING_IP>.nip.io/` (MinIO console; user from `minio-root` Secret), `https://grafana.<YOUR_FLOATING_IP>.nip.io/` (log in with `admin` and the `grafana-admin` Secret password), and optionally `https://prometheus.<YOUR_FLOATING_IP>.nip.io/` — accept cert warning if self-signed.

If **`/new/`** org creation is enabled, ensure `SETTING_OPEN_REALM_CREATION` is set consistently in values files and recycle the Zulip pod after `helm upgrade` when changing env.

---

## 14. Operational notes

- **Traefik** is the default k3s ingress controller; `ingressClassName: traefik` is set on MLflow, MinIO, Grafana, Prometheus (if exposed), and Zulip Ingresses.
- **Prometheus/Grafana:** Prometheus scrapes pods annotated with `prometheus.io/scrape: "true"` (MLflow includes these). Prometheus has no public Ingress by default; use Grafana’s Explore or add dashboards.
- **Storage:** examples target k3s **`local-path`**; change `storageClassName` / Helm values if your cluster uses another provisioner.
- **Optional path:** `infra/terraform/k8s-apps/` can manage some Kubernetes resources with Terraform; this is optional and orthogonal to the Ansible flow above.
- **`zulip/` submodule:** upstream source reference only; runtime uses published images via the docker-zulip chart.

---

## 15. Troubleshooting

| Symptom | Typical cause | Action |
|--------|----------------|--------|
| Ansible `ModuleNotFoundError: ...six.moves` | Broken / mixed Ansible install | New venv; `pip install ansible-core`; see `infra/ansible/README.md` |
| SSH “permissions too open” for `.pem` | Key on `/mnt/c/` (WSL) | Copy key to `~/.ssh`, `chmod 600` |
| Traefik **404** for Zulip | `Host` header / `SETTING_EXTERNAL_HOST` mismatch | Align Ingress host, secret `SETTING_EXTERNAL_HOST`, and browser URL (`zulip.<ip>.nip.io`) |
| Zulip **ProxyMisconfigurationError** | Traefik not trusted | Set **`LOADBALANCER_IPS`** to pod CIDR; confirm in pod env and `zulip.conf`; `helm upgrade` + pod restart |
| HTTPS timeout | Security group | Allow **443** (and **80** if needed) on the floating IP |
| Helm merge dropped env | Multiple `-f` files | Put critical env in the file that wins the merge or duplicate in `values-secret.yaml` as documented in chart comments |
| Grafana **CrashLoop** / secret missing | `grafana-admin` not created | Run deploy_platform (bootstrap task) or `kubectl create secret generic grafana-admin ...` before `apply -k observability` |
| Grafana login fails | Wrong password | `kubectl get secret grafana-admin -n monitoring -o jsonpath='{.data.admin-password}' \| base64 -d` |
| MinIO **CreateContainerConfigError** | `minio-root` missing | Run deploy_platform (bootstrap task) or create `minio-root` with keys `root-user` and `root-password` before pods schedule |

For deeper Ansible-only detail, see [`infra/ansible/README.md`](infra/ansible/README.md). For Zulip chart specifics, see [`k8s/zulip/README.md`](k8s/zulip/README.md). Observability manifests: [`k8s/platform/observability/README.md`](k8s/platform/observability/README.md).
