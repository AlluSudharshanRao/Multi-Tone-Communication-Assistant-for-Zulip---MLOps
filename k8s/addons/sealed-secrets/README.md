# Sealed Secrets (bonus: Git-safe Kubernetes secrets)

[Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) encrypts a `Secret` **before** it leaves your workstation. You commit the resulting `SealedSecret` manifest to Git; only the **controller running in your cluster** can decrypt it into a normal `Secret`. Plaintext credentials never belong in the repo.

## Why this improves operability (short justification)

**Scenario:** The team uses Git for all environment manifests. A junior engineer needs to add an API key for a batch job. Without Sealed Secrets, the usual anti-pattern is a `secret.yaml` in a private branch, Slack DM, or “just run `kubectl create secret` on the VM” — none of which are reviewable or reproducible. With Sealed Secrets, they open a PR that only adds a **SealedSecret** (ciphertext). Reviewers see *what* resource is created (name, namespace, keys) without seeing the value; `kubectl apply -f` from CI or Ansible matches production. **Concrete win:** you can **delete the plaintext file after sealing** and still **rebuild the cluster from Git**; losing a laptop does not leak the key from the repository history.

## One concrete operational win (demo video)

1. Show that a **plaintext** `Secret` manifest must **not** be committed (or show it redacted in Git).
2. Run `generate-sealed-demo.sh` (or the one-liner below) to produce `sealedsecret-demo.yaml`.
3. `kubectl apply -f sealedsecret-demo.yaml` then `kubectl apply -k demo/` (or `kubectl apply -k k8s/addons/sealed-secrets/demo/`).
4. `kubectl logs -n ml-platform deploy/sealed-secrets-demo` — line shows **API_KEY present** (do not print the value on screen).
5. **Contrast:** emphasize the committed file is a SealedSecret; stealing the Git repo does not reveal the secret without the cluster’s sealing keys.

## Install the controller (cluster)

Pinned in `kustomization.yaml` (currently v0.36.1).

```bash
kubectl apply -k k8s/addons/sealed-secrets/
kubectl get deploy,pods -n kube-system -l app.kubernetes.io/name=sealed-secrets
```

Or with Ansible (after `k3s_install` and repo synced to the VM):

```bash
ansible-playbook -i inventory.ini playbooks/install_sealed_secrets_controller.yml
```

## Install `kubeseal` (your laptop or the VM)

- **Linux (amd64)** — see [upstream release assets](https://github.com/bitnami-labs/sealed-secrets/releases) for the matching version (use **v0.36.1** to match this repo’s controller).
- **macOS:** `brew install kubeseal`

`kubeseal` must be able to reach the cluster API (same as `kubectl`).

## Generate the demo SealedSecret

From repo root, with `kubectl` pointed at the cluster:

```bash
# Writes to $HOME/sealedsecret-demo.yaml by default (works when /opt/mlops_project is not writable).
bash k8s/addons/sealed-secrets/demo/generate-sealed-demo.sh
# optional: DEMO_API_KEY='your-non-production-value' bash ...
# optional: SEALED_SECRET_DEMO_OUT=/tmp/sealedsecret-demo.yaml bash ...
```

Equivalent one-liner (output in your home directory):

```bash
kubectl create secret generic demo-api-key --dry-run=client -n ml-platform \
  --from-literal=api-key='demo-value-for-video' -o yaml | kubeseal -o yaml > ~/sealedsecret-demo.yaml
```

**Note:** `sealedsecret-demo.yaml` is **cluster-specific**. If you regenerate on another cluster, commit the file that matches **your** demo cluster (or keep it out of Git and apply from CI artifacts). Copy from `$HOME` into the repo if you want it under `k8s/addons/sealed-secrets/demo/`.

## Apply demo workload

```bash
kubectl apply -f ~/sealedsecret-demo.yaml
# or: kubectl apply -f k8s/addons/sealed-secrets/demo/sealedsecret-demo.yaml  (if you copied the file there)
kubectl apply -k k8s/addons/sealed-secrets/demo/
kubectl rollout status -n ml-platform deploy/sealed-secrets-demo
kubectl logs -n ml-platform deploy/sealed-secrets-demo --tail=5
```

## Evidence (coursework)

```bash
kubectl get sealedsecrets -A
kubectl get secret demo-api-key -n ml-platform -o jsonpath='{.metadata.ownerReferences[0].kind}{"\n"}'
```

You should see a `SealedSecret` owned/decoded relationship (controller manages the `Secret`).
