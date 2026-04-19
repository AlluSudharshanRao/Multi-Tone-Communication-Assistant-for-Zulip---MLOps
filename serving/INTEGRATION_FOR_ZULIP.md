# Zulip / bot integration — serving API handoff (serving-owned)

This note is for whoever implements the **Zulip bot, outgoing webhook, or small bridge service**. Serving owns **HTTP behavior** of classifier + generator only.

## Base URLs

| Environment | Example (adjust with DevOps) |
|-------------|------------------------------|
| Docker Compose (VM) | `http://127.0.0.1:8001` (classifier), `http://127.0.0.1:8010` (generator) |
| Kubernetes in-cluster | `http://classifier-pytorch.ml-serving.svc.cluster.local:8001`, `http://tone-generator.ml-serving.svc.cluster.local:8010` |

The generator already calls the classifier using **`CLASSIFIER_URL`** inside the cluster. The Zulip bridge typically calls **generator `/generate` only** (which internally calls classifier).

## Timeouts (recommended)

| Call | Suggested client timeout | Notes |
|------|---------------------------|--------|
| `POST /predict` | 3–5 s | CPU DistilBERT is usually &lt; 200 ms p95 in benchmarks; allow headroom. |
| `POST /generate` | 15–30 s | Dummy mode sleeps ~400–600 ms per tone; real LLM/GPU may need more. |

Generator code uses **2.0 s** for the internal classifier hop (`httpx`); if your classifier is slower, raise that in a future serving change — coordinate with serving owner.

## `POST /predict` (classifier)

**Request** (align with `contracts/classifier_input.json`):

```json
{
  "message_id": "zulip_msg_123",
  "text": "user message here",
  "message_type": "stream"
}
```

**Smoke test:**

```bash
curl -sS -X POST "http://127.0.0.1:8001/predict" \
  -H "Content-Type: application/json" \
  -d '{"message_id":"t1","text":"please review when you can","message_type":"stream"}'
```

**Success:** HTTP `200`, JSON includes `predicted_tone`, `probabilities` (formal, friendly, neutral), `confidence`, `latency_ms`, `backend`.

## `POST /generate` (generator)

**Request** (align with `contracts/generator_input.json`):

```json
{
  "message_id": "zulip_msg_123",
  "text": "user message here",
  "message_type": "stream"
}
```

**Smoke test:**

```bash
curl -sS -X POST "http://127.0.0.1:8010/generate" \
  -H "Content-Type: application/json" \
  -d '{"message_id":"t1","text":"please review when you can","message_type":"stream"}'
```

**Success:** HTTP `200`, JSON includes `variants.formal.text`, `variants.friendly.text`, `variants.neutral.text`, `classifier_result`, `offensive_content_flagged`, `total_latency_ms`.

## Auth (team decision)

- If APIs are **ClusterIP only**, the bridge must run **inside the cluster** or use **kubectl port-forward** for dev.
- If exposed via **Ingress**, use **HTTPS**, restrict by network policy or **shared secret** header (implement in bridge or add middleware in serving — discuss before course freeze).

## Observability (team stack)

Use **team Grafana / Prometheus only** (see `OBSERVABILITY_AND_RELEASE.md`). Serving exposes **`GET /metrics`** on the same ports as HTTP.

## Optional audit JSON logs (for log pipelines)

Set on classifier and/or generator containers:

- `SERVING_AUDIT_LOG=true` — one JSON log line per successful request at INFO (low-PII: lengths + IDs + labels, **not** full message text unless explicitly enabled).
- `SERVING_AUDIT_LOG_INCLUDE_TEXT=true` — **not recommended** for production; includes truncated text snippet for debug only.

## Local smoke (CI or post-deploy)

From repo:

```bash
bash serving/scripts/smoke_predict_generate.sh "http://CLASSIFIER:8001" "http://GENERATOR:8010"
```
