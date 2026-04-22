# Terraform layout (IaC)

Terraform is used for **IaC** (cloud provisioning) on Chameleon/OpenStack. Kubernetes configuration/deploy is handled via **Ansible** in `infra/ansible/`.

| Directory | Role | Typical course label |
|-----------|------|---------------------|
| [`openstack/`](./openstack/) | Networks, VM, floating IP | **IaC** — cloud infrastructure on Chameleon |

Apply order:

1. `cd openstack && terraform init && terraform apply`
2. Run Ansible to install Kubernetes + deploy apps: see `../ansible/README.md`.

Plain YAML under `k8s/` remains valid **CaC in Git**; Ansible applies these (or Helm charts) as the cluster source of truth.

