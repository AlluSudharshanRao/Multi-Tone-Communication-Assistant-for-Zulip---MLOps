# Prometheus, Grafana, and Alertmanager

Namespace `monitoring` hosts the shared observability stack:

- **Grafana** Ingress: **`https://grafana.<floating-ip>.nip.io/`**. **Prometheus** also has an Ingress (`ingress-prometheus.yaml`) at **`https://prometheus.<floating-ip>.nip.io/`**; include that name in your TLS cert SAN when you generate `tls.crt`.
- **Datasource** is provisioned automatically: Grafana → Prometheus in-cluster (Prometheus datasource UID **`prometheus`**).
- **Dashboards:** folder **MLOps** includes **ML serving — tone inference**, **ML retraining and feedback overview**, **Infrastructure Health**, **Data Monitoring and Quality**, and **Platform Operations**. Re-apply `kubectl apply -k k8s/platform/observability/` after pulling manifest changes, then restart Grafana if it does not pick up new files immediately.
- **Pod scraping**: any pod with annotations `prometheus.io/scrape: "true"`, `prometheus.io/port`, optional `prometheus.io/path` (see `ml-serving` inference Deployments). If a target stays **down**, the app may not expose Prometheus metrics on that path; adjust or remove annotations.
- **Grafana admin password**: Secret **`grafana-admin`** — created by `deploy_platform.yml` if missing (`openssl rand -base64 32`). Read it:
- `prometheus` stores scraped metrics on the `prometheus-data` PVC
- `grafana` serves dashboards from the `grafana-data` PVC
- `alertmanager` receives alerts from Prometheus
- `kube-state-metrics` exports Kubernetes object state
- `node-exporter` runs on every node and exports host metrics

## Access

- Grafana: `https://grafana.<floating-ip>.nip.io/`
- Prometheus: `https://prometheus.<floating-ip>.nip.io/`

The Grafana admin password lives in the `grafana-admin` Secret:

```bash
kubectl get secret grafana-admin -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d && echo
```

## What Is Monitored

Prometheus scrapes:

- annotated inference and integration pods in `ml-serving`
- `kube-state-metrics` for deployment, pod, and node state
- `node-exporter` for host CPU and memory usage

This supports both platform and serving views from a single Prometheus instance.

## Dashboards

Grafana provisions the `MLOps` folder automatically. The current dashboards are:

- `ML Serving Health`
  - request rate
  - p95 latency
  - error rate
  - feedback counters for the tone assistant services
- `ML retraining and feedback overview`
  - classifier prediction volume by tone
  - classifier confidence trends
  - feedback events by outcome, category, deadline bucket, and requested tone
- `Infrastructure Health`
  - node CPU and memory pressure
  - deployment replica availability
  - pod restart behavior
  - Kubernetes node readiness
- `Data Monitoring and Quality`
  - bridge feedback counters
  - feature-log activity
  - data and training job health
  - data and training pod restarts
- `Data Quality Health`
  - raw and batch row counts
  - null, duplicate, and invalid-label signals
  - online log volume and error rate
  - feedback approval and preferred-text rates
  - drift PSI and batch merge volume
- `Platform Operations`
  - Traefik / ingress health
  - block-volume and root-disk free space
  - backup job success and failure
  - namespace CPU and memory request totals
  - running versus pending pods by namespace

If dashboards are changed, re-apply:

```bash
kubectl apply -k k8s/platform/observability/
```

## Data Quality Exporter Runtime

The `data-quality-exporter` Deployment is now bootstrapped directly from repo-managed runtime files instead of relying on a prebuilt node-local image. The observability kustomization generates a `data-quality-runtime` ConfigMap from [monitoring/data_quality](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\monitoring\data_quality), mounts that runtime into the pod, and starts it on `python:3.11-slim`.

Operational notes:

- `minio-root` must exist in the `monitoring` namespace because the exporter reads batch, feedback, and drift artifacts directly from MinIO.
- the Deployment is pinned to the control-plane node and tolerates temporary `disk-pressure` so monitoring stays available even if the worker is under storage pressure.
- if you change exporter source code, re-apply `kubectl apply -k k8s/platform/observability/` to refresh the runtime ConfigMap and restart the Deployment.

## Alerts

Prometheus evaluates alert rules from `configmap-prometheus.yaml` and forwards them to Alertmanager.

Current platform alerts:

- `Watchdog`
- `PlatformNodeNotReady`
- `PlatformDeploymentUnavailableReplicas`
- `PlatformPodRestartsHigh`
- `PlatformNodeCpuHigh`
- `PlatformNodeMemoryHigh`

Current serving alerts:

- `ServingClassifierHighErrorRatio`
- `ServingClassifierLatencyP95High`
- `ServingGeneratorHighErrorRatio`
- `ServingGeneratorLatencyP95High`
- `ServingGeneratorFallbackRatioHigh`
- `ServingGeneratorFeedbackApprovalLow`
- `ServingGeneratorQueueWaitP95High`

Current data quality alerts:

- `DataQualityExporterDown`
- `DataQualityApprovalRateLow`
- `DataQualityOnlineErrorRateHigh`
- `DataQualityDriftHigh`

Alertmanager supports SMTP email delivery through deployment-time variable injection. Set these before running `deploy_platform.yml`:

- `ALERT_EMAIL_TO`
- `ALERT_EMAIL_FROM`
- `ALERT_EMAIL_SMARTHOST`
- `ALERT_EMAIL_AUTH_USERNAME`
- `ALERT_EMAIL_AUTH_PASSWORD`

The repo keeps placeholders only; `deploy_platform.yml` patches the copied VM manifest before `kubectl apply`, so credentials do not need to be stored in Git.

## Autoscaling

HorizontalPodAutoscalers are configured for:

- `classifier-pytorch-staging`
- `classifier-pytorch-canary`
- `classifier-pytorch-prod`
- `tone-generator-staging`
- `tone-generator-canary`
- `tone-generator-prod`
- `zulip-bridge`
- `kube-state-metrics`
- `alertmanager`

The classifier HPAs target `70%` CPU utilization, the generator HPAs target `65%`, and the
bridge / observability HPAs use CPU-plus-memory targets to absorb bursty traffic and cluster-state churn.

Deliberately fixed-size services:

- `mlflow` remains singleton because it uses SQLite on a PVC
- `minio` remains singleton because this deployment is a single-node PVC-backed object store
- `prometheus` remains singleton because it uses one PVC-backed TSDB
- `grafana` remains singleton because it is backed by a single PVC and is not a throughput bottleneck in this class project

Validated live on the current cluster:

- `classifier-pytorch-staging` scaled from `1` replica to `4` replicas under sustained request load
- after the load completed and the downscale stabilization window elapsed, it returned from `4` replicas to `1`

## Rollout Note

Prometheus uses a single PVC-backed TSDB, so its Deployment uses a `Recreate` strategy. This prevents overlapping pods from competing for the same storage lock during rollouts.

## Evidence

See [EVIDENCE.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\platform\observability\EVIDENCE.md) for the live validation checklist and the observed monitoring, alerting, and autoscaling results captured from the current cluster.
