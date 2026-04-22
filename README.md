# Multi-Tone Communication Assistant for Zulip

This repository contains the infrastructure, Kubernetes manifests, training code, serving code, and Zulip integration needed to run the project end to end on Chameleon Cloud.

## What is in this repo

- OpenStack + networking provisioning with Terraform
- Two-node k3s cluster bootstrap with Ansible
- Shared platform services: MLflow, MinIO, Prometheus, Grafana
- Zulip deployment through the docker-zulip Helm chart
- Data, training, model registration, and serving workloads
- Zulip bridge and custom Zulip UI integration for tone suggestions

## Current architecture

- `control-plane` node: public floating IP, cluster admin operations, core platform access
- `worker` node: additional cluster capacity for workloads
- Namespaces:
  - `ml-platform`: MLflow, MinIO
  - `monitoring`: Prometheus, Grafana, Alertmanager
  - `zulip`: Zulip application and its backing services
  - `ml-data`: ingest, batch, and online data services
  - `ml-training`: training jobs and registry jobs
  - `ml-serving`: classifier, generator, bridge, ingress

## Documentation map

- [GETTING_STARTED.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\GETTING_STARTED.md): full bring-up order
- [ARCHITECTURE.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\ARCHITECTURE.md): system layout and runtime flow
- [infra/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\README.md): infrastructure entry point
- [k8s/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\README.md): Kubernetes manifest map
- [k8s/training/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\training\README.md): training, retraining, feedback, and registry verification
- [serving/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\serving\README.md): serving stack and smoke tests
- [training_proj15-main/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\training_proj15-main\README.md): training code and MLflow flow
- [SECURITY.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\SECURITY.md): secrets and public-repo hygiene

## Bring-up summary

1. Provision OpenStack resources from `infra/terraform/openstack/`.
2. Generate inventory and bootstrap k3s from `infra/ansible/`.
3. Deploy platform services.
4. Create TLS secrets and Zulip secret values.
5. Deploy Zulip.
6. Deploy ML workloads.
7. Verify data, training, serving, and Zulip tone suggestions.

## Important operational notes

- Secrets are not committed. You still need local `terraform.tfvars`, `inventory.ini`, TLS material, and Zulip secret values.
- The ML workloads playbook now waits for data jobs, training jobs, serving deployments, bridge rollout, and the registry job.
- The tone generator serving path includes a mounted copy of the current generator logic so cluster behavior matches the repo source.
- Self-signed `*.nip.io` certificates are acceptable for demos, but browsers will warn until you trust or replace them.
