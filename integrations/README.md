# Product integrations

## Zulip bridge (`zulip-bridge/`)

Small FastAPI service that accepts **Zulip outgoing webhook** POSTs and forwards them to the tiered tone **generator** (`/generate`).

### Cluster wiring

1. Build and push the image (included in [`.github/workflows/build-push-ml-images.yml`](../.github/workflows/build-push-ml-images.yml) as `mlops-zulip-bridge`).
2. Apply manifests: `kubectl apply -k k8s/integration/` (also run by [`deploy_ml_workloads.yml`](../infra/ansible/playbooks/deploy_ml_workloads.yml) after inference).
3. **Generator URL:** the Deployment defaults to `GENERATOR_URL=http://tone-generator-prod:8010`. For staging tests, patch env to `http://tone-generator-staging:8010`.

### Zulip server configuration (org admin)

1. Create an **outgoing webhook** bot (or generic bot with outgoing webhook) in Zulip.
2. Set the webhook URL to a URL that reaches this service:
   - **Same cluster as Zulip:** if Zulip runs in Kubernetes, use `http://zulip-bridge.ml-serving.svc.cluster.local:8090/zulip/webhook` from a Zulip **custom profile field hook** or a small in-Zulip component that can call cluster DNS; the stock docker-zulip app container **cannot** resolve `ml-serving` unless you use **Ingress** or a **sidecar** / **external** URL.
   - **Practical path for class demos:** expose the bridge with an Ingress (see [`k8s/integration/ingress-zulip-bridge.yaml`](../k8s/integration/ingress-zulip-bridge.yaml) example), or `kubectl port-forward svc/zulip-bridge 8090:8090` during the demo and use a tunnel/ngrok if Zulip must reach it from the browser network.

3. Optional: create Secret for token check:

   ```bash
   kubectl create secret generic zulip-bridge -n ml-serving \
     --from-literal=webhook-secret='YOUR_ZULIP_OUTGOING_WEBHOOK_TOKEN'
   ```

   Zulip sends this value as `token` in the webhook JSON; the bridge compares it to `ZULIP_WEBHOOK_SECRET` when the Secret is present.

### Safeguards (defaults)

- **Rate limit:** ~60 requests/minute per client IP (in-memory; replace with Redis for multi-replica).
- **Payload size:** capped (`MAX_BODY_BYTES`).
- **Logging:** `REDACT_LOGS=true` logs lengths, not full message bodies.

### CI: promote / rollback without SSH

- [`promote-inference.yml`](../.github/workflows/promote-inference.yml) — set image tags for `classifier-pytorch-<tier>` and `tone-generator-<tier>`.
- [`rollback-inference.yml`](../.github/workflows/rollback-inference.yml) — `kubectl rollout undo` for the same Deployments.

Both require repository secret **`KUBE_CONFIG_B64`**: `base64 -w0 ~/.kube/config` (Linux) or equivalent for your kubeconfig that can update `ml-serving`.
