# OpenStack / Chameleon (IaC)

Provisions a single VM and associates a **floating IP**—typical pattern for a one-node **k3s** or jump host. Names include `project_id_suffix`.

## Before apply

1. In Horizon or CLI, note **`image_name`**, **`network_id`**, **`key_pair`**, and at least one **security group** (SSH from your IP; later NodePort/443 as needed).
2. Copy `terraform.tfvars.example` → `terraform.tfvars` (gitignored at parent level; add `*.tfvars` here to `.gitignore` if you store locally).
3. Set `install_k3s_cloud_init = true` if you want k3s installed on first boot (simple single-node cluster).

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

```bash
terraform init
terraform plan
terraform apply
```

## After apply

- SSH: `ssh -i ~/.ssh/your_key cc@<floating_ip>` (user may be `ubuntu` depending on image—check site docs).
- If you used cloud-init k3s: copy `/etc/rancher/k3s/k3s.yaml` and replace `127.0.0.1` with the floating IP for API access from your laptop (or use SSH `-L` port-forward).

Then install Kubernetes and deploy services with **`../../ansible/`** (see repo `infra/ansible/README.md`).
