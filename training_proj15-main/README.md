# Training Code

This directory contains the model training code used by the cluster training jobs.

## Main components

- `training/train.py`: classifier training
- `training/train_llm.py`: generator training
- `training/configs/`: config-driven training settings
- `training/Dockerfile`: classifier training image
- `training/Dockerfile.llm`: generator training image

## Runtime flow

- training reads prepared data from MinIO
- runs are logged to MLflow
- trained models are registered and aliased for serving

## Local build examples

```bash
docker build -f training/Dockerfile -t tone-train ./training
docker build -f training/Dockerfile.llm -t llm-train ./training
```

## Related docs

## Latest-batch retraining

The training stack can now consume a manifest-backed dataset bundle instead of relying only on local seed files.

- `training/prepare_training_data.py` turns the latest batch manifest plus optional feedback artifacts into:
  - `classifier_tone.csv`
  - `generator_train.jsonl`
  - `generator_eval.jsonl`
  - `dataset_manifest.json`
- `training/train.py` and `training/train_llm.py` read `DATASET_MANIFEST_PATH` from the environment when set.
- The Kubernetes training jobs are wired to pull `batch/latest/` and `feedback/` from MinIO before training.

This improves the retraining story: `prepare_training_data.py` now prefers `batch/latest/classifier_dataset.csv`, `batch/latest/generator_train.jsonl`, and `batch/latest/generator_val.jsonl` when they exist, then layers user feedback on top. If those batch artifacts are missing, it falls back to the repo seed files.

The live learning signal can still be weak if feedback is sparse, and the generated manifest records that limitation explicitly.

## Layout

| Path | Content |
|------|---------|
| `training/train.py` | Classifier: YAML config, sklearn + optional DistilBERT, Optuna, MLflow |
| `training/train_llm.py` | Generator: LoRA SFT, MLflow |
| `training/prepare_training_data.py` | Build manifest-backed classifier/generator datasets from latest batch + feedback |
| `training/dataset_contract.py` | Shared dataset manifest resolver |
| `training/configs/*.yaml` | Training configurations |
| `training/Dockerfile` | Classifier image |
| `training/Dockerfile.llm` | LLM image |
| `training/Dockerfile.dev` | Dev image (optional) |
| `training/docker-compose.yml` | `tone-train` + `llm-train`, host network |

## Documentation

| Document | Description |
|----------|-------------|
| [training/DEPLOYMENT.md](training/DEPLOYMENT.md) | MLflow, firewall, Docker |
| [training/Q2_COURSE_SUBMISSION.md](training/Q2_COURSE_SUBMISSION.md) | Course Q2 checklist |
| [training/Q2_2_REPOSITORY_ARTIFACTS.md](training/Q2_2_REPOSITORY_ARTIFACTS.md) | Artifact upload list |
| [training/Q2_1_TRAINING_RUNS_TABLE_FILLED.md](training/Q2_1_TRAINING_RUNS_TABLE_FILLED.md) | Q2.1 table draft |
| `DOCS/` | Course PDFs |

## Rubric alignment (summary)

- Training via **Docker** on Chameleon; **MLflow** tracking.
- **Config-driven** (`train.py` / `train_llm.py` + YAML); **Optuna** where enabled for sklearn.
- Submission details: `Q2_COURSE_SUBMISSION.md`.
- [training/DEPLOYMENT.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\training_proj15-main\training\DEPLOYMENT.md)
- [../k8s/training/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\training\README.md)
