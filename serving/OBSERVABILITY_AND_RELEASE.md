# Serving — observability, model-output checks, feedback, promotion/rollback

This document is **serving-owned**: it defines what we expose, how we measure it, and how we recommend promoting or rolling back **tone classifier** and **tone generator** releases. **Dashboards and cluster Prometheus are owned by DevOps** — serving does not maintain a parallel Grafana or duplicate dashboards for the same environment.

### Team observability (canonical — use these only)

| Tool        | URL |
|------------|-----|
| **Grafana**  | [https://grafana.129.114.27.192.nip.io/](https://grafana.129.114.27.192.nip.io/) |
| **Prometheus** | [https://prometheus.129.114.27.192.nip.io/](https://prometheus.129.114.27.192.nip.io/) |

Use the existing dashboards there. If classifier/generator panels are missing, ask DevOps to add panels to **this** stack (same Prometheus datasource), rather than importing a second dashboard elsewhere.

---

## 1. Operational metrics (rubric: latency, error rate, CPU/RAM, restarts)

### What serving exposes today

Both services expose Prometheus text on **`GET /metrics`**:

| Service    | Port (compose) | Counters / histograms (examples) |
|-----------|----------------|----------------------------------|
| Classifier | 8001          | `classifier_requests_total{status}`, `classifier_latency_seconds_*` |
| Generator  | 8010          | `generator_requests_total{status}`, `generator_latency_seconds_*` |

**Latency:** use histogram buckets, e.g. p95:

```promql
histogram_quantile(0.95, sum(rate(classifier_latency_seconds_bucket[5m])) by (le))
```

**Error rate (HTTP handled as errors inside app):**

```promql
sum(rate(classifier_requests_total{status="error"}[5m]))
/ clamp_min(sum(rate(classifier_requests_total[5m])), 0.001)
```

**CPU/RAM/restarts:** come from **kubelet/cAdvisor/kube-state-metrics** on the cluster (not emitted by our Python apps). Those belong in **team Grafana** next to app metrics. The PromQL snippets above are serving’s **SLO inputs** you can paste into Explore or ask DevOps to add to existing dashboards.

### Optional: local Prometheus (not canonical)

`docker compose --profile monitoring up` can still run the small Prometheus in `serving/docker-compose.yml` for **offline demos** on a laptop or VM without cluster access. It is **not** a second source of truth when the cluster stack above is available.

---

## 2. Model output monitoring (rubric: defined approach)

Serving recommends a **three-layer** approach (implementable without changing Zulip or data pipelines):

1. **Contract / schema (automatable)**  
   After deploy, run `serving/scripts/smoke_predict_generate.sh` against `/predict` and `/generate`. Fails on non-200 or missing JSON fields (`predicted_tone`, `variants.formal`, etc.).

2. **Structured inference log (operational, low-PII)**  
   Set **`SERVING_AUDIT_LOG=true`** on classifier and/or generator to emit **one JSON line per successful request** at INFO (`serving_audit: true`, `message_id`, tones, variant character lengths, latencies — **no raw message text** unless `SERVING_AUDIT_LOG_INCLUDE_TEXT=true`, which is for debug only). Collect with the cluster log stack (platform).

3. **Distribution sanity (batch or scheduled job)**  
   Periodically sample `predicted_tone` counts from logs or a metrics exporter; alert if one class goes to ~100% for extended windows (stuck model / bad deploy).

Layers 2–3 are **policy + platform** to enable; serving defines the **fields and thresholds** here so training/data can align.

---

## 3. User feedback (rubric: what we capture, where it lands)

**Capture (product — typically Zulip UI):**

- Thumbs up / down on the rewritten message, or  
- Emoji reaction on the bot message, or  
- “Report” / feedback button that POSTs JSON.

**Payload (suggested shape — align with `contracts/` when team freezes):**

- `message_id`, `rewrite_id` (optional), `helpful` (bool), `tone_requested`, `timestamp`, optional `reason` enum.

**Where it lands (serving recommendation):**

| Stage | Destination | Owner |
|-------|-------------|--------|
| Ingest | HTTP POST to a small **feedback API** or object key in **MinIO** `s3://…/feedback/…` | Data/platform |
| Analytics | Batch job reads MinIO / DB → training set refresh | Data + training |

Serving does **not** implement the feedback API in this repo slice; we document the contract so the **Zulip bridge** and **data** tracks can implement one sink.

---

## 4. Promotion / rollback triggers (rubric: clear rules)

Serving proposes **versioned** images (e.g. `tone-classifier:v20260418-abc123`). Promotion is **not** “SSH and edit YAML”; it is **git tag / image digest bump + apply** (GitOps or CI job).

| Trigger | Condition (example) | Action |
|--------|----------------------|--------|
| **Block rollout** | `smoke_predict_generate.sh` fails on staging | Do not promote |
| **Rollback candidate** | Classifier p95 > 150 ms for 15m **or** error ratio > 5% | Roll back to previous digest |
| **Rollback candidate** | Generator p95 > 800 ms SLO for 15m **or** error ratio > 5% | Roll back |
| **Model output** | Contract failures > N/hour | Roll back + page on-call |
| **Manual gate** | Release owner approves in ticket/CI | Promote digest to prod |

**Manual approval is OK**; replacing production should still be **one automated step** (pipeline input: approved digest).

Reference automation stub (serving-owned): `serving/scripts/example_promote_digest.sh` (documents env vars; does not modify cluster manifests outside this folder).

---

## 5. End-to-end path (serving slice only)

Serving sits in the middle of the ML path:

```text
[Data / training artifacts] → MODEL_PATH / PEFT_MODEL_PATH / image digest
       → build serving images → deploy → health + metrics + smoke
       → [User feedback] → future retrain (training/data)
```

**Serving responsibilities:** image build, runtime env, health, `/metrics`, smoke contracts, **SLO-oriented alert expressions** (as reference in `serving/alerts/` for DevOps to merge into cluster Prometheus if agreed), and this runbook.

**Not serving:** Terraform, cluster install, MinIO bucket creation, training jobs, Zulip Helm values, **Grafana dashboard JSON in a separate tree** (use team Grafana only).

---

## 6. Files in `serving/` that support the rubric

| Path | Purpose |
|------|---------|
| `prometheus.yml` | Optional: scrape classifier + generator when using **compose** Prometheus only |
| `alerts/serving.rules.yml` | **Reference** alert rules — ask DevOps to merge into [team Prometheus](https://prometheus.129.114.27.192.nip.io/) config; not loaded by compose by default |
| `INTEGRATION_FOR_ZULIP.md` | Curl examples, timeouts, URLs for bot / webhook owner |
| `classifier/audit_log.py`, `generator/audit_log.py` | Optional `SERVING_AUDIT_LOG` JSON lines (low-PII) |
| `scripts/smoke_predict_generate.sh` | Contract smoke after deploy (checks HTTP status) |
| `scripts/example_promote_digest.sh` | Example non-interactive promote by digest |

---

## 7. Zulip “in user flow” (schedule note)

Product integration (webhook/bot → classifier → generator → reply) is **cross-cutting**. Serving defines **HTTP contracts and SLOs** here; the Zulip-specific bridge is owned by the product/integration track. Before Apr 20, serving should keep **stable `/predict` and `/generate`** and publish **this doc + smoke script** so the bridge can be tested early.

**Concrete handoff for bridge developers:** [INTEGRATION_FOR_ZULIP.md](./INTEGRATION_FOR_ZULIP.md).
