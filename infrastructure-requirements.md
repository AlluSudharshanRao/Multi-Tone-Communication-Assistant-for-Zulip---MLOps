# Infrastructure requirements

This document records **GPU**, **CPU and memory requests and limits**, and **persistent storage** for workloads deployed on a single-node **k3s** cluster on **Chameleon Cloud** (`KVM@TACC`). Values are taken from version-controlled manifests where applicable; **Zulip** dependencies use Helm subchart defaults unless otherwise noted. **Empirical validation** references node `mlops-k8s-proj15` (April 2026).

**GPU:** This cluster node is **CPU-only**. The course **Zulip / tone-assistant** design may call for a **GPU** for the LLM generator in a later phase; that workload is **out of scope for this infrastructure snapshot** and is not scheduled here. No `nvidia.com/gpu` requests are configured.

---

## 1. Compute host

The cluster runs on one OpenStack instance provisioned by Terraform (`infra/terraform/openstack/`). **Schedulable capacity** is determined by the instance **flavor** or **Blazar reservation**, not by the sum of container limits (the scheduler uses **requests** for admission).

| Dimension | Specification | Basis |
|-----------|---------------|--------|
| vCPU / memory | 16 cores; 32 863 408 Ki reported capacity (~31.3 GiB RAM) | `kubectl describe node` |
| Ephemeral storage (kubelet) | 38 691 548 Ki reported (~36.9 GiB) | Same source; distinct from total VM disk |
| GPU | None | KVM@TACC educational deployment |
| Network | Floating IP; security groups allow TCP 22, 80, 443 | Operational requirement for SSH and Ingress |

**Utilization (requests vs. allocatable):** After the Zulip application pod declares **500 m CPU** and **6 Gi** memory requests (§3), total non-system **CPU requests** rise to approximately **2050 m** (~13% of 16 cores) and **memory requests** to approximately **8.5 Gi** (~27% of ~31 GiB allocatable), in addition to any prior totals from `kubectl describe node`. Re-check **Allocated resources** after `helm upgrade`. **Observed** usage under light load (`kubectl top node`): on the order of **~0.5** cores CPU and **~6 GiB** memory for the whole node, leaving headroom under declared requests.

**OpenStack alignment:** Flavor or reservation **vCPU and RAM** from Horizon or `openstack server show` / `openstack flavor show` should agree with the node capacity above. **Disk:** the root (or data) volume must accommodate **80 Gi** in bound **PersistentVolumeClaims** (see §3) plus the operating system, container images, and logs; `local-path` consumes host filesystem space.

---

## 2. Platform services (Kubernetes manifests)

Requests and limits are defined in the repository paths indicated.

| Service | Namespace | CPU request | CPU limit | Memory request | Memory limit | PVC | Source |
|---------|-----------|-------------|-----------|----------------|--------------|-----|--------|
| MLflow | `ml-platform` | 250 m | 1 | 512 Mi | 2 Gi | 20 Gi (`mlflow-data`) | `k8s/platform/mlflow/` |
| MinIO | `ml-platform` | 250 m | 1 | 512 Mi | 2 Gi | 20 Gi (`minio-data`) | `k8s/platform/minio/` |
| Prometheus | `monitoring` | 200 m | 1 | 512 Mi | 2 Gi | 10 Gi (`prometheus-data`) | `k8s/platform/observability/` |
| Grafana | `monitoring` | 100 m | 500 m | 256 Mi | 1 Gi | 5 Gi (`grafana-data`) | `k8s/platform/observability/` |

**Rationale:** Requests are set conservatively for co-location on a single-node cluster; limits bound peak consumption. MLflow and MinIO receive symmetric CPU and memory envelopes. Prometheus receives a higher ceiling for time-series retention and scraping; Grafana remains smaller (UI and metadata).

**Measurement:** Declared values were verified against the node’s pod list (`kubectl describe node`). **Idle** samples from `kubectl top` fell well below limits for these workloads, consistent with limits functioning as upper bounds rather than steady-state demand.

---

## 3. Primary application: Zulip (Helm)

Zulip is deployed with the **docker-zulip** Helm chart. **PostgreSQL** volume size and **main-container `resources`** are set in `k8s/zulip/values-chameleon.yaml`. Subchart CPU/memory values in the table match **`kubectl describe node`** for release `zulip-proj15` unless the chart is upgraded.

| Component | CPU request | CPU limit | Memory request | Memory limit | Persistent storage |
|-----------|-------------|-----------|----------------|--------------|--------------------|
| Zulip application | 500 m | 2 | 6 Gi | 8 Gi | 10 Gi (`zulip-proj15-data`, `local-path`) |
| PostgreSQL | 100 m | 150 m | 128 Mi | 192 Mi | 15 Gi (`data-zulip-proj15-postgresql-0`, `local-path`) |
| Redis | 100 m | 150 m | 128 Mi | 192 Mi | None (ephemeral) |
| RabbitMQ | 250 m | 380 m | 256 Mi | 384 Mi | None (ephemeral) |
| Memcached | 100 m | 150 m | 128 Mi | 192 Mi | None (ephemeral) |

**Right-sizing narrative:** `kubectl top pods -n zulip` showed the application pod at **~4.3 GiB** memory and **~8 m** CPU at light load, and **~196 m** CPU in an earlier busier sample. **Memory request 6 Gi** sits above steady RSS to avoid immediate pressure; **limit 8 Gi** matches a common ceiling for a small server. **CPU request 500 m** covers moderate concurrency; **limit 2** cores bounds spikes. Apply via `helm upgrade`, then confirm **Burstable** QoS with `kubectl describe pod` on `zulip-proj15-0`.

---

## 4. Persistent volumes and evidence summary

**Bound claims (80 Gi total):**

| Namespace | PersistentVolumeClaim | Capacity | StorageClass |
|-----------|----------------------|----------|--------------|
| `ml-platform` | `mlflow-data` | 20 Gi | `local-path` |
| `ml-platform` | `minio-data` | 20 Gi | `local-path` |
| `monitoring` | `prometheus-data` | 10 Gi | `local-path` |
| `monitoring` | `grafana-data` | 5 Gi | `local-path` |
| `zulip` | `data-zulip-proj15-postgresql-0` | 15 Gi | `local-path` |
| `zulip` | `zulip-proj15-data` | 10 Gi | `local-path` |

**Reproduce** the PVC listings and node resource tables using the commands in **§5.1**.

**Chameleon (OpenStack) evidence** (flavor name, vCPU, RAM, root disk) should accompany this document: Horizon screenshots or the CLI output from §5.

**Persistence mapping:** MLflow state and artifacts, MinIO object data, Prometheus TSDB, Grafana data, Zulip PostgreSQL, and Zulip application data each use **ReadWriteOnce** volumes on **`local-path`**, so state survives pod restart.

**“Persistent storage as appropriate” (rubric):** The requirement applies to **durable platform and application state**, not to every container disk. **Memcached** is an in-memory cache by design; losing its data on restart only causes a **cold cache**, not loss of chat history. **Redis** and **RabbitMQ** in this Helm deployment use **ephemeral** volumes for broker/cache data: **authoritative** Zulip content lives in **PostgreSQL** and **Zulip’s PVC**; after a broker restart, workers reconnect and the system recovers (possible brief queue loss of **non-durably-queued** work). Enabling PVCs for Redis/RabbitMQ is optional (see commented blocks in `k8s/zulip/values-chameleon.yaml`) if the team requires stricter broker durability at the cost of more disk and operational complexity. **Shared platform services** in §2 (MLflow, MinIO, observability) all use PVCs where long-lived data is expected.

**Secrets:** Credentials and keys (`terraform.tfvars`, `inventory.ini`, `values-secret.yaml`, TLS material) are excluded from version control per `SECURITY.md` and `.gitignore`.

**Bonus — Sealed Secrets:** The cluster may run the [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) controller (`kubectl apply -k k8s/addons/sealed-secrets/` or Ansible `playbooks/install_sealed_secrets_controller.yml`). That lets you store **only** `SealedSecret` objects in Git (ciphertext); the controller decrypts them in-cluster. Rationale and a concrete demo script live in [`k8s/addons/sealed-secrets/README.md`](k8s/addons/sealed-secrets/README.md).

---

## 5. Evidence commands (run on the cluster VM)

Run as user **`cc`** (or any account with a valid kubeconfig). **Do not** paste raw output that contains **passwords** or **API keys** into public repos; use screenshots or redacted excerpts for coursework.

### 5.1 Kubernetes

```bash
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

# Node — compact evidence (fits a report; avoids a full describe screenshot)
NODE=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
echo "Node: $NODE"
echo "--- Capacity ---"
kubectl get node "$NODE" -o jsonpath='cpu={.status.capacity.cpu}{"\n"}memory={.status.capacity.memory}{"\n"}ephemeral-storage={.status.capacity.ephemeral-storage}{"\n"}'
echo "--- Allocatable ---"
kubectl get node "$NODE" -o jsonpath='cpu={.status.allocatable.cpu}{"\n"}memory={.status.allocatable.memory}{"\n"}ephemeral-storage={.status.allocatable.ephemeral-storage}{"\n"}'
echo "--- Allocated resources (summary) ---"
kubectl describe node "$NODE" | sed -n '/^Allocated resources:/,/^$/p'
echo "--- Non-terminated pods (name / requests / limits only) ---"
kubectl describe node "$NODE" | sed -n '/^Non-terminated Pods:/,/^Allocated resources:/p' | head -n -1

# Full node describe (very long — use only when debugging)
# kubectl describe node

# Observed CPU/memory (requires metrics-server)
kubectl top node
kubectl top pods -A

# Scheduling and health
kubectl get pods -A -o wide
kubectl get ingress -A

# Persistent volumes (cross-check §4 table)
kubectl get pvc -n ml-platform
kubectl get pvc -n monitoring
kubectl get pvc -n zulip

# Service endpoints (backends must be non-empty for Ingress)
kubectl get endpoints -n zulip
kubectl get endpoints -n ml-platform
kubectl get endpoints -n monitoring

# Zulip stack — compact evidence for §3 table (CPU/mem requests & limits, QoS; no env secrets)
# Set REL to your Helm release name (e.g. zulip-proj15).
REL=zulip-proj15
NS=zulip
for name in "${REL}-0" "${REL}-postgresql-0" "${REL}-redis-master-0" "${REL}-rabbitmq-0"; do
  echo "========== ${name} =========="
  kubectl get pod -n "$NS" "$name" -o jsonpath='QoS: {.status.qosClass}{"\n"}{range .spec.containers[*]}{.name}{": req cpu="}{.resources.requests.cpu}{" mem="}{.resources.requests.memory}{"; lim cpu="}{.resources.limits.cpu}{" mem="}{.resources.limits.memory}{"\n"}{end}'
  echo ""
done
echo "========== memcached =========="
kubectl get pods -n "$NS" -l app.kubernetes.io/name=memcached -o jsonpath='{.items[0].metadata.name}{"\n"}{"QoS: "}{.items[0].status.qosClass}{"\n"}{range .items[0].spec.containers[*]}{.name}{": req cpu="}{.resources.requests.cpu}{" mem="}{.resources.requests.memory}{"; lim cpu="}{.resources.limits.cpu}{" mem="}{.resources.limits.memory}{"\n"}{end}'
echo ""
echo "========== PVCs (Zulip namespace) =========="
kubectl get pvc -n "$NS" -o custom-columns=NAME:.metadata.name,SIZE:.status.capacity.storage,CLASS:.spec.storageClassName

# Full describe only when debugging (long; redact environment before submitting)
# kubectl describe pod -n zulip <pod-name>

# Sealed Secrets (bonus) — controller and demo secret linkage (no secret values)
kubectl get deploy -n kube-system -l app.kubernetes.io/name=sealed-secrets -o wide 2>/dev/null || true
kubectl get sealedsecrets -A 2>/dev/null || true
kubectl get secret demo-api-key -n ml-platform -o jsonpath='owner: {.metadata.ownerReferences[0].kind}/{.metadata.ownerReferences[0].name}{"\n"}' 2>/dev/null || true
kubectl get pods -n ml-platform -l app.kubernetes.io/name=sealed-secrets-demo -o wide 2>/dev/null || true
```

**Reachability (optional):** from the VM, substitute your floating IP:

```bash
curl -skI -H "Host: zulip.<YOUR_FLOATING_IP>.nip.io" "https://<YOUR_FLOATING_IP>/"
```

### 5.2 OpenStack / Chameleon evidence (no CLI required)

**Recommended:** use the **Chameleon Horizon** web UI (no installation). Capture screenshots that show the **same** instance that runs k3s, for example:

- **Compute → Instances** — instance name, **Status**, **Flavor** (or reservation), **IP** (floating / fixed as shown).
- **Compute → Flavors** — open the flavor attached to that instance: **VCPUs**, **RAM (MB)**, **Root Disk** (if shown).
- If the VM uses **Blazar**, include the **lease / reservation** view that shows the resource bundle tied to the instance.

Align **vCPU** and **RAM** from Horizon with **Capacity** in `kubectl describe node` (§5.1).

**Optional — OpenStack CLI:** if you later install `python-openstackclient` in a venv and configure application-credential (or password) auth, you may attach CLI output instead of or in addition to Horizon:

```bash
openstack server list
openstack server show <SERVER_NAME_OR_ID>
openstack flavor show <FLAVOR_NAME_OR_ID>
```

The CLI is **not** required for coursework if Horizon evidence is clear.

---

## 6. System components (k3s)

CoreDNS and **metrics-server** expose small **requests** (100 m CPU, 70 Mi memory per component where set). **Traefik** (default Ingress) and **local-path-provisioner** did not declare requests or limits in the captured configuration. These components are bundled with k3s and are ancillary to the workload tables above.
