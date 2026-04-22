# Zulip on Kubernetes (base open-source service)

**Upstream product (source code):** [github.com/zulip/zulip](https://github.com/zulip/zulip) — the Zulip server and web app (Python/Django, etc.). That is the main open-source repo for the platform your ML feature complements.

**How we run it in Kubernetes:** images and the official **Helm chart** come from [docker-zulip](https://github.com/zulip/docker-zulip) (`helm/zulip/`). The chart packages the same server for containerized deployment; day-to-day app behavior and APIs are defined in the `zulip/zulip` tree.

## Prereqs

- Cluster storage class for PostgreSQL / Redis / RabbitMQ PVCs (e.g. k3s `local-path`).
- **Ingress:** k3s default **Traefik**; **`values-chameleon.yaml`** enables Ingress + TLS secret name **`chameleon-nip-tls`** (create the Secret on the cluster — see repo root [`GETTING_STARTED.md`](../../GETTING_STARTED.md), *Step 6 — TLS Secret for Ingress*).
- Hostname aligned with **`SETTING_EXTERNAL_HOST`**: **`zulip.<floating-ip>.nip.io`** (subdomain form so MLflow can use **`mlflow.<same-ip>.nip.io`**).
- Env **`LOADBALANCER_IPS`** (pod CIDR, e.g. `10.42.0.0/16`) so Zulip’s nginx trusts Traefik; optional **`SETTING_OPEN_REALM_CREATION`** for stable **`/new/`**.
- TLS secret and `values-secret.yaml` **not** committed to Git.

## Install (example)

Clone or vendor the chart, then install with team overrides:

```bash
# Example only — adjust paths to where you vendor the chart
helm dependency update ./zulip-chart
helm install zulip-proj15 ./zulip-chart \
  --namespace zulip \
  --create-namespace \
  -f values-chameleon.yaml \
  -f values-secret.yaml
```

`values-secret.yaml` should contain `zulipSecret`, database passwords, etc., and stay **local** or in a secret manager.



See `values-chameleon.yaml` and `values-secret.yaml.example` for proxy, TLS, realm-creation flags, and **main Zulip container `resources`** (sized from `kubectl top`; re-tune after `helm upgrade`).

## Custom Zulip server image (forked `zulip/zulip`)

For **compose-area tone UI** or other server changes, build from your fork of [zulip/zulip](https://github.com/zulip/zulip) and publish an image compatible with [docker-zulip](https://github.com/zulip/docker-zulip) (same entrypoints as upstream `zulip-server`).

1. **CI/CD:** build and push e.g. `ghcr.io/<org>/zulip-server:<tag>` (pin tags; avoid only `:latest` in production).
2. **Helm:** set chart-root **`image.repository`** and **`image.tag`** (see commented example at the bottom of [`values-chameleon.yaml`](values-chameleon.yaml)).
3. **Upgrade:** always pass **both** values files so immutable fields stay aligned, e.g.  
   `helm upgrade --install zulip-proj15 <chart> -n zulip --kubeconfig ~/.kube/config -f values-chameleon.yaml -f values-secret.yaml`  
   Omitting `values-chameleon.yaml` can reset `zulip.persistence.storageClass` / Ingress and **fail** the upgrade on existing PVCs.

4. **Compose tone UI:** after you build a forked server image, uncomment **`TONE_MLOPS_BRIDGE_URL`** inside `zulip.environment.ZULIP_CUSTOM_SETTINGS` in `values-chameleon.yaml` (or your secret overlay) so Django can reach **`zulip-bridge`** in `ml-serving`. Source and patches: [`integrations/zulip-server-mlops/README.md`](../../integrations/zulip-server-mlops/README.md).
