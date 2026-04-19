# Inference (tiered serving)

## Layout

| Path | Purpose |
|------|---------|
| [`base/`](base/) | PyTorch classifier + tone generator (names without tier suffix). |
| [`overlays/staging`](overlays/staging/) | `*-staging` Deployments/Services; `DUMMY_MODE=true` for cheap integration. |
| [`overlays/canary`](overlays/canary/) | `*-canary`; `DUMMY_MODE=false` for pre-prod validation. |
| [`overlays/prod`](overlays/prod/) | `*-prod`; `DUMMY_MODE=false` for live traffic. |
| [`backends/`](backends/) | Shared ONNX + quantized classifiers (not multiplied per tier). |

**In-cluster DNS (recommended for Zulip bots):**

- Production chain: `http://tone-generator-prod:8010` → calls `http://classifier-pytorch-prod:8001`.
- Staging: `tone-generator-staging:8010`, `classifier-pytorch-staging:8001`.

**Optional browser-facing URLs:** edit [`ingress/tiered-ingress.yaml`](ingress/tiered-ingress.yaml) (replace `FLOATING_IP_PLACEHOLDER`), copy TLS Secret into `ml-serving`, then `kubectl apply -k k8s/inference/ingress/`.

## Apply

```bash
kubectl apply -k k8s/inference/
```

Same command is used by [`deploy_ml_workloads.yml`](../../infra/ansible/playbooks/deploy_ml_workloads.yml).

## Design choices

- **Single namespace `ml-serving`** with `nameSuffix` per tier: simple RBAC and one place for `imagePullSecrets`; matches common single-cluster env patterns.
- **Kustomize overlays**: DRY base manifests; GitOps-friendly.
- **Canary ≠ traffic split by default**: three isolated Services support explicit routing (Zulip prod → `-prod`; CI → `-canary`). Add Traefik weights or Argo Rollouts later if you need automatic percentage-based canary.

## Legacy flat YAML

The previous single-tier `classifier-pytorch-deployment.yaml` / `generator-deployment.yaml` files were folded into `base/` + overlays. Update any external docs that referenced the old Service names (`tone-generator` without suffix) to `tone-generator-prod` for production.

### Immutable deployment selector (kubectl apply errors)

Older `classifier-onnx` / `classifier-quantized` objects may have a different `spec.selector` than this bundle. Recreate them (brief downtime for those two):

```bash
kubectl delete deployment classifier-onnx classifier-quantized -n ml-serving
kubectl apply -k /opt/mlops_project/k8s/inference/
```

### Stale files under `/opt/mlops_project/k8s/inference/*.yaml`

Ansible `copy` does not remove extra files. Flat-era `*-deployment.yaml` (often with old `ghcr.io/.../tone-classifier` images) can remain beside the kustomize tree. Re-run **`deploy_platform.yml`** from a laptop checkout of this repo (it now deletes those obsolete names on the VM), or remove them manually, then `kubectl apply -k` again.

Delete superseded **flat** workloads if they still exist (names vary):

```bash
kubectl get deploy,svc -n ml-serving
kubectl delete deployment classifier-pytorch tone-generator -n ml-serving --ignore-not-found
```
