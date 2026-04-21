# Demo Script — Serving Track
**Project:** Multi-Tone Communication Assistant for Zulip  
**Role:** Serving — Rithwik Amajala  
**Time budget:** ~10–12 minutes  

---

## Before the demo (prep checklist — do this 10 min before)

```bash
# On your laptop, open 3 browser tabs:
# 1. https://grafana.129.114.27.192.nip.io/   (admin / grafana-password)
# 2. https://prometheus.129.114.27.192.nip.io/
# 3. https://github.com/AlluSudharshanRao/Multi-Tone-Communication-Assistant-for-Zulip---MLOps/actions

# SSH into the VM (keep this terminal open)
ssh -i ~/.ssh/id_rsa_chameleon cc@129.114.25.7
cd Multi-Tone-Communication-Assistant-for-Zulip---MLOps/serving

# Confirm containers are up
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
# Expected: classifier-pytorch (healthy), generator (healthy)

# Quick smoke test to confirm both respond
bash scripts/smoke_predict_generate.sh http://127.0.0.1:8001 http://127.0.0.1:8010
# Expected: OK: smoke checks passed
```

---

## Part 1 — "What we built" (2 min)

**Say:**
> "My role is **serving**. I own the two microservices that take a Zulip message, classify its tone, and generate three rewritten variants — formal, friendly, and neutral. I'll walk through the live API, the observability stack, and the automated retraining loop."

**Show on screen:** The repo on GitHub, open `serving/` folder.

> "Everything runs as Docker containers locally and as Kubernetes deployments in the cluster. The Zulip bridge connects the two to Zulip itself."

**Architecture in one sentence:**
```
Zulip message → bridge /zulip/webhook
    → generator /generate  (calls classifier internally)
    → classifier /predict  (DistilBERT, 3-class tone)
    ← 3 tone variants back to Zulip
```

---

## Part 2 — Live API demo (3 min)

**Switch to VM terminal.**

### 2a. Classifier
```bash
curl -sS -X POST http://127.0.0.1:8001/predict \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","text":"yo can u just fix the bug already its been 3 days","message_type":"stream"}' | python3 -m json.tool
```
**Point out:**
- `predicted_tone: "neutral"` or `"friendly"`
- `probabilities` — 3 class scores
- `confidence`, `latency_ms`, `backend: pytorch`
- Meets **p95 < 83ms** target (show from SERVING_OPTIONS.md if asked)

### 2b. Generator (full pipeline)
```bash
curl -sS -X POST http://127.0.0.1:8010/generate \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","text":"yo can u just fix the bug already its been 3 days","message_type":"stream"}' | python3 -m json.tool
```
**Point out:**
- `variants.formal.text` — professional rewrite
- `variants.friendly.text` — warm rewrite
- `variants.neutral.text` — neutral rewrite
- `classifier_result` — embedded classifier call
- `offensive_content_flagged` — safety check
- `total_latency_ms` — end-to-end latency

### 2c. Audit log (model output monitoring)
```bash
docker logs --tail 5 classifier-pytorch | grep serving_audit
docker logs --tail 5 generator         | grep serving_audit
```
**Point out:**
> "Every request emits a structured JSON audit log — `message_id`, `predicted_tone`, `confidence`, `inference_latency_ms`. This is our model output monitoring. Keyed by `message_id` so we can join it with user feedback later."

---

## Part 3 — Observability: Grafana + Prometheus (2 min)

**Switch to browser — Grafana tab.**

Navigate to: `Dashboards → MLOps → ML Serving — Classifier, Generator & Feedback`

**Walk through the 3 rows:**

**Row 1 — Classifier**
- RPS by status (ok/error)
- p95 + p50 latency — point to the **sub-100ms** value
- Error ratio — should be green (0%)

**Row 2 — Generator**
- RPS, latency, error ratio
- p95 ~600ms in dummy mode; GPU would bring this to ~490ms

**Row 3 — Feedback signals** *(new)*
- Approval rate — thumbs_up / total
- Feedback by action type
- Thumbs-down by tone — shows which tone users reject most

**Say:**
> "Prometheus scrapes both pods every 15 seconds via `prometheus.io/scrape=true` annotations on the K8s deployments. No manual config needed — just deploy and it appears."

**Switch to Prometheus tab** — paste into the search box:
```
classifier_requests_total
```
Show the raw metric. Then show:
```
histogram_quantile(0.95, sum(rate(classifier_latency_seconds_bucket[5m])) by (le))
```
> "These are the same PromQL queries in our alert rules — if p95 exceeds 150ms for 15 minutes, Alertmanager fires."

---

## Part 4 — CI/CD: end-to-end automation (2 min)

**Switch to browser — GitHub Actions tab.**

Show the Actions page. Point to the 6 workflows:

| Workflow | What it does |
|----------|-------------|
| `build-push-ml-images` | Builds classifier + generator Docker images on push to main |
| `deploy-observability` | Applies Grafana/Prometheus manifests + restarts pods on config change |
| `deploy-serving-staging` | Auto-deploys to staging after build + runs smoke test |
| `promote-inference` | Manual canary → prod promotion with image tag |
| `rollback-inference` | One-click rollback to previous image |
| `retrain-on-trigger` | Runs full retrain pipeline when trigger fires |

**Say:**
> "The full deploy flow is: push code → images built → staging deployed automatically → smoke test runs via port-forward — no SSH required. Promotion to production is a manual gate in `promote-inference` so we always review MLflow metrics before shipping."

**Show the `deploy-serving-staging` workflow file briefly:**
> "After the build, it applies the staging overlay, waits for rollout, then calls our smoke script against `kubectl port-forward`. If it fails, the whole workflow fails — broken serving code can't reach production."

---

## Part 5 — Feedback loop + retraining (2 min)

**Switch to browser — show `integrations/zulip-bridge/app.py` on GitHub, scroll to `/feedback` endpoint.**

**Say:**
> "When a user reacts in Zulip — thumbs up, thumbs down, or selects a tone — the Zulip bot calls our `/feedback` endpoint."

```bash
# Demo the feedback endpoint
curl -sS -X POST http://127.0.0.1:8010/feedback \
  -H 'Content-Type: application/json' \
  -d '{"message_id":"demo_1","tone_shown":"formal","user_action":"thumbs_up"}'
```

**Then show the full loop on a whiteboard or verbally:**

```
POST /feedback  →  MinIO  feedback/2026-04-20/{uuid}.json
                        ↓ (daily batch pipeline)
              training dataset with feedback labels merged in
                        ↓ (daily retrain trigger at 02:00 UTC)
              Evaluates 3 conditions:
                DATA:    >= 500 new labeled examples?
                QUALITY: approval rate < 70%?
                DRIFT:   production F1 < 0.60?
                        ↓ (if any fires → GitHub Actions at 03:00 UTC)
              retrain classifier + generator jobs in K8s
              → register new model in MLflow
              → manual review → promote-inference
```

> "No human needs to manually trigger retraining. The CronJob evaluates conditions daily and writes a trigger record to MinIO. GitHub Actions picks it up and runs the full pipeline."

---

## Part 6 — Promotion / Rollback (1 min)

**Show GitHub → Actions → `promote-inference` workflow.**

> "Promotion is a single GitHub Actions `workflow_dispatch` — you pick the tier (staging/canary/prod) and the image tag. It runs `kubectl set image` and waits for the rollout."

> "Rollback is the same pattern in reverse — `rollback-inference` reverts to the previous image tag. Both are scriptable and audit-logged in GitHub Actions history — no SSH, no manual kubectl."

---

## Part 7 — Wrap-up (30 sec)

**Say:**
> "To summarize what serving owns end-to-end:
> 1. **Two FastAPI microservices** — classifier (DistilBERT ONNX, p95 48ms) and generator (SmolLM2 + LoRA)
> 2. **Observability** — Prometheus metrics, structured audit logs, Grafana dashboard with classifier, generator, and feedback panels
> 3. **Feedback capture** — `/feedback` endpoint persists to MinIO, keyed by `message_id`
> 4. **Automated retraining** — data/quality/drift triggers evaluated daily, full pipeline in CI
> 5. **GitOps CI/CD** — build → staging deploy → smoke test → manual promote → one-click rollback"

---

## Likely questions + answers

**Q: Why dummy mode still in K8s?**
> "The K8s manifests have `DUMMY_MODE=true` as a safe default. Once the real model artifacts are in MLflow with the `prod` alias, we flip that env var in the overlay and redeploy via `promote-inference`. The serving code already supports real DistilBERT (pytorch/onnx/quantized) and SmolLM2+LoRA — it's a config change, not a code change."

**Q: How does Prometheus know to scrape the pods?**
> "Both K8s Deployments have `prometheus.io/scrape: 'true'` annotations on the pod template. Our Prometheus ConfigMap uses `kubernetes_sd_configs` with a `relabel_configs` that reads those annotations — zero manual target config."

**Q: What's the promotion gate / quality bar?**
> "New model must beat baseline F1 on a fixed holdout set AND the last 30 days of feedback data. If p95 latency regresses by >20% or error ratio spikes above 5% for 10 minutes, Alertmanager fires and we roll back."

**Q: What if the retrain trigger fires too often?**
> "Thresholds are env vars on the CronJob — `DATA_TRIGGER_COUNT`, `QUALITY_THRESHOLD`, `DRIFT_THRESHOLD`. Change them without rebuilding the image. The watermark file in MinIO prevents double-triggering."

**Q: How does feedback join with training data?**
> "The batch pipeline reads `feedback/` prefix from MinIO in Step 2b. Feedback rows with `preferred_text` (user-edited rewrites) are directly added as labeled training examples. `thumbs_up` improves confidence in the predicted tone; `thumbs_down` + `correct_tone` flips the label."

---

## Emergency fallbacks (if live demo breaks)

| Problem | Fallback |
|---------|---------|
| Containers not running | `docker start classifier-pytorch generator` |
| Grafana blank | Show `curl http://127.0.0.1:8001/metrics` output instead |
| Generator slow/timeout | Demo classifier only — still shows the full flow |
| SSH can't connect | Show GitHub Actions run history as proof of automation |
| No traffic in Grafana | Run benchmark: `python evaluate/benchmark.py --url http://127.0.0.1:8001/predict --endpoint classifier --concurrency 5 --n 50 --label demo` |
