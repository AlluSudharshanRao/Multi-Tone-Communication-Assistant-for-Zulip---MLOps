# API / payload contracts (joint deliverable)

These JSON files are **reference shapes** the team agrees on for the tone-assistant flow: what goes **into** each model service and what comes **out**. They are not runtime config; they support design reviews, tests, and milestone write-ups.

## Files

| File | Role | Purpose |
|------|------|---------|
| [`classifier_input.json`](classifier_input.json) | Classifier **request** | Zulip-style message context + draft `text` to classify. |
| [`classifier_output.json`](classifier_output.json) | Classifier **response** | Tone prediction (e.g. label, probabilities, confidence). |
| [`generator_input.json`](generator_input.json) | Generator **request** | Same message context as the classifier, plus embedded **`classifier_result`** (what the rewriter should condition on). |
| [`generator_output.json`](generator_output.json) | Generator **response** | Rewritten text (and any metadata your API returns). |

Flow: **draft text** → classifier → **generator** uses classifier output to produce **ranked or single rewrite** (exact schema for “multi-tone” variants is up to the team; keep these samples aligned with what `ml-serving` exposes).

## Maintenance

- Update the four files together when the team changes field names, enums, or nesting.
- If the course asks for a single “inference request / model output” pair, point graders at **classifier_*** as the minimal pair and **generator_*** as the second-stage pair.
- Serving manifests under [`k8s/inference/`](../k8s/inference/) should stay consistent with these contracts (paths, JSON keys, HTTP bodies).
