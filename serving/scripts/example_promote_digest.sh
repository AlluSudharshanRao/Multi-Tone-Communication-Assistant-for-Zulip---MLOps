#!/usr/bin/env bash
# Promote serving with MLflow Registry model aliases.
#
# Usage:
#   CLASSIFIER_MODEL_URI=models:/tone-classifier@prod \
#   GENERATOR_MODEL_URI=models:/tone-generator-lora@prod \
#   NEW_CLASSIFIER_IMAGE=<digest-or-tag> NEW_GENERATOR_IMAGE=<digest-or-tag> \
#   ./example_promote_digest.sh
#
# Notes:
# - This script updates deployment images and env vars in-place (kubectl set image/set env).
# - Model artifacts are fetched by the app at startup from MLflow using model URIs.
set -euo pipefail

: "${CLASSIFIER_MODEL_URI:?set CLASSIFIER_MODEL_URI, e.g. models:/tone-classifier@prod}"
: "${GENERATOR_MODEL_URI:?set GENERATOR_MODEL_URI, e.g. models:/tone-generator-lora@prod}"

NAMESPACE="${NAMESPACE:-ml-serving}"
CLASSIFIER_DEPLOYMENT="${CLASSIFIER_DEPLOYMENT:-classifier-pytorch}"
GENERATOR_DEPLOYMENT="${GENERATOR_DEPLOYMENT:-tone-generator}"
MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://mlflow.ml-platform.svc.cluster.local:5000}"
CLASSIFIER_ARTIFACT_PATH="${CLASSIFIER_ARTIFACT_PATH:-model}"
GENERATOR_ARTIFACT_PATH="${GENERATOR_ARTIFACT_PATH:-lora_checkpoint}"
GENERATOR_MODEL_NAME="${GENERATOR_MODEL_NAME:-HuggingFaceTB/SmolLM2-135M-Instruct}"
CTX="${KUBECTL_CONTEXT:-}"

CTX_ARGS=()
if [[ -n "${CTX}" ]]; then
  CTX_ARGS=(--context "${CTX}")
fi

if [[ -n "${NEW_CLASSIFIER_IMAGE:-}" ]]; then
  kubectl "${CTX_ARGS[@]}" -n "${NAMESPACE}" set image "deployment/${CLASSIFIER_DEPLOYMENT}" \
    "${CLASSIFIER_DEPLOYMENT}=${NEW_CLASSIFIER_IMAGE}"
fi

if [[ -n "${NEW_GENERATOR_IMAGE:-}" ]]; then
  kubectl "${CTX_ARGS[@]}" -n "${NAMESPACE}" set image "deployment/${GENERATOR_DEPLOYMENT}" \
    "${GENERATOR_DEPLOYMENT}=${NEW_GENERATOR_IMAGE}"
fi

kubectl "${CTX_ARGS[@]}" -n "${NAMESPACE}" set env "deployment/${CLASSIFIER_DEPLOYMENT}" \
  DUMMY_MODE=false \
  MODEL_PATH=distilbert-base-uncased \
  MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI}" \
  CLASSIFIER_MODEL_URI="${CLASSIFIER_MODEL_URI}" \
  MLFLOW_RUN_ID- \
  MLFLOW_ARTIFACT_PATH="${CLASSIFIER_ARTIFACT_PATH}"

kubectl "${CTX_ARGS[@]}" -n "${NAMESPACE}" set env "deployment/${GENERATOR_DEPLOYMENT}" \
  DUMMY_MODE=false \
  GENERATOR_BACKEND=causal \
  MODEL_NAME="${GENERATOR_MODEL_NAME}" \
  MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI}" \
  GENERATOR_PEFT_MODEL_URI="${GENERATOR_MODEL_URI}" \
  PEFT_MLFLOW_RUN_ID- \
  PEFT_MLFLOW_ARTIFACT_PATH="${GENERATOR_ARTIFACT_PATH}"

kubectl "${CTX_ARGS[@]}" -n "${NAMESPACE}" rollout status "deployment/${CLASSIFIER_DEPLOYMENT}" --timeout=5m
kubectl "${CTX_ARGS[@]}" -n "${NAMESPACE}" rollout status "deployment/${GENERATOR_DEPLOYMENT}" --timeout=10m

echo "Promotion complete."
echo "Classifier model uri: ${CLASSIFIER_MODEL_URI}"
echo "Generator model uri:  ${GENERATOR_MODEL_URI}"
echo "Run smoke: serving/scripts/smoke_predict_generate.sh <classifier_url> <generator_url>"
