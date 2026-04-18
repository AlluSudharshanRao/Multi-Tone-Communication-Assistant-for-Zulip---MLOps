# MLflow (shared platform service)

PVC uses **`storageClassName: local-path`** (k3s default). On another cluster, edit `pvc.yaml` to your provisioner. See repo root [`ARCHITECTURE.md`](../../../ARCHITECTURE.md).

The Deployment sets **Prometheus** scrape annotations (`prometheus.io/*`) for the optional stack in [`k8s/platform/observability/`](../observability/README.md); if metrics are unavailable at `/metrics`, targets may show as down until you change the path or disable scraping.

Apply after namespaces exist:

```bash
kubectl apply -f ../base/namespaces.yaml
kubectl apply -k .
```

Expose for course staff:

- **Current (Chameleon):** **Ingress** `ingress.yaml` — **`https://mlflow.<floating-ip>.nip.io`** via k3s **Traefik** and TLS secret **`chameleon-nip-tls`** (same cert as Zulip; create Secret on cluster, not in Git).
- **Local debug:** `kubectl -n ml-platform port-forward svc/mlflow 5000:5000`

For production-style tracking, point `default-artifact-root` at object storage (S3-compatible on Chameleon) instead of the PVC; this minimal stack satisfies “persistent across pod restarts” for the initial milestone.
