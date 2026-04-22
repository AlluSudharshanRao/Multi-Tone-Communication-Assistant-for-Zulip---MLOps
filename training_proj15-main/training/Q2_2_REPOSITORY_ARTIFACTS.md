# Q2.2 — Repository artifacts

Training must have run on **Chameleon** in **Docker** with these files. Two frameworks: **`train.py`** (classifier) and **`train_llm.py`** (LLM).

Paths: repository root `training_proj15/`, files under **`training/`**.

## LMS uploads (two file pickers)

| Picker | Include |
|--------|---------|
| **Dockerfile(s)** | `Dockerfile`, `Dockerfile.llm`, optional `Dockerfile.dev`, recommended `docker-compose.yml` |
| **Code + configs** | `train.py`, `train_llm.py`, `requirements.txt`, `requirements-llm.txt`, `configs/baseline_tone_nb.yaml`, `configs/candidate_tone_logistic.yaml`, `configs/candidate_tone_random_forest.yaml`, `configs/candidate_tone_distilbert.yaml`, `configs/llm_generator_small.yaml` |

If each picker allows one archive only, use the zip layouts below.

### Zip: `q2_2_dockerfiles.zip`

```text
Dockerfile
Dockerfile.llm
Dockerfile.dev
docker-compose.yml
```

### Zip: `q2_2_code_and_configs.zip`

```text
train.py
train_llm.py
requirements.txt
requirements-llm.txt
configs/
  baseline_tone_nb.yaml
  candidate_tone_logistic.yaml
  candidate_tone_random_forest.yaml
  candidate_tone_distilbert.yaml
  llm_generator_small.yaml
```

## Do not submit

- Jupyter notebooks as the primary training entrypoint  
- `mlruns/`, checkpoints, or Hugging Face cache unless required  

## Optional LMS note

> Docker: `training/Dockerfile`, `Dockerfile.llm`, optional `Dockerfile.dev`, `docker-compose.yml`. Code: `train.py`, `train_llm.py`, `requirements.txt`, `requirements-llm.txt`, and the listed YAMLs under `training/configs/`. Executed on Chameleon with MLflow.

See **`Q2_COURSE_SUBMISSION.md`** and **`DEPLOYMENT.md`**.
