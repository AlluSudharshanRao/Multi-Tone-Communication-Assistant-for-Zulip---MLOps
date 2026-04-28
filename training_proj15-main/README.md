# training_proj15

ML training for Chameleon Cloud: **tone classifier** (`training/train.py`) and **LoRA LLM generator** (`training/train_llm.py`). API samples: `samples/`.

## Quick start

```bash
# Tone (sklearn / DistilBERT)
docker build --build-arg GIT_SHA="$(git rev-parse HEAD)" -f training/Dockerfile -t tone-train:proj15 ./training
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000   # adjust for your setup
docker run --rm --network host -e MLFLOW_TRACKING_URI tone-train:proj15 --config /app/configs/baseline_tone_nb.yaml

# LLM (LoRA)
docker build --build-arg GIT_SHA="$(git rev-parse HEAD)" -f training/Dockerfile.llm -t llm-train:proj15 ./training
docker run --rm --network host -e MLFLOW_TRACKING_URI llm-train:proj15 --config /app/configs/llm_generator_small.yaml
```

Compose (Linux / Chameleon): `docker compose -f training/docker-compose.yml build` then `run` services `tone-train` / `llm-train`.

## Latest-batch retraining

The training stack can now consume a manifest-backed dataset bundle instead of relying only on local seed files.

- `training/prepare_training_data.py` turns the latest batch manifest plus optional feedback artifacts into:
  - `classifier_tone.csv`
  - `generator_train.jsonl`
  - `generator_eval.jsonl`
  - `dataset_manifest.json`
- `training/train.py` and `training/train_llm.py` read `DATASET_MANIFEST_PATH` from the environment when set.
- The Kubernetes training jobs are wired to pull `batch/latest/` and `feedback/` from MinIO before training.

This improves the retraining story, but it does not magically make the live learning signal strong: if feedback data is sparse, seed examples still dominate the generator dataset and the manifest records that limitation explicitly.

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
