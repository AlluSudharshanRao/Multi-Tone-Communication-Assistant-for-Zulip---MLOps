#!/usr/bin/env python3
"""
Config-driven training for the tone classifier (serving contract in samples/classifier_*.json).

Inference contract:
  Input:  message fields including at least `text` (see samples/classifier_input.json).
  Output: predicted_tone + probabilities for formal | friendly | neutral (+ latency_ms added at serve time).

Data:
  - `dataset: tone_csv` — CSV with columns text,tone (tone must be one of data.label_classes).
    Point csv_path at your versioned labeled export on Chameleon for production training.
  - `dataset: twenty_newsgroups` — optional benchmark from sklearn (Ken Lang, CMU-CS-96-118).

Usage:
  python train.py --config configs/baseline_tone_nb.yaml

model.type:
  - multinomial_nb | logistic_regression | random_forest — sklearn Pipeline + TF-IDF
  - distilbert — Hugging Face Trainer (set optuna.enabled: false); logs HF weights under artifact path model/

Tracking: set MLFLOW_TRACKING_URI to your MLflow server (e.g. http://<host>:5000). On the same host as the server, http://127.0.0.1:5000 is typical.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import optuna
import yaml
from sklearn.datasets import fetch_20newsgroups
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    log_loss,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.environ.get("GIT_SHA", "unknown")


def _training_environment() -> dict[str, Any]:
    env: dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or "",
    }
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        env["gpu"] = out.strip().replace("\n", "; ")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        env["gpu"] = "none_detected"
    env["execution_context"] = "docker" if Path("/.dockerenv").exists() else "bare_metal_or_vm"
    return env


def _build_vectorizer(cfg: dict[str, Any]) -> TfidfVectorizer:
    t = cfg["tfidf"]
    return TfidfVectorizer(
        max_features=int(t["max_features"]),
        ngram_range=(int(t["ngram_min"]), int(t["ngram_max"])),
        min_df=int(t["min_df"]),
        sublinear_tf=True,
    )


def _build_classifier(model_cfg: dict[str, Any]) -> Any:
    mtype = model_cfg["type"]
    p = dict(model_cfg.get("params") or {})
    if mtype == "multinomial_nb":
        return MultinomialNB(**p)
    if mtype == "logistic_regression":
        return LogisticRegression(**p)
    if mtype == "random_forest":
        if p.get("max_depth") == "none" or p.get("max_depth") == "null":
            p["max_depth"] = None
        return RandomForestClassifier(**p)
    raise ValueError(f"Unknown model.type: {mtype}")


def _build_pipeline(cfg: dict[str, Any]) -> Pipeline:
    return Pipeline(
        [
            ("tfidf", _build_vectorizer(cfg)),
            ("clf", _build_classifier(cfg["model"])),
        ]
    )


def _load_twenty_newsgroups(cfg: dict[str, Any]) -> tuple[list[str], np.ndarray, list[str]]:
    d = cfg["data"]
    cats = d.get("categories")
    remove = ("headers", "footers", "quotes")
    bunch = fetch_20newsgroups(
        subset="all",
        categories=cats,
        remove=remove,
        shuffle=True,
        random_state=int(d["random_seed"]),
    )
    texts = bunch.data
    y = np.asarray(bunch.target, dtype=np.int64)
    return texts, y, list(bunch.target_names)


def _load_tone_csv(cfg: dict[str, Any]) -> tuple[list[str], np.ndarray, list[str]]:
    d = cfg["data"]
    label_classes = list(d["label_classes"])
    label_to_idx = {name: i for i, name in enumerate(label_classes)}
    raw_path = Path(d["csv_path"])
    path = raw_path if raw_path.is_absolute() else Path(__file__).resolve().parent / raw_path
    texts: list[str] = []
    ys: list[int] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "text" not in reader.fieldnames or "tone" not in reader.fieldnames:
            raise ValueError("tone_csv requires CSV headers including 'text' and 'tone'")
        for row in reader:
            t = (row.get("text") or "").strip()
            tone = (row.get("tone") or "").strip()
            if not t:
                continue
            if tone not in label_to_idx:
                raise ValueError(f"Unknown tone {tone!r}; expected one of {label_classes}")
            texts.append(t)
            ys.append(label_to_idx[tone])
    if len(texts) < 6:
        raise ValueError("tone_csv needs more rows for a stable train/val/test split")
    return texts, np.asarray(ys, dtype=np.int64), label_classes


def _load_dataset(cfg: dict[str, Any]) -> tuple[list[str], np.ndarray, list[str]]:
    kind = cfg["data"].get("dataset", "tone_csv")
    if kind == "twenty_newsgroups":
        return _load_twenty_newsgroups(cfg)
    if kind == "tone_csv":
        return _load_tone_csv(cfg)
    raise ValueError(f"Unknown data.dataset: {kind}")


def _lineage_record(cfg: dict[str, Any], class_names: list[str]) -> dict[str, Any]:
    d = cfg["data"]
    kind = d.get("dataset", "tone_csv")
    if kind == "tone_csv":
        raw_path = Path(d["csv_path"])
        path = raw_path if raw_path.is_absolute() else Path(__file__).resolve().parent / raw_path
        return {
            "dataset_kind": "tone_csv",
            "csv_path": str(path),
            "label_classes": class_names,
            "lineage_note": (
                "Replace tone_seed.csv with your team's versioned, labeled export (object store) "
                "and document collector, time range, and labeling process for the course data requirement."
            ),
        }
    return {
        "dataset_kind": "twenty_newsgroups",
        "reference": "Lang, K. (1995). NewsWeeder: Learning to filter netnews. CMU-CS-96-118.",
        "sklearn_loader": "sklearn.datasets.fetch_20newsgroups",
        "categories_used": d.get("categories"),
        "preprocessing": "headers/footers/quotes removed by sklearn loader",
    }


def _evaluate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_proba: np.ndarray | None,
    class_names: list[str],
) -> dict[str, float]:
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    metrics: dict[str, float] = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1),
        "precision_macro": float(prec),
        "recall_macro": float(rec),
    }
    labels = np.arange(len(class_names), dtype=np.int64)
    prec_c, rec_c, f1_c, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average=None, zero_division=0
    )
    for i, name in enumerate(class_names):
        metrics[f"f1_{name}"] = float(f1_c[i])
        metrics[f"precision_{name}"] = float(prec_c[i])
        metrics[f"recall_{name}"] = float(rec_c[i])
    if y_proba is not None:
        try:
            metrics["log_loss"] = float(log_loss(y_true, y_proba, labels=labels))
        except ValueError:
            pass
    return metrics


def _metric_from_val(metric_name: str, metrics: dict[str, float]) -> float:
    if metric_name not in metrics:
        raise KeyError(metric_name)
    return metrics[metric_name]


def _apply_cfg_updates(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    c = copy.deepcopy(base)
    for path, val in updates.items():
        parts = path.split(".")
        cur: Any = c
        for p in parts[:-1]:
            cur = cur[p]
        cur[parts[-1]] = val
    return c


def _suggest_from_search_space(trial: optuna.Trial, space: dict[str, Any]) -> dict[str, Any]:
    """Map Optuna suggestions to dotted-path updates for the training config."""
    updates: dict[str, Any] = {}
    if "C" in space:
        s = space["C"]
        updates["model.params.C"] = trial.suggest_float(
            "C", float(s["low"]), float(s["high"]), log=bool(s.get("log", False))
        )
    if "tfidf_max_features" in space:
        updates["tfidf.max_features"] = trial.suggest_categorical(
            "tfidf_max_features", [int(x) for x in space["tfidf_max_features"]["choices"]]
        )
    if "ngram_max" in space:
        updates["tfidf.ngram_max"] = trial.suggest_categorical(
            "ngram_max", [int(x) for x in space["ngram_max"]["choices"]]
        )
    if "n_estimators" in space:
        s = space["n_estimators"]
        updates["model.params.n_estimators"] = trial.suggest_int(
            "n_estimators", int(s["low"]), int(s["high"])
        )
    if "max_depth" in space:
        choices = list(space["max_depth"]["choices"])
        raw = trial.suggest_categorical("max_depth", choices)
        updates["model.params.max_depth"] = None if raw in (None, "none", "null") else int(raw)
    if "min_samples_leaf" in space:
        s = space["min_samples_leaf"]
        updates["model.params.min_samples_leaf"] = trial.suggest_int(
            "min_samples_leaf", int(s["low"]), int(s["high"])
        )
    return updates


def _best_params_to_updates(best_params: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for k, v in best_params.items():
        if k == "C":
            updates["model.params.C"] = v
        elif k == "tfidf_max_features":
            updates["tfidf.max_features"] = int(v)
        elif k == "ngram_max":
            updates["tfidf.ngram_max"] = int(v)
        elif k == "n_estimators":
            updates["model.params.n_estimators"] = int(v)
        elif k == "max_depth":
            updates["model.params.max_depth"] = None if v in (None, "none", "null") else int(v)
        elif k == "min_samples_leaf":
            updates["model.params.min_samples_leaf"] = int(v)
    return updates


def _run_optuna(
    cfg: dict[str, Any],
    X_train: list[str],
    X_val: list[str],
    y_train: np.ndarray,
    y_val: np.ndarray,
    class_names: list[str],
) -> tuple[dict[str, Any], optuna.Study]:
    oc = cfg["optuna"]
    metric = oc.get("metric", "f1_macro")
    n_trials = int(oc["n_trials"])
    space = oc["search_space"]

    def objective(trial: optuna.Trial) -> float:
        trial_cfg = _apply_cfg_updates(cfg, _suggest_from_search_space(trial, space))
        pipe = _build_pipeline(trial_cfg)
        t0 = time.perf_counter()
        pipe.fit(X_train, y_train)
        fit_s = time.perf_counter() - t0
        y_pred = pipe.predict(X_val)
        y_proba = None
        if hasattr(pipe.named_steps["clf"], "predict_proba"):
            y_proba = pipe.predict_proba(X_val)
        m = _evaluate(y_val, y_pred, y_proba, class_names)
        trial.set_user_attr("val_fit_seconds", fit_s)
        return _metric_from_val(metric, m)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=int(cfg["data"]["random_seed"])),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return _best_params_to_updates(study.best_params), study


def _train_distilbert(
    cfg: dict[str, Any],
    X_train: list[str],
    X_val: list[str],
    X_test: list[str],
    y_train: np.ndarray,
    y_val: np.ndarray,
    y_test: np.ndarray,
    class_names: list[str],
    env_info: dict[str, Any],
    git_sha: str,
    config_path: Path | None,
) -> None:
    if cfg.get("optuna", {}).get("enabled"):
        raise ValueError("Optuna is not supported for model.type distilbert; set optuna.enabled: false.")

    import shutil

    import torch
    from datasets import Dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    d = cfg["data"]
    seed = int(d["random_seed"])
    mp = dict(cfg["model"].get("params") or {})
    model_name = str(mp.get("pretrained_model_name", "distilbert-base-uncased"))
    max_length = int(mp.get("max_length", 128))
    num_epochs = float(mp.get("num_epochs", 3.0))
    batch_size = int(mp.get("batch_size", 8))
    learning_rate = float(mp.get("learning_rate", 5e-5))
    weight_decay = float(mp.get("weight_decay", 0.01))

    id2label = {i: n for i, n in enumerate(class_names)}
    label2id = {n: i for i, n in enumerate(class_names)}

    print(f"[distilbert] Loading tokenizer: {model_name}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def make_hf_dataset(texts: list[str], labels: np.ndarray) -> Dataset:
        ds = Dataset.from_dict({"text": texts, "label": labels.tolist()})

        def tokenize_fn(examples: dict[str, list]) -> dict[str, list]:
            enc = tokenizer(
                examples["text"],
                truncation=True,
                max_length=max_length,
                padding="max_length",
            )
            enc["labels"] = examples["label"]
            return enc

        return ds.map(tokenize_fn, batched=True, remove_columns=["text"])

    print("[distilbert] Tokenizing train/val/test...", flush=True)
    ds_train = make_hf_dataset(X_train, y_train)
    ds_val = make_hf_dataset(X_val, y_val)
    ds_test = make_hf_dataset(X_test, y_test)

    torch.manual_seed(seed)
    print("[distilbert] Loading model weights (may download on first run)...", flush=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(class_names),
        id2label=id2label,
        label2id=label2id,
    )

    train_out = Path("./hf_training_out")
    train_out.mkdir(parents=True, exist_ok=True)
    eval_strategy = "epoch" if len(ds_val) > 0 else "no"
    ta_kwargs: dict[str, Any] = {
        "output_dir": str(train_out),
        "num_train_epochs": num_epochs,
        "per_device_train_batch_size": batch_size,
        "per_device_eval_batch_size": batch_size,
        "learning_rate": learning_rate,
        "weight_decay": weight_decay,
        "save_strategy": "no",
        "logging_strategy": "epoch",
        "report_to": [],
        "seed": seed,
        "disable_tqdm": False,
    }
    try:
        training_args = TrainingArguments(eval_strategy=eval_strategy, **ta_kwargs)
    except TypeError:
        training_args = TrainingArguments(evaluation_strategy=eval_strategy, **ta_kwargs)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ds_train,
        eval_dataset=ds_val if len(ds_val) > 0 else None,
    )

    print("[distilbert] Opening MLflow run...", flush=True)
    with mlflow.start_run(run_name=cfg.get("run_name")):
        if config_path is not None:
            mlflow.set_tag("training.config_path", str(config_path))
        mlflow.set_tag("hyperparameter_tuning", "none")
        mlflow.set_tag("dataset", d.get("dataset", "tone_csv"))
        mlflow.set_tag("label_classes", ",".join(class_names))
        mlflow.set_tag("features", "distilbert_hf")
        if d.get("dataset", "tone_csv") == "tone_csv":
            mlflow.set_tag(
                "dataset_lineage",
                "Labeled CSV (text,tone); document production source in dataset_lineage.json",
            )
        else:
            mlflow.set_tag("dataset_lineage", "Ken Lang CMU NewsWeeder; sklearn.datasets.fetch_20newsgroups")
        mlflow.set_tag("code_version_git_sha", git_sha)
        if cfg.get("description"):
            mlflow.set_tag("mlflow.note.content", str(cfg["description"])[:1000])
        mlflow.log_dict(env_info, "training_environment.json")
        mlflow.log_params(
            {
                "data.test_size": d["test_size"],
                "data.random_seed": seed,
                "model.type": cfg["model"]["type"],
                "env.gpu": env_info.get("gpu", ""),
                "env.python": env_info["python_version"],
                "features.note": "TF-IDF block in YAML is unused for distilbert; tokenizer from HF",
            }
        )
        mlflow.log_params({f"model.params.{k}": ("null" if v is None else v) for k, v in mp.items()})

        print("[distilbert] Starting Trainer (CPU can take ~1-2 min for 3 epochs on seed data)...", flush=True)
        t0 = time.perf_counter()
        trainer.train()
        fit_wall = time.perf_counter() - t0

        pred_out = trainer.predict(ds_test)
        logits = pred_out.predictions
        if logits.ndim > 2:
            logits = logits.squeeze(-1)
        exp_l = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        y_proba = exp_l / np.sum(exp_l, axis=1, keepdims=True)
        y_pred = np.argmax(logits, axis=1).astype(np.int64)

        metrics = _evaluate(y_test, y_pred, y_proba, class_names)
        n_train = len(X_train)
        mlflow.log_metrics(metrics)
        mlflow.log_metrics(
            {
                "train_n_samples": float(n_train),
                "test_n_samples": float(len(X_test)),
                "fit_wall_seconds": fit_wall,
                "fit_samples_per_second": n_train / max(fit_wall, 1e-9),
            }
        )
        if num_epochs > 0:
            mlflow.log_metric("cost_avg_epoch_wall_seconds", fit_wall / float(num_epochs))
        # Wall-clock GPU-hours not instrumented; 0.0 on CPU nodes. See training_environment.json for GPU probe.
        mlflow.log_metric("training_gpu_hours", 0.0)

        bundle = Path("./hf_model_bundle")
        if bundle.exists():
            shutil.rmtree(bundle, ignore_errors=True)
        bundle.mkdir(parents=True, exist_ok=True)
        trainer.model.save_pretrained(bundle)
        tokenizer.save_pretrained(bundle)
        print("[distilbert] Uploading model artifacts to MLflow...", flush=True)
        mlflow.log_artifacts(str(bundle), artifact_path="model")
        mlflow.log_dict(
            {
                "format": "huggingface",
                "load_with": "AutoModelForSequenceClassification.from_pretrained + AutoTokenizer",
                "pretrained_model_name": model_name,
                "label_classes": class_names,
            },
            "model/serving_hint.json",
        )

        lineage_path = Path("dataset_lineage.json")
        lineage_path.write_text(
            json.dumps(_lineage_record(cfg, class_names), indent=2),
            encoding="utf-8",
        )
        mlflow.log_artifact(str(lineage_path))
        lineage_path.unlink(missing_ok=True)

        shutil.rmtree(bundle, ignore_errors=True)
        shutil.rmtree(train_out, ignore_errors=True)


def train(cfg: dict[str, Any], config_path: Path | None = None) -> None:
    d = cfg["data"]
    seed = int(d["random_seed"])

    texts, y, class_names = _load_dataset(cfg)
    X_train, X_test, y_train, y_test = train_test_split(
        texts,
        y,
        test_size=float(d["test_size"]),
        random_state=seed,
        stratify=y,
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train,
        y_train,
        test_size=0.15,
        random_state=seed,
        stratify=y_train,
    )

    mlflow.set_experiment(cfg.get("experiment_name", "default"))
    env_info = _training_environment()
    git_sha = _git_sha()

    if cfg["model"]["type"] == "distilbert":
        _train_distilbert(
            cfg,
            X_train,
            X_val,
            X_test,
            y_train,
            y_val,
            y_test,
            class_names,
            env_info,
            git_sha,
            config_path,
        )
        return

    with mlflow.start_run(run_name=cfg.get("run_name")):
        if config_path is not None:
            mlflow.set_tag("training.config_path", str(config_path))
        tuning = "optuna" if cfg.get("optuna", {}).get("enabled") else "none"
        mlflow.set_tag("hyperparameter_tuning", tuning)
        mlflow.set_tag("dataset", d.get("dataset", "tone_csv"))
        mlflow.set_tag("label_classes", ",".join(class_names))
        if d.get("dataset", "tone_csv") == "tone_csv":
            mlflow.set_tag(
                "dataset_lineage",
                "Labeled CSV (text,tone); document production source in dataset_lineage.json",
            )
        else:
            mlflow.set_tag("dataset_lineage", "Ken Lang CMU NewsWeeder; sklearn.datasets.fetch_20newsgroups")
        mlflow.set_tag("code_version_git_sha", git_sha)
        if cfg.get("description"):
            mlflow.set_tag("mlflow.note.content", str(cfg["description"])[:1000])
        mlflow.log_dict(env_info, "training_environment.json")
        mlflow.log_params(
            {
                "data.test_size": d["test_size"],
                "data.random_seed": seed,
                "model.type": cfg["model"]["type"],
                "env.gpu": env_info.get("gpu", ""),
                "env.python": env_info["python_version"],
            }
        )
        mlflow.log_params({f"tfidf.{k}": v for k, v in cfg["tfidf"].items()})
        flat_model_params = {
            f"model.params.{k}": ("null" if v is None else v)
            for k, v in (cfg["model"].get("params") or {}).items()
        }
        mlflow.log_params(flat_model_params)

        final_cfg = cfg
        study = None
        if cfg.get("optuna", {}).get("enabled"):
            t_tune0 = time.perf_counter()
            with mlflow.start_run(run_name="optuna_tuning", nested=True):
                best_updates, study = _run_optuna(cfg, X_train, X_val, y_train, y_val, class_names)
                final_cfg = copy.deepcopy(cfg)
                for path, val in best_updates.items():
                    parts = path.split(".")
                    cur: Any = final_cfg
                    for p in parts[:-1]:
                        cur = cur[p]
                    cur[parts[-1]] = val
                mlflow.log_metric("optuna_best_value", study.best_value)
                mlflow.log_metric("optuna_n_trials", len(study.trials))
                mlflow.log_params({f"best.{k}": v for k, v in study.best_params.items()})
            mlflow.log_metric("tuning_wall_seconds", time.perf_counter() - t_tune0)

        mlflow.log_params({f"effective.tfidf.{k}": v for k, v in final_cfg["tfidf"].items()})
        mlflow.log_params(
            {
                f"effective.model.params.{k}": ("null" if v is None else v)
                for k, v in (final_cfg["model"].get("params") or {}).items()
            }
        )

        pipe = _build_pipeline(final_cfg)
        t0 = time.perf_counter()
        pipe.fit(X_train, y_train)
        fit_wall = time.perf_counter() - t0

        y_pred = pipe.predict(X_test)
        y_proba = None
        if hasattr(pipe.named_steps["clf"], "predict_proba"):
            y_proba = pipe.predict_proba(X_test)
        metrics = _evaluate(y_test, y_pred, y_proba, class_names)

        n_train = len(X_train)
        mlflow.log_metrics(metrics)
        mlflow.log_metrics(
            {
                "train_n_samples": float(n_train),
                "test_n_samples": float(len(X_test)),
                "fit_wall_seconds": fit_wall,
                "fit_samples_per_second": n_train / max(fit_wall, 1e-9),
            }
        )

        # Approximate "epoch" cost for iterative models
        clf = pipe.named_steps["clf"]
        if isinstance(clf, LogisticRegression) and hasattr(clf, "n_iter_"):
            niter = np.max(clf.n_iter_) if hasattr(clf.n_iter_, "__len__") else clf.n_iter_
            mlflow.log_metric("solver_iterations_max", float(niter))
            mlflow.log_metric("time_per_solver_iter_seconds", fit_wall / max(float(niter), 1.0))
        if isinstance(clf, RandomForestClassifier):
            ne = int(clf.n_estimators)
            mlflow.log_metric("time_per_estimator_seconds", fit_wall / max(float(ne), 1.0))

        mlflow.log_metric("training_gpu_hours", 0.0)

        # Avoid mlflow.sklearn.log_model → Model.log → logged-models REST API, which older
        # tracking servers (or mismatched client/server) reject with 404. DistilBERT path
        # already uses log_artifacts; same artifact layout for sklearn flavor.
        with tempfile.TemporaryDirectory() as model_dir:
            mlflow.sklearn.save_model(sk_model=pipe, path=model_dir)
            mlflow.log_artifacts(model_dir, artifact_path="model")

        lineage_path = Path("dataset_lineage.json")
        lineage_path.write_text(
            json.dumps(_lineage_record(cfg, class_names), indent=2),
            encoding="utf-8",
        )
        mlflow.log_artifact(str(lineage_path))
        lineage_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train text classifier with MLflow tracking.")
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to YAML training config (mount in container under /app/configs/...).",
    )
    args = parser.parse_args()
    cfg = _load_config(args.config)
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        mlflow.set_tracking_uri(uri)
    train(cfg, config_path=args.config)


if __name__ == "__main__":
    main()
