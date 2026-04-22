# Q2 Training contributions — submission guide

Use this document for **ECE-GY 9183 (or equivalent) training-role deliverables**. All work must be **executed on Chameleon Cloud** from **inside a Docker container** on a **compute instance**, with runs tracked in **MLflow**. Local-only training does not count for credit.

**Team / repo:** `training_proj15`  
**Framework 1 — tone classifier:** `train.py` + YAML configs under `configs/`  
**Framework 2 — LLM generator (LoRA):** `train_llm.py` + `Dockerfile.llm` + `configs/llm_generator_small.yaml`  

Both are **config-driven Python scripts** (not notebooks), containerized on Chameleon, tracked in MLflow.

---

## Question 2 — Training contributions (overview)

| Sub-question | Points | Deliverable type |
|--------------|--------|-------------------|
| **Q2.1** Training runs table | 4 | PDF upload (clickable MLflow links) |
| **Q2.2** Repository artifacts | 3 | File upload (Dockerfile + script + configs) |
| **Q2.3** Demo video | 1 | Video upload |
| **Q2.4** Live MLflow service | 1 | URL in LMS |
| **Q3** Bonus (Ray Train) | 0 (extra) | Optional PDF + artifacts |

---

## Q2.1 Training runs table (PDF)

### Requirements

- Table of training runs; **highlight** rows you consider most promising.
- Each row includes a **working MLflow run link** (test every link in a fresh browser / incognito).
- **Notes** explain tradeoffs for your “manager” (quality vs training speed vs serving cost).
- Include at least **one simple baseline** plus **other candidates**.
- **Submit as PDF** with **clickable hyperlinks** (Word/Google Docs → Export PDF, or LaTeX `\href{}{}`).

### Column definitions (match the rubric)

| Column | What to put |
|--------|-------------|
| **Candidate** | Short name (e.g. `baseline_nb`, `logistic_optuna`, `distilbert`). |
| **MLflow run link** | Full URL, e.g. `http://<FLOATING_IP>:5000/#/experiments/<EXP_ID>/runs/<RUN_ID>` (copy from MLflow UI). |
| **Code version** | Git SHA from run tag **`code_version_git_sha`** (must match Docker image built with `GIT_SHA` build-arg). |
| **Key hyperparams** | Short summary from run **Parameters** (`model.type`, TF-IDF / `model.params.*`, Optuna `best.*` if nested). |
| **Key model metrics** | **Classifier:** `accuracy`, `f1_macro`, per-class `f1_*`, `log_loss` if logged. **LLM:** `last_loss` / `last_eval_loss` (as `last_*` metrics from TRL), or whatever your run logs. |
| **Key training cost metrics** | **Classifier:** `fit_wall_seconds`, `tuning_wall_seconds`, `fit_samples_per_second`, `cost_avg_epoch_wall_seconds`, solver/estimator timing, `training_gpu_hours`. **LLM:** `train_wall_seconds`, `cost_avg_epoch_wall_seconds`, `training_gpu_hours`. |
| **Notes** | Tradeoff + why this row is or isn’t your pick; what to try next. |

### Template table (copy into Word/Google Docs / LaTeX, then export PDF)

Replace `<FLOATING_IP>`, experiment/run IDs, and SHAs after each Chameleon Docker run.

| Candidate | MLflow run link | Code version | Key hyperparams | Key model metrics | Key training cost metrics | Notes |
|-----------|-----------------|--------------|-----------------|-------------------|---------------------------|-------|
| **baseline** (Multinomial NB + TF-IDF) | `http://<FLOATING_IP>:5000/#/experiments/_/runs/_` | `<sha>` | `model.type=multinomial_nb`; TF-IDF per `baseline_tone_nb.yaml` | `accuracy`, `f1_macro`, `f1_*` | `fit_wall_seconds`, `fit_samples_per_second`, `training_gpu_hours` | Baseline: fast, cheap; anchors comparison. |
| candidate_logistic (+ Optuna) | `http://...` | `<sha>` | `logistic_regression`; tuned `C`, `tfidf.max_features`, `ngram_max` | same (+ `log_loss` if present) | `tuning_wall_seconds`, `fit_wall_seconds`, `time_per_solver_iter_seconds` | **Optuna** (not grid search); strong linear candidate. |
| candidate_random_forest (+ Optuna) | `http://...` | `<sha>` | `random_forest`; search over trees/depth/etc. | same | `tuning_wall_seconds`, `fit_wall_seconds`, `time_per_estimator_seconds` | Often slower training; document quality vs cost. |
| candidate_distilbert | `http://...` | `<sha>` | HF: `pretrained_model_name`, `num_epochs`, `lr`, `batch_size`, `max_length` | same | `fit_wall_seconds`, `cost_avg_epoch_wall_seconds` | Heavier serve/train; neural text inductive bias. |
| **LLM** — SmolLM2 LoRA generator | `http://<FLOATING_IP>:5000/#/experiments/<LLM_EXP_ID>/runs/<RUN_ID>` | `<sha>` | `model.name`, LoRA `r`/`alpha`, `epochs`, `lr`, `batch`, `grad_accum`, `max_length` (see `llm_generator_small.yaml`) | `last_*` train/eval metrics from MLflow | `train_wall_seconds`, `cost_avg_epoch_wall_seconds`, `training_gpu_hours` | **Different task** (generation / rewrites); separate experiment **`teamchat_tone_generator_llm`** in MLflow. |

### Manager narrative (required in or below the table)

Write **3–6 sentences**:

1. Which run **maximizes** the metric you care about most (name it).
2. Which run is the **best speed/cost** at **acceptable** quality.
3. What you would run **next** (data, config, or search space).

### Hyperparameter tuning (justify in PDF)

- **Sklearn:** **Optuna** — `candidate_tone_logistic.yaml`, `candidate_tone_random_forest.yaml`.
- **DistilBERT:** YAML/manual hyperparameters (`train.py`); Optuna not used for this `model.type`.
- **LLM:** YAML-driven LoRA + SFT hyperparameters (`train_llm.py` + `llm_generator_small.yaml`); document search strategy if you add tuning later.

### How each row was produced (for your own audit)

**Tone classifier (every sklearn / DistilBERT row):**

```bash
export GIT_SHA=$(git rev-parse HEAD)
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
docker compose -f training/docker-compose.yml build tone-train
docker compose -f training/docker-compose.yml run --rm tone-train --config /app/configs/<config>.yaml
```

**LLM generator row:**

```bash
export GIT_SHA=$(git rev-parse HEAD)
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
docker compose -f training/docker-compose.yml build llm-train
docker compose -f training/docker-compose.yml run --rm llm-train --config /app/configs/llm_generator_small.yaml
```

Use **`127.0.0.1`** inside the container with **host networking**; **PDF links** for staff use **`http://<FLOATING_IP>:5000/...`**. LLM runs live under experiment **`teamchat_tone_generator_llm`** (experiment id may differ from `teamchat_tone_clf`).

---

## Q2.2 Repository artifacts (upload)

File lists and zip layouts: [`Q2_2_REPOSITORY_ARTIFACTS.md`](Q2_2_REPOSITORY_ARTIFACTS.md).

---

## Q2.3 Demo video (upload)

### Requirements

- **One complete** training run **in Docker on Chameleon** (sped-up OK).
- If training is long: **snippets** = beginning + middle + end, stitched into one short video.
- **Length:** a **few minutes** max (per rubric).

### Suggested shot list

1. **Start:** On Chameleon — `docker compose -f training/docker-compose.yml build tone-train` (and/or `build llm-train`) — can fast-forward.
2. **Run A (required for rubric “one complete run”):**  
   `docker compose -f training/docker-compose.yml run --rm tone-train --config /app/configs/<config>.yaml` — beginning → middle → end.
3. **Run B (recommended if LLM is part of your project):**  
   `docker compose ... run --rm llm-train --config /app/configs/llm_generator_small.yaml` — snippets if long.
4. **Browser:** MLflow — open **teamchat_tone_clf** and **teamchat_tone_generator_llm** runs; show **Parameters**, **Metrics**, **Artifacts**.

### One-sentence narration (example)

> “We build Docker images with `GIT_SHA`, run config-driven `train.py` and `train_llm.py` in containers on Chameleon, and verify both experiment types in MLflow.”

---

## Q2.4 Live MLflow service (URL in LMS)

### What to submit

- **Single browseable URL** for course staff, e.g.  
  `http://<YOUR_CHAMELEON_FLOATING_IP>:5000`  
  Use your Chameleon floating IP and port 5000 (see `DEPLOYMENT.md`).

### Checklist before you paste the link

- [ ] `mlflow server` is bound to **`0.0.0.0`** (not only `127.0.0.1`) if staff reach it from outside the VM.
- [ ] **Security group / firewall** allows **inbound TCP 5000** (or your chosen port).
- [ ] **Floating IP** is attached to the correct instance.
- [ ] Experiments list shows **all runs referenced in your Q2.1 PDF** — both **`teamchat_tone_clf`** (classifier) and **`teamchat_tone_generator_llm`** (LLM), if LLM rows are in the table (same backend store / DB).
- [ ] **Lease** on Chameleon keeps the instance (and MLflow) **up through the course deadline** (e.g. **Tuesday, April 7**, per your syllabus) and **presentation day** if applicable.

### If staff see “connection refused” or timeout

- Confirm server process is running (`ss -tlnp | grep 5000`).
- Confirm host binding and cloud firewall rules.
- Use **`http://`** not **`https://`** unless you terminated TLS yourself.

---

## Q3 Bonus — Ray Train (optional)

**Only if you attempt extra credit.**

- Submit a **PDF** explaining a **concrete** Ray Train integration that goes **beyond** “`ray submit` on an unmodified script.”
- Include **artifacts** (e.g. Dockerfile, Python) used on **Chameleon**.

If you did not do Ray integration, **leave Q3 empty** — it is optional.

---

## Pre-submission checklist (all of Q2)

- [ ] **Q2.1** PDF uploaded; **every** MLflow link clicked and works.
- [ ] **Q2.2** Dockerfiles + `train.py` + configs uploaded; matches what ran on Chameleon.
- [ ] **Q2.3** Video shows Docker on Chameleon + MLflow UI.
- [ ] **Q2.4** Live MLflow URL works for an external browser; runs visible.
- [ ] All table runs were **Docker on Chameleon**, not local-only.
- [ ] Baseline + multiple classifier candidates; **LLM** row if generator is in scope; **Optuna** documented for sklearn configs.

---

## Related files in this repository

| Document | Purpose |
|----------|---------|
| `training/Q2_1_TRAINING_RUNS_TABLE_FILLED.md` | Q2.1 table draft for PDF. |
| `training/DEPLOYMENT.md` | MLflow, network, Docker. |
| `README.md` | Project overview. |
