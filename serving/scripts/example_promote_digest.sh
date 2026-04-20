#!/usr/bin/env bash
# Example promotion step (serving-owned documentation stub).
# Replace CLUSTER_TOOLING with your GitOps/CI flow — serving does not mutate platform manifests here.
#
# Inputs:
#   NEW_CLASSIFIER_IMAGE  e.g. ghcr.io/org/tone-classifier@sha256:...
#   NEW_GENERATOR_IMAGE   e.g. ghcr.io/org/tone-generator@sha256:...
#   KUBECTL_CONTEXT         optional
#
# Example (run only where you have kube credentials — typically CI, not random laptops):
#   NEW_CLASSIFIER_IMAGE=... NEW_GENERATOR_IMAGE=... ./example_promote_digest.sh
set -euo pipefail

: "${NEW_CLASSIFIER_IMAGE:?set NEW_CLASSIFIER_IMAGE}"
: "${NEW_GENERATOR_IMAGE:?set NEW_GENERATOR_IMAGE}"

CTX="${KUBECTL_CONTEXT:-}"
CTX_ARGS=()
if [[ -n "${CTX}" ]]; then
  CTX_ARGS=(--context "${CTX}")
fi

echo "This script is an example. Uncomment kubectl lines after your team agrees namespace and object names."

# kubectl "${CTX_ARGS[@]}" -n ml-serving set image deployment/classifier-pytorch classifier-pytorch="${NEW_CLASSIFIER_IMAGE}"
# kubectl "${CTX_ARGS[@]}" -n ml-serving set image deployment/tone-generator tone-generator="${NEW_GENERATOR_IMAGE}"
# kubectl "${CTX_ARGS[@]}" -n ml-serving rollout status deployment/classifier-pytorch --timeout=5m
# kubectl "${CTX_ARGS[@]}" -n ml-serving rollout status deployment/tone-generator --timeout=10m

echo "Would set classifier to: ${NEW_CLASSIFIER_IMAGE}"
echo "Would set generator to:  ${NEW_GENERATOR_IMAGE}"
echo "Then run: serving/scripts/smoke_predict_generate.sh against the cluster endpoints (or port-forward)."
