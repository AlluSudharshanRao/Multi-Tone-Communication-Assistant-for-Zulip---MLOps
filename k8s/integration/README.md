# Kubernetes integration (`k8s/integration/`)

| Manifest | Purpose |
|----------|---------|
| [`zulip-bridge-deployment.yaml`](zulip-bridge-deployment.yaml) | `zulip-bridge` Deployment + Service — Zulip webhook → `tone-generator-prod` |

Apply with the rest of ML workloads:

```bash
kubectl apply -k k8s/integration/
```

Optional HTTPS for Zulip (external) callbacks: copy and edit [`ingress-zulip-bridge.yaml`](ingress-zulip-bridge.yaml), replicate TLS Secret `chameleon-nip-tls` into `ml-serving` if needed, then `kubectl apply -f ingress-zulip-bridge.yaml`.

See [`integrations/README.md`](../../integrations/README.md) for Zulip UI steps and CI secrets.
