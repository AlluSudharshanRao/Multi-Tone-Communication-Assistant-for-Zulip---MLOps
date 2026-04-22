# OpenStack Terraform

This module provisions the two-node Chameleon environment used by the project.

## What it creates

- one control-plane instance
- one worker instance
- one floating IP attached to the control-plane
- managed security group rules for SSH, HTTP, HTTPS, and internal k3s traffic
- outputs that generate the Ansible inventory

## Required local inputs

Create `terraform.tfvars` from `terraform.tfvars.example` and fill in:

- OpenStack auth values or use `TF_VAR_*` environment variables
- `network_id`
- `key_pair`
- lease or reservation ids
- image and flavor selections if different from defaults

## Apply

```bash
terraform init
terraform plan
terraform apply
```

## Useful outputs

```bash
terraform output
terraform output -raw ansible_inventory_ini
```

The generated inventory includes:

- public `ansible_host` for the control-plane
- private worker address
- jump-host SSH path through the control-plane

## Notes

- The worker intentionally has no floating IP.
- The control-plane floating IP is the public entry point for ingress and SSH.
- Existing user-managed security groups can still be attached; Terraform also adds the project-managed security group used by the cluster.
