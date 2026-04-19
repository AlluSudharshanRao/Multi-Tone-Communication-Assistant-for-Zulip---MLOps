#!/usr/bin/env bash
# Contract smoke: classifier /predict + generator /generate (serving-owned).
# Usage:
#   ./smoke_predict_generate.sh http://127.0.0.1:8001 http://127.0.0.1:8010
set -euo pipefail

CLASSIFIER_BASE="${1:-http://127.0.0.1:8001}"
GENERATOR_BASE="${2:-http://127.0.0.1:8010}"

payload='{"message_id":"smoke_1","text":"please review when you can","message_type":"stream"}'

echo "==> POST ${CLASSIFIER_BASE}/predict"
resp="$(curl -fsS -X POST "${CLASSIFIER_BASE}/predict" -H 'Content-Type: application/json' -d "${payload}")"
echo "${resp}" | head -c 400
echo

if command -v jq >/dev/null 2>&1; then
  echo "${resp}" | jq -e '.predicted_tone and .probabilities and .latency_ms' >/dev/null
else
  echo "${resp}" | grep -q predicted_tone
fi

echo "==> POST ${GENERATOR_BASE}/generate"
gresp="$(curl -fsS -X POST "${GENERATOR_BASE}/generate" -H 'Content-Type: application/json' -d "${payload}")"
echo "${gresp}" | head -c 600
echo

if command -v jq >/dev/null 2>&1; then
  echo "${gresp}" | jq -e '.variants.formal.text and .variants.friendly.text and .variants.neutral.text' >/dev/null
else
  echo "${gresp}" | grep -q '"formal"'
fi

echo "OK: smoke checks passed"
