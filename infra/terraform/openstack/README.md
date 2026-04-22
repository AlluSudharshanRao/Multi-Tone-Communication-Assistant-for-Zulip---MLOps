# OpenStack / Chameleon (IaC)

Provisions a single VM and associates a **floating IP**—typical pattern for a one-node **k3s** or jump host. Names include `project_id_suffix`.

## Before apply

1. Confirm your **Blazar lease** is **ACTIVE** in Horizon (reservation id and `openstack_tenant_id` are pre-filled in `terraform.tfvars.example` for project 15).
2. In Horizon or CLI, note **`network_id`**, **`key_pair`**, and at least one **security group** (SSH from your IP; **80** and **443** for Ingress).
3. Copy `terraform.tfvars.example` → `terraform.tfvars` (gitignored). Fill **`key_pair`**, **`network_id`**, and **application credential** id/secret (or use `TF_VAR_*` / `OS_*` env vars — see `providers.tf`).
4. Set `install_k3s_cloud_init = true` if you want k3s installed on first boot (simple single-node cluster). Otherwise use Ansible `k3s_install.yml` after SSH works.

## Floating IP error: “External network … is not reachable from subnet …”

Your private subnet needs a **router** with **external gateway** to the pool you use for floating IPs (`floating_ip_pool`, usually `public`). This module can create **`create_public_router = true`** (default) and attach the first subnet on `network_id`.

If you already fixed routing in Horizon, set **`create_public_router = false`** to avoid duplicate routers.

## Authentication (Chameleon + college SSO)

Use an **application credential** from Horizon (**Identity → Application Credentials**). Do not commit `application_credential_secret`.

Either put values in `terraform.tfvars` (local only) or use:

```powershell
$env:TF_VAR_application_credential_id     = "..."
$env:TF_VAR_application_credential_secret = "..."
```

Ensure **`openstack_auth_url`** ends with **`/v3`** (e.g. `https://kvm.tacc.chameleoncloud.org:5000/v3`).

### Using a `clouds.yaml` (OpenStack CLI / optional)

1. Save your file as **`%USERPROFILE%\.config\openstack\clouds.yaml`** (Windows) or **`~/.config/openstack/clouds.yaml`** (Linux/macOS/WSL). **Do not** commit it to this repo; `clouds.yaml` is gitignored if placed under the project tree by mistake.
2. Under `auth`, use **`auth_url: https://kvm.tacc.chameleoncloud.org:5000/v3`** (trailing **`/v3`** matches Terraform and avoids subtle auth failures).
3. For **`python-openstackclient`**: `set OS_CLOUD=openstack` (Windows) or `export OS_CLOUD=openstack`, then `openstack server list`, etc.

**Terraform** does not read `clouds.yaml` by itself. Either keep **`application_credential_id`** / **`application_credential_secret`** in local **`terraform.tfvars`** (gitignored), or set the same values via **`TF_VAR_application_credential_*`** / **`OS_*`** as in repo root **`GETTING_STARTED.md`**.

**If a secret was pasted in chat, email, or a ticket:** revoke that application credential in Horizon (**Identity → Application Credentials → Delete**), create a new one, and update only your **local** `clouds.yaml` / `terraform.tfvars` — never commit the secret.

```bash
terraform init
terraform plan
terraform apply
```

## After apply

- SSH: `ssh -i ~/.ssh/your_key cc@<floating_ip>` (user may be `ubuntu` depending on image—check site docs).
- If you used cloud-init k3s: copy `/etc/rancher/k3s/k3s.yaml` and replace `127.0.0.1` with the floating IP for API access from your laptop (or use SSH `-L` port-forward).

Then install Kubernetes and deploy services with **`../../ansible/`** (see repo `infra/ansible/README.md`).
