# Ansible

These playbooks install k3s and deploy the cluster workloads from the control-plane node.

## Playbooks

- `playbooks/k3s_install.yml`: installs k3s server on `control_plane` and joins `workers`
- `playbooks/deploy_platform.yml`: deploys MLflow, MinIO, Prometheus, Grafana, Alertmanager
- `playbooks/deploy_zulip.yml`: installs or upgrades Zulip through Helm
- `playbooks/deploy_ml_workloads.yml`: deploys data, training, inference, and bridge workloads

## Inventory

Use the generated Terraform inventory shape:

```ini
[control_plane]
control-plane ansible_host=<floating_ip> private_ip=<control_plane_private_ip>

[workers]
worker-1 ansible_host=<worker_private_ip> private_ip=<worker_private_ip> ansible_ssh_common_args='-o ProxyJump=cc@<floating_ip>'

[chameleon:children]
control_plane
workers

[chameleon:vars]
ansible_user=cc
ansible_ssh_private_key_file=~/.ssh/YOUR_KEY
ansible_python_interpreter=/usr/bin/python3.12
```

## Bring-up order

```bash
source .venv/bin/activate
ansible-playbook -i inventory.ini playbooks/k3s_install.yml
ansible-playbook -i inventory.ini playbooks/deploy_platform.yml
ansible-playbook -i inventory.ini playbooks/deploy_zulip.yml \
  -e zulip_chart_dir=/home/cc/docker-zulip/helm/zulip \
  -e project_id_suffix=proj15 \
  -e zulip_values_file=/opt/mlops_project/k8s/zulip/values-chameleon.yaml \
  -e zulip_secret_values_file=/home/cc/values-secret.yaml
ansible-playbook -i inventory.ini playbooks/deploy_ml_workloads.yml
```

## Notes

- The playbooks only run cluster-admin actions on `control_plane`.
- `deploy_platform.yml` and `deploy_ml_workloads.yml` rewrite floating-IP-based hostnames in the synced VM manifests.
- `deploy_ml_workloads.yml` now waits for:
  - data jobs
  - inference deployment rollouts
  - Zulip bridge rollout
  - training jobs
  - `register-and-alias-latest`

## Inputs still required outside git

- `inventory.ini`
- `terraform.tfvars`
- TLS secret material
- Zulip secret values file
- SMTP and other credential values
