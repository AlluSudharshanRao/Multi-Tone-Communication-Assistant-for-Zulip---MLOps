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

> "My role is **serving**. I own the two microservices that power the tone assistant — a **classifier** and a **generator**. When a Zulip user sends a message, the classifier reads it and predicts whether the tone is formal, friendly, or neutral. The generator then rewrites the same message in all three tones so the user can pick the one that fits best."

> "Both services run as FastAPI apps — containerised with Docker locally and deployed as Kubernetes pods in the cluster. There's also a Zulip bridge that connects them to the actual bot. My job is to make sure these services are fast, reliable, observable, and keep improving over time from real user feedback."

```
Zulip message → /zulip/webhook (bridge)
    → generator /generate
        → classifier /predict  (DistilBERT, 3-class tone)
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
> "So I'm sending a casual, slightly frustrated message to the classifier. It returns a `predicted_tone` — probably neutral or friendly — along with the full probability breakdown across all three classes and the `latency_ms`. In our benchmarks on Chameleon Cloud this runs at **p95 under 83 milliseconds** on CPU, which is well inside our 100ms target."

### Generator (full pipeline)
```bash
curl -sS -X POST http://127.0.0.1:8010/generate \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","text":"yo can u just fix the bug already its been 3 days","message_type":"stream"}' \
  | python3 -m json.tool
```
> "Now I'm hitting the generator with the same message. Internally it calls the classifier first, then produces three rewrites. Look at `variants.formal` — that's a polished, professional version. `variants.friendly` keeps it warm but appropriate. `variants.neutral` is clean and direct. There's also an `offensive_content_flagged` field — if profanity is detected, that's set to true and the output is blocked. The `total_latency_ms` covers the entire round trip including the internal classifier call."

### Audit log (model output monitoring)
```bash
docker logs --tail 3 classifier-pytorch | grep serving_audit
docker logs --tail 3 generator         | grep serving_audit
```
> "Every successful request writes a structured JSON audit line to the container logs. It captures the `message_id`, `predicted_tone`, `confidence`, and `latency_ms` — but not the raw message text by default, so it's low-PII. The key thing is the `message_id` — that same ID is what links this log entry to user feedback later, which is how we build our retraining dataset."

---

## Part 3 — Grafana dashboard (2 min)

**Switch to Grafana → Dashboards → MLOps → "ML Serving — Classifier, Generator & Feedback"**

> "This is the serving dashboard I built — it has three rows. The first row is for the classifier: requests per second broken down by status, p95 and p50 latency side by side, and an error ratio stat panel that turns red if it goes above 5%."

**Row 1 — Classifier:** RPS by status · p95+p50 latency · error ratio (colour threshold: green < 1%, red ≥ 5%)

> "The second row is the same layout for the generator. You can see the latency is higher here — around 600ms in dummy mode — but on a real GPU with SmolLM2 we'd expect p95 around 490ms."

**Row 2 — Generator:** RPS · p95+p50 latency · error ratio

> "The third row is what makes this more than just uptime monitoring — it tracks user feedback. The approval rate stat shows what percentage of responses users reacted positively to. The bar chart shows which tones are getting rejected the most. If 'formal' keeps getting thumbs-down, that's a signal the model needs retraining on formal rewrites."

**Row 3 — Feedback:** Approval rate · signals by type · thumbs-down by tone

> "The whole thing is provisioned automatically — the dashboard JSON is in the repo, and whenever I push a change to it, a GitHub Actions workflow applies the Grafana ConfigMap and restarts the pod. No manual import needed. Prometheus scrapes both pods via `prometheus.io/scrape=true` pod annotations, so any new pod in the `ml-serving` namespace is picked up automatically."

**Show one PromQL in Prometheus:**
```
histogram_quantile(0.95, sum(rate(classifier_latency_seconds_bucket[5m])) by (le))
```
> "This is the same query that's in our alert rules. If p95 stays above 150ms for 15 minutes, Alertmanager fires. Same pattern for the generator at 800ms."

---

## Part 4 — Feedback → retraining loop (1 min)

```bash
curl -sS -X POST http://127.0.0.1:8010/feedback \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","tone_shown":"formal","user_action":"thumbs_up"}'
```

> "This is what the full feedback loop looks like. The Zulip bridge exposes a `/feedback` endpoint. When a user taps thumbs-up or thumbs-down on a rewrite, this call is made. It writes a JSON record into MinIO — the same MinIO that stores our models and training artifacts. The record includes the `message_id`, the tone that was shown, and what the user did."

> "Every night the batch pipeline reads all the feedback records from that day, joins them by `message_id` back to the classifier's audit log, and builds a labeled dataset. That feeds the retrain trigger, which checks three things:"

```
DATA_TRIGGER:    >= 500 new labeled examples?      → model hasn't seen enough new data
QUALITY_TRIGGER: approval rate < 70%?              → users are rejecting too many responses
DRIFT_TRIGGER:   production F1 < 0.60?             → model quality confirmed degrading

→ if any fires: full retrain pipeline runs in CI
→ new models registered in MLflow with new experiment run
→ promotion gate: must beat current production F1 on holdout + last 30d feedback slice
→ on pass: model gets the 'production' alias → deploy workflow picks it up
```

> "The key design decision here is that nothing is hardcoded. The thresholds — 500 rows, 70%, 0.60 — are all environment variables on the Kubernetes CronJob. You can tune them without rebuilding any image. And the promotion gate is strict: a new model has to beat the current production model on both the fixed holdout set and on recent real-world feedback. If latency p95 regresses by more than 20%, the promotion is blocked too."

---

## Wrap-up (15 sec)

> "So to summarize what serving owns end-to-end: two FastAPI microservices — classifier and generator — running on Kubernetes, with Prometheus metrics and a live Grafana dashboard covering latency, throughput, errors, and now user feedback. Structured audit logs for every model output. A `/feedback` endpoint that feeds directly into our training data. And automated data, quality, and drift triggers that close the loop from production usage back to model improvement — all without anyone having to manually SSH in or run a training job by hand. That's the full MLOps lifecycle on the serving side."

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
