#!/usr/bin/env bash
# Contract smoke: classifier /predict + generator /generate (serving-owned).
# Usage:
#   ./smoke_predict_generate.sh [CLASSIFIER_BASE] [GENERATOR_BASE]
# Defaults: http://127.0.0.1:8001  http://127.0.0.1:8010
set -euo pipefail

CLASSIFIER_BASE="${1:-http://127.0.0.1:8001}"
GENERATOR_BASE="${2:-http://127.0.0.1:8010}"

payload='{"message_id":"smoke_1","text":"please review when you can","message_type":"stream"}'

http_post_json() {
  local url="$1"
  local label="$2"
  local tmp
  tmp="$(mktemp)"
  local code
  code="$(curl -sS -o "$tmp" -w "%{http_code}" -X POST "$url" \
    -H 'Content-Type: application/json' \
    -d "${payload}" || true)"
  if [[ "$code" != "200" ]]; then
    echo "FAIL: ${label} HTTP ${code} (expected 200)" >&2
    head -c 800 "$tmp" >&2 || true
    echo >&2
    rm -f "$tmp"
    exit 1
  fi
  cat "$tmp"
  rm -f "$tmp"
}

echo "==> POST ${CLASSIFIER_BASE}/predict"
resp="$(http_post_json "${CLASSIFIER_BASE}/predict" "classifier")"
echo "${resp}" | head -c 400
echo

if command -v jq >/dev/null 2>&1; then
  echo "${resp}" | jq -e '.predicted_tone and .probabilities and .latency_ms' >/dev/null
else
  echo "${resp}" | grep -q predicted_tone
fi

echo "==> POST ${GENERATOR_BASE}/generate"
gresp="$(http_post_json "${GENERATOR_BASE}/generate" "generator")"
echo "${gresp}" | head -c 600
echo

if command -v jq >/dev/null 2>&1; then
  echo "${gresp}" | jq -e '.variants.formal.text and .variants.friendly.text and .variants.neutral.text' >/dev/null
else
  echo "${gresp}" | grep -q '"formal"'
fi

echo "OK: smoke checks passed"
