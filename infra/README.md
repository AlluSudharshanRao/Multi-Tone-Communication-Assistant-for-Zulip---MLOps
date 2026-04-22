# Infrastructure

Infrastructure is split into Terraform for cloud resources and Ansible for cluster and workload deployment.

## Layout

- [terraform/openstack/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\terraform\openstack\README.md): OpenStack resources and generated inventory
- [ansible/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\README.md): k3s bootstrap and workload playbooks
- [ONE_PLATFORM_AND_CLEANUP.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ONE_PLATFORM_AND_CLEANUP.md): operational cleanup notes for shared platform ownership

## Recommended order

1. Terraform apply
2. Inventory generation
3. k3s install
4. Platform deploy
5. Zulip deploy
6. ML workloads deploy
