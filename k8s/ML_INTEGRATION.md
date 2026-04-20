# ML workloads integration (DevOps path)

**Shared platform:** Use the team’s single MLflow and MinIO; playbook order and cleanup checklist: [`../infra/ONE_PLATFORM_AND_CLEANUP.md`](../infra/ONE_PLATFORM_AND_CLEANUP.md).

**Tiered inference:** `kubectl apply -k k8s/inference/` deploys **staging / canary / prod** stacks (Services `tone-generator-staging`, `tone-generator-canary`, `tone-generator-prod`, and matching `classifier-pytorch-*`) plus shared ONNX/quantized backends. Zulip or bots should call **`tone-generator-prod`** for live traffic unless testing another tier. Layout: [`inference/README.md`](inference/README.md).

**Zulip bridge:** `kubectl apply -k k8s/integration/` deploys **`zulip-bridge`** (webhook → generator). Zulip setup and Ingress: [`integrations/README.md`](../integrations/README.md).

**CI (no SSH):** image promotion and rollout undo — [`.github/workflows/promote-inference.yml`](../.github/workflows/promote-inference.yml) and [`.github/workflows/rollback-inference.yml`](../.github/workflows/rollback-inference.yml) (require repo secret `KUBE_CONFIG_B64`).

Application code under `data/`, `serving/`, and `training_proj15-main/` is **not** modified here. Integration is:

1. **Build & push images** (GitHub Actions) from those Dockerfiles to **GHCR**.
2. **Point Kubernetes** manifests under `k8s/data/`, `k8s/inference/`, and `k8s/training/` at those images.
3. **Apply** manifests on the cluster and ensure **MinIO** credentials exist where Jobs/Deployments expect them.

## 1. Image names and registry

Workflow: [`.github/workflows/build-push-ml-images.yml`](../.github/workflows/build-push-ml-images.yml).

Images are pushed as:

`ghcr.io/<lowercase_github_owner>/mlops-<component>:latest` (and `:sha`).

Manifests in this repo default to **`ghcr.io/allusudharshanrao/mlops-...`**. If your GitHub user or org differs, replace that segment (case-insensitive registry owner → **lowercase**) in:

- `k8s/data/*.yaml`
- `k8s/inference/base/*.yaml`, `k8s/inference/backends/*.yaml`, and overlay patches under `k8s/inference/overlays/**/patches/`
- `k8s/integration/zulip-bridge-deployment.yaml`
- `k8s/training/*.yaml`

or change the workflow output to match your fork’s owner after the first successful CI run.

**GHCR visibility:** For k3s to pull without `imagePullSecrets`, packages must be **public** or you must add a **docker-registry** Secret in each namespace (`ml-data`, `ml-serving`, `ml-training`) and set `imagePullSecrets` on workloads (not done in the base manifests).

## 2. Run CI

On GitHub: **Actions → “Build and push ML images” → Run workflow**, or push to `main`/`master` touching `data/`, `serving/`, or `training_proj15-main/training/`.

Wait for all matrix jobs to finish (large training images may take several minutes).

## 3. Sync manifests to the VM

Re-run **`deploy_platform.yml`** from your laptop (it copies `k8s/` to `/opt/mlops_project/k8s/`), or `rsync`/git pull on the VM so updated image lines are present.

## 4. Apply workloads on the cluster

From WSL (Ansible venv), after **`inventory.ini`** and SSH work:

```bash
cd infra/ansible
source .venv/bin/activate
ansible-playbook -i inventory.ini playbooks/deploy_ml_workloads.yml
```

To run the same steps manually on the VM, mirror the tasks in `infra/ansible/playbooks/deploy_ml_workloads.yml` (Secret copy + three `kubectl apply -k` commands).

## 5. MinIO buckets

- **Data stack** manifests use bucket **`zulip-rewriter`** (see env in `k8s/data/*.yaml`). Create it in the MinIO console (or `mc`) if empty.
- **Training Jobs** use the same bucket **`zulip-rewriter`** in `k8s/training/*.yaml` so ingest + training share one object store. Use distinct prefixes inside the bucket for raw vs model artifacts (e.g. `datasets/`, `classifier/`); adjust training code if it still expects a `proj15/` prefix.

## 6. Verify

```bash
kubectl get pods -n ml-data
kubectl get pods,svc -n ml-serving
kubectl get jobs,pods -n ml-training
```

In `ml-serving`, expect **Running** pods for `classifier-pytorch-{staging,canary,prod}`, `tone-generator-{staging,canary,prod}`, and optionally `classifier-onnx`, `classifier-quantized`.

`ImagePullBackOff` → image name/registry mismatch or private package without pull secret. `CrashLoopBackOff` → app/config (logs), not Dockerfile layout.

### Troubleshooting: wrong image on the cluster

If `kubectl describe pod -n ml-serving …` shows an image such as **`tone-classifier`** or **`ghcr.io/<someone-else>/…`** (for example a fork you no longer use), the YAML on the VM is **stale**. This repo’s inference workloads use **`ghcr.io/<owner>/mlops-serving-classifier`** and **`mlops-serving-generator`**, not `tone-classifier`. Refresh **`k8s/`** on the VM (re-run **`deploy_platform.yml`** from a checkout of this repo, or rsync/git pull), then re-apply inference. On the VM you can confirm with:

```bash
grep -r "image:" /opt/mlops_project/k8s/inference --include="*.yaml"
```

You should see `mlops-serving-classifier` / `mlops-serving-generator` (and your intended GHCR owner). **`403 Forbidden`** from GHCR usually means the package is **private** and the cluster has no `imagePullSecrets`, or the image name does not exist for anonymous pulls — make the package **public** or add a pull Secret (see above).

Flat-era `*-deployment.yaml` files under `k8s/inference/` are removed on the VM when you run an up-to-date **`deploy_platform.yml`** (they are not in this repo; Ansible `copy` alone used to leave them behind). If `kubectl apply -k …/inference/` fails with **`spec.selector: field is immutable`**, see [`inference/README.md`](inference/README.md#immutable-deployment-selector-kubectl-apply-errors).

### Troubleshooting: Zulip bridge and flat vs tiered generator

The default Deployment sets **`GENERATOR_URL`** to **`http://tone-generator-prod:8010`**, which matches **tiered** inference (Service `tone-generator-prod`). If you still run a **flat** stack where the Service is named **`tone-generator`** only, point the bridge at that Service without changing files in git:

```bash
kubectl set env deployment/zulip-bridge -n ml-serving \
  GENERATOR_URL=http://tone-generator.ml-serving.svc.cluster.local:8010
```

After you move to tiered inference, set it back to prod:

```bash
kubectl set env deployment/zulip-bridge -n ml-serving \
  GENERATOR_URL=http://tone-generator-prod.ml-serving.svc.cluster.local:8010
```

## 7. Training Jobs

Jobs are **one-shot**: after a successful run they may remain `Completed`. Re-run with `kubectl delete job …` then `kubectl apply -k …/training/` if you need another run.
