# Infrastructure (Chameleon Cloud)

We use **two tools** for **IaC/CaC**:

- **Terraform (IaC)**: provision Chameleon/OpenStack resources (VM, floating IP, etc.).
- **Ansible (CaC)**: install/configure Kubernetes and deploy cluster services/apps.

Artifacts live under:

- **`terraform/openstack/`** — Chameleon VM, floating IP (IaC).
- **`ansible/`** — Kubernetes install + app deployment (CaC).

Every resource name should include your **`projNN`** suffix. Do **not** commit passwords or kube secrets; use `terraform.tfvars` (gitignored) or environment variables.
