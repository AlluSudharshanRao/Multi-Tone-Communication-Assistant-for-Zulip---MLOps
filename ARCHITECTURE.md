# Architecture (high level)

Reproducible **MLOps course** stack on **Chameleon Cloud** (`KVM@TACC`): OpenStack VM, single-node **k3s**, shared **MLflow**, **MinIO**, **Prometheus/Grafana**, and **Zulip** behind **Kubernetes Ingress**.

```mermaid
flowchart TB
  subgraph cloud [Chameleon OpenStack]
    TF[Terraform IaC]
    VM[VM + floating IP + networking]
    TF --> VM
  end
  subgraph vm [VM]
    AN[Ansible CaC]
    K[k3s]
    AN --> K
    T[Traefik Ingress]
    K --> T
  end
  subgraph workloads [Namespaces]
    M[MLflow + MinIO ml-platform]
    O[Prometheus + Grafana monitoring]
    Z[Zulip + data stack]
    T --> M
    T --> O
    T --> Z
  end
```

| Layer | Responsibility | Location in repo |
|-------|----------------|------------------|
| Cloud | VM, network, FIP | `infra/terraform/openstack/` |
| Node + cluster | k3s install, kubeconfig for `cc` | `infra/ansible/playbooks/k3s_install.yml` |
| Platform | Namespaces, MLflow, MinIO, Prometheus/Grafana | `infra/ansible/playbooks/deploy_platform.yml`, `k8s/` |
| Application | Zulip Helm (docker-zulip chart) | `infra/ansible/playbooks/deploy_zulip.yml`, `k8s/zulip/*.yaml` |

**Public HTTPS** terminates at **Traefik** (k3s default). TLS Secret `chameleon-nip-tls` is created on the cluster (not committed). **Zulip**, **MLflow**, **MinIO** (API + console), **Grafana**, and optionally **Prometheus** use separate **nip.io** subdomains on the same floating IP.

**Reference only:** `zulip/` is a **git submodule** pointing at upstream [zulip/zulip](https://github.com/zulip/zulip) (source study). Runtime images come from the **docker-zulip** Helm chart, not a local build from that submodule.
