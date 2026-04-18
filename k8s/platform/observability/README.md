# Prometheus + Grafana (shared observability)

Namespace **`monitoring`**: **Prometheus** (metrics TSDB on PVC) and **Grafana** (UI on PVC, Ingress + TLS like MLflow).

- **Grafana** Ingress: **`https://grafana.<floating-ip>.nip.io/`**. **Prometheus** also has an Ingress (`ingress-prometheus.yaml`) at **`https://prometheus.<floating-ip>.nip.io/`**; include that name in your TLS cert SAN when you generate `tls.crt`.
- **Datasource** is provisioned automatically: Grafana → Prometheus in-cluster.
- **Pod scraping**: any pod with annotations `prometheus.io/scrape: "true"`, `prometheus.io/port`, optional `prometheus.io/path` (see MLflow deployment). If a target stays **down**, the app may not expose Prometheus metrics on that path; adjust or remove annotations.
- **Grafana admin password**: Secret **`grafana-admin`** — created by `deploy_platform.yml` if missing (`openssl rand -base64 32`). Read it:

  ```bash
  kubectl get secret grafana-admin -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d && echo
  ```

Ensure **`ingress-grafana.yaml`**, **`ingress-prometheus.yaml`**, and **`deployment-grafana.yaml`** (`GF_SERVER_ROOT_URL`) use **your** floating IP and hostnames, and add those hosts to the TLS cert SAN (see [`GETTING_STARTED.md`](../../GETTING_STARTED.md)). Tracked files may use a documentation IP or your environment’s IP—keep Ingress hosts, `GF_SERVER_ROOT_URL`, and browser URLs consistent.

Apply manually: `kubectl apply -k k8s/platform/observability/` (after namespaces and `grafana-admin` Secret exist).
