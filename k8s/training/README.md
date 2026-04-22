# Training

Training jobs run in namespace `ml-training`.

## What is here

- classifier training job
- generator training job
- register bundle that updates MLflow aliases

## Runtime flow

1. Training jobs read data from MinIO.
2. Runs are logged to MLflow.
3. `register-and-alias-latest` assigns aliases such as `canary` and `prod`.
4. Serving deployments resolve models from those aliases.

## Apply

```bash
kubectl apply -k k8s/training/
kubectl apply -k k8s/training/register-bundle/
```

In normal operation this is handled by [deploy_ml_workloads.yml](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\infra\ansible\playbooks\deploy_ml_workloads.yml).

## Verification

```bash
kubectl get jobs,pods -n ml-training
kubectl logs -n ml-training job/classifier-training
kubectl logs -n ml-training job/generator-training
kubectl logs -n ml-training job/register-and-alias-latest
```

## Notes

- The register job is applied from `register-bundle/` so the ConfigMap and Job stay aligned.
- The current playbook waits for both training jobs and the register job to finish.
