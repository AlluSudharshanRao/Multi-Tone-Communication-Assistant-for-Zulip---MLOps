# Demo Script — Serving Track
**Role:** Serving — Rithwik Amajala | **Time: ~6 min**

---

## Before the demo (5 min before)

```bash
# Open 2 browser tabs:
# 1. https://grafana.129.114.27.192.nip.io/  (admin / grafana-password)
# 2. https://prometheus.129.114.27.192.nip.io/

# SSH into VM
ssh -i ~/.ssh/id_rsa_chameleon cc@129.114.25.7
cd Multi-Tone-Communication-Assistant-for-Zulip---MLOps/serving

# Confirm containers are healthy
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Quick sanity check
bash scripts/smoke_predict_generate.sh http://127.0.0.1:8001 http://127.0.0.1:8010
# Expected: OK: smoke checks passed
```

---

## Part 1 — What we built (1 min)

> "My role is serving. I own two microservices — a tone **classifier** and a tone **generator** — that sit behind the Zulip bot and turn any message into three rewrites: formal, friendly, and neutral."

```
Zulip message → /zulip/webhook (bridge)
    → generator /generate
        → classifier /predict  (DistilBERT, 3-class)
    ← 3 tone variants back to Zulip
```

---

## Part 2 — Live API (2 min)

**Run on VM terminal:**

### Classifier
```bash
curl -sS -X POST http://127.0.0.1:8001/predict \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","text":"yo can u just fix the bug already its been 3 days","message_type":"stream"}' \
  | python3 -m json.tool
```
Point out: `predicted_tone`, `probabilities`, `latency_ms` — **p95 < 83ms** ✅

### Generator (full pipeline)
```bash
curl -sS -X POST http://127.0.0.1:8010/generate \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","text":"yo can u just fix the bug already its been 3 days","message_type":"stream"}' \
  | python3 -m json.tool
```
Point out: `variants.formal/friendly/neutral`, `offensive_content_flagged`, `total_latency_ms`

### Audit log (model output monitoring)
```bash
docker logs --tail 3 classifier-pytorch | grep serving_audit
docker logs --tail 3 generator         | grep serving_audit
```
> "Every request logs a structured JSON line — `message_id`, `predicted_tone`, `confidence`, `latency_ms`. Keyed by `message_id` so it joins with user feedback for retraining."

---

## Part 3 — Grafana dashboard (2 min)

**Switch to Grafana → Dashboards → MLOps → "ML Serving — Classifier, Generator & Feedback"**

**Row 1 — Classifier:** RPS · p95 latency (sub-100ms) · error ratio (green = 0%)

**Row 2 — Generator:** RPS · p95 latency · error ratio

**Row 3 — Feedback:** Approval rate · signals by type · thumbs-down by tone

> "Prometheus scrapes both pods via `prometheus.io/scrape=true` annotations — no manual config. Alert rules fire if p95 > 150ms for 15 min or error ratio > 5%."

**Show one PromQL in Prometheus:**
```
histogram_quantile(0.95, sum(rate(classifier_latency_seconds_bucket[5m])) by (le))
```

---

## Part 4 — Feedback → retraining loop (1 min)

```bash
curl -sS -X POST http://127.0.0.1:8010/feedback \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","tone_shown":"formal","user_action":"thumbs_up"}'
```

> "That `thumbs_up` goes to MinIO → daily batch pipeline joins it as a training label → retrain trigger evaluates three conditions each night:"

```
DATA_TRIGGER:    >= 500 new labeled examples?
QUALITY_TRIGGER: approval rate < 70%?
DRIFT_TRIGGER:   production F1 < 0.60?
→ if any fires: full retrain pipeline runs automatically in CI
→ new model registered in MLflow → manual review → promote
```

---

## Wrap-up (15 sec)

> "Serving owns: two FastAPI microservices, Prometheus metrics + Grafana dashboard, structured audit logs, a `/feedback` endpoint that feeds retraining, and automated data/quality/drift triggers — all without manual SSH."

---

## Q&A cheat sheet

| Question | Answer |
|----------|--------|
| Why `DUMMY_MODE=true` in K8s? | Safe default — flip env var + redeploy once real MLflow artifacts are aliased `prod` |
| How does Prometheus find the pods? | `prometheus.io/scrape: true` annotation + `kubernetes_sd_configs` in Prometheus ConfigMap |
| Promotion gate? | New model beats baseline F1 on holdout + last 30d feedback; p95 regression >20% → rollback |
| Retrain triggers too often? | Thresholds are env vars on the CronJob — change without rebuild |

---

## Emergency fallbacks

| Problem | Fix |
|---------|-----|
| Containers down | `docker start classifier-pytorch generator` |
| Grafana blank | `curl http://127.0.0.1:8001/metrics` — show raw Prometheus output |
| Generator slow | Demo classifier only — same story |
| SSH broken | Show audit log JSON / Grafana screenshots |
