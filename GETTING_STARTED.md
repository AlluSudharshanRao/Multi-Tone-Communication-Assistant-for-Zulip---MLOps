# Getting Started

This guide is the clean bring-up order for the current repository state.

## Prerequisites

- Chameleon leases for one control-plane node and one worker node
- OpenStack application credentials
- A floating IP
- Terraform installed on Windows or Linux
- WSL or Linux shell with Ansible in `infra/ansible/.venv`
- SSH key available to both Terraform and Ansible

## Local files you need

- `infra/terraform/openstack/terraform.tfvars`
- `infra/ansible/inventory.ini`
- TLS certificate and key for `*.nip.io`
- Zulip secret values file on the control-plane VM, usually `/home/cc/values-secret.yaml`

Do not commit any of those files.

## Bring-up order

### 1. Provision infrastructure

From [infra/terraform/openstack](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\terraform\openstack):

```bash
terraform init
terraform plan
terraform apply
terraform output -raw ansible_inventory_ini
```

Copy the generated inventory into [infra/ansible/inventory.ini](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\inventory.ini) and add your SSH key path if needed.

### 2. Install k3s

From [infra/ansible](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible):

```bash
source .venv/bin/activate
ansible-playbook -i inventory.ini playbooks/k3s_install.yml
```

This installs k3s server on the control-plane and joins the worker through the control-plane jump host.

### 3. Prepare block storage for persistent state

If you attached a Chameleon block volume for persistent service data, prepare it on the
control-plane before deploying workloads:

```bash
ansible-playbook -i inventory.ini playbooks/prepare_block_storage.yml
```

This playbook:

- persists the `/mnt/block` mount in `/etc/fstab`
- creates service directories under `/mnt/block`
- labels the control-plane node as the block-backed storage node
- updates k3s `local-path` so new claims scheduled on the control-plane use the block volume

Important:

- the playbook expects the attached partition to be `/dev/vdb1`
- existing PVCs are not migrated automatically; only newly provisioned or recreated claims will move

If the platform services already exist and you want to move their current PVC contents to
the block-backed path, run the migration after the next platform apply:

```bash
ansible-playbook -i inventory.ini playbooks/migrate_platform_pvcs_to_block.yml
```

This migrates:

- MinIO
- MLflow
- Prometheus
- Grafana

The migration is serialized and service-by-service: scale down, stream backup, recreate
the PVC, restore, then scale back up.

### 4. Deploy the shared platform

```bash
ansible-playbook -i inventory.ini playbooks/deploy_platform.yml
```

This deploys:

- namespaces
- MLflow
- MinIO
- Prometheus
- Grafana
- Alertmanager

The playbook also rewrites `*.nip.io` hostnames in the synced VM manifests to the current floating IP.

### 5. Create TLS secrets

Create `chameleon-nip-tls` in:

- `zulip`
- `ml-platform`
- `monitoring`
- `ml-serving`

Use the same certificate SAN set for all public `*.nip.io` hosts you expose.

### 6. Prepare Zulip secret values

On the control-plane VM:

```bash
git clone --depth 1 https://github.com/zulip/docker-zulip.git ~/docker-zulip
cp /opt/mlops_project/k8s/zulip/values-secret.yaml.example ~/values-secret.yaml
```

Fill in:

- `SETTING_EXTERNAL_HOST`
- `SETTING_ZULIP_ADMINISTRATOR`
- SMTP settings
- secret keys
- passwords

### 7. Deploy Zulip

```bash
ansible-playbook -i inventory.ini playbooks/deploy_zulip.yml \
  -e zulip_chart_dir=/home/cc/docker-zulip/helm/zulip \
  -e project_id_suffix=proj15 \
  -e zulip_values_file=/opt/mlops_project/k8s/zulip/values-chameleon.yaml \
  -e zulip_secret_values_file=/home/cc/values-secret.yaml
```

### 8. Deploy ML workloads

```bash
ansible-playbook -i inventory.ini playbooks/deploy_ml_workloads.yml
```

The playbook now:

- syncs the current `k8s/` tree to the VM
- rewrites public hostnames to the active floating IP
- replicates `minio-root` into workload namespaces
- runs the data jobs and waits for them
- applies inference and bridge manifests and waits for rollouts
- runs training jobs and waits for them
- runs the registry job and waits for completion

## Verification checklist

On the control-plane VM:

```bash
kubectl get nodes
kubectl get pods,svc,ingress -n ml-platform
kubectl get pods,svc,ingress -n monitoring
kubectl get pods,svc,ingress -n zulip
kubectl get pods,svc -n ml-data
kubectl get pods,svc -n ml-serving
kubectl get jobs,pods -n ml-training
```

Expected high-level state:

- both nodes `Ready`
- platform pods `Running`
- Zulip pods `Running`
- data jobs `Complete`
- training jobs `Complete`
- `register-and-alias-latest` `Complete`
- classifier and generator deployments ready in `staging`, `canary`, and `prod`

## Browser checks

Verify:

- `https://zulip.<floating-ip>.nip.io`
- `https://mlflow.<floating-ip>.nip.io`
- `https://minio-console.<floating-ip>.nip.io`
- `https://grafana.<floating-ip>.nip.io`

Then log into Zulip and test `Tone suggestions`.

## If something fails

- Platform issues: see [infra/ansible/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\README.md)
- Kubernetes manifest ownership and layout: see [k8s/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\README.md)
- Serving and integration checks: see [serving/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\serving\README.md)
