#!/usr/bin/env python3
"""
Fine-tune a very small instruct LM on CPU (LoRA) for tone rewriting — generator side.

Produces formal / friendly / neutral variants (see samples/generator_output.json).
Separate from train.py (sklearn tone classifier).

Usage:
  pip install -r requirements-llm.txt
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  python train_llm.py --config configs/llm_generator_small.yaml

Remote tracking:
  export MLFLOW_TRACKING_URI=http://<host>:5000
  docker build -f Dockerfile.llm -t llm-train:proj15 ./training
"""

from __future__ import annotations

import argparse
import collections
import difflib
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import mlflow
import torch
import yaml
from datasets import Dataset
from dataset_contract import (
    load_dataset_manifest,
    manifest_lineage,
    resolve_manifest_artifact,
    resolve_path,
)
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


def _load_config(path: Path) -> dict[str, Any]:
    def expand(value: Any) -> Any:
        if isinstance(value, str):
            return re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), ""), value)
        if isinstance(value, list):
            return [expand(v) for v in value]
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value

    with path.open("r", encoding="utf-8") as f:
        return expand(yaml.safe_load(f))


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
        "torch_version": torch.__version__,
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


def _build_supervised_text(
    tokenizer: Any,
    *,
    system: str,
    user_content: str,
    assistant_content: str,
) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content},
    ]
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
    eos = tokenizer.eos_token or "</s>"
    return f"<<SYS>>\n{system}\n<</SYS>>\n\n{user_content}\n{assistant_content}{eos}"

def _load_generator_examples(cfg: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]] | None, dict[str, Any]]:
    base = Path(__file__).resolve().parent
    d = cfg["data"]
    tones: list[str] = list(cfg["prompt"]["tones"])
    manifest_bundle = load_dataset_manifest(base, d)
    artifact = resolve_manifest_artifact(
        manifest_bundle,
        artifact_name=str(d.get("dataset_manifest_role", "generator_rewrites")),
        required_fields=("train_path",),
    )

    if artifact is not None:
        train_path = resolve_path(base, str(artifact["train_path"]))
        eval_raw = artifact.get("eval_path")
        eval_path = resolve_path(base, str(eval_raw)) if eval_raw else None
        manifest_tones = artifact.get("tones")
        if manifest_tones and list(manifest_tones) != tones:
            raise ValueError("dataset manifest tones do not match config prompt.tones")
        lineage = {
            "dataset_kind": "generator_manifest",
            "train_data": str(train_path),
            "eval_data": str(eval_path) if eval_path else None,
            "tones": tones,
            **manifest_lineage(
                manifest_bundle,
                str(d.get("dataset_manifest_role", "generator_rewrites")),
            ),
        }
    else:
        train_path = resolve_path(base, str(d["train_path"]))
        eval_raw = d.get("eval_path")
        eval_path = resolve_path(base, str(eval_raw)) if eval_raw else None
        lineage = {
            "dataset_kind": "generator_jsonl",
            "train_data": str(train_path),
            "eval_data": str(eval_path) if eval_path else None,
            "tones": tones,
            "note": "Replace with your curated, versioned rewrite dataset and document lineage for grading.",
        }

    def load_rows(path: Path) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if "original_text" not in obj:
                    raise KeyError("Generator JSONL rows must contain original_text")
                for tone in tones:
                    if tone not in obj:
                        raise KeyError(f"Missing key {tone!r} in JSONL row")
                rows.append({"original_text": obj["original_text"], **{tone: obj[tone] for tone in tones}})
        return rows

    train_examples = load_rows(train_path)
    eval_examples = load_rows(eval_path) if eval_path is not None else None
    if d.get("max_samples"):
        max_samples = int(d["max_samples"])
        train_examples = train_examples[:max_samples]
        if eval_examples is not None:
            eval_examples = eval_examples[:max_samples]
    if len(train_examples) < 2:
        raise ValueError("Need at least 2 generator training examples")
    return train_examples, eval_examples, lineage


def _examples_to_rows(cfg: dict[str, Any], tokenizer: Any, examples: list[dict[str, str]]) -> list[dict[str, str]]:
    tones: list[str] = list(cfg["prompt"]["tones"])
    system = str(cfg["prompt"]["system"])
    user_tmpl = str(cfg["prompt"]["user_template"])
    rows: list[dict[str, str]] = []
    for obj in examples:
        orig = obj["original_text"]
        for tone in tones:
            user = user_tmpl.format(tone=tone, original=orig)
            text = _build_supervised_text(
                tokenizer,
                system=system,
                user_content=user,
                assistant_content=obj[tone],
            )
            rows.append({"text": text})
    return rows


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _tokenize(text: str) -> list[str]:
    return [tok for tok in _normalize_text(text).replace("\n", " ").split(" ") if tok]


def _token_f1(reference: str, prediction: str) -> float:
    ref_counts = collections.Counter(_tokenize(reference))
    pred_counts = collections.Counter(_tokenize(prediction))
    overlap = sum((ref_counts & pred_counts).values())
    ref_total = sum(ref_counts.values())
    pred_total = sum(pred_counts.values())
    if ref_total == 0 or pred_total == 0 or overlap == 0:
        return 0.0
    precision = overlap / pred_total
    recall = overlap / ref_total
    return 2 * precision * recall / (precision + recall)


def _rouge_l_f1(reference: str, prediction: str) -> float:
    ref_tokens = _tokenize(reference)
    pred_tokens = _tokenize(prediction)
    if not ref_tokens or not pred_tokens:
        return 0.0
    m = len(ref_tokens)
    n = len(pred_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_tokens[i - 1] == pred_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[m][n]
    precision = lcs / n
    recall = lcs / m
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _build_generation_prompt(tokenizer: Any, cfg: dict[str, Any], tone: str, original_text: str) -> str:
    user_content = str(cfg["prompt"]["user_template"]).format(tone=tone, original=original_text)
    messages = [
        {"role": "system", "content": str(cfg["prompt"]["system"])},
        {"role": "user", "content": user_content},
    ]
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return f"<<SYS>>\n{cfg['prompt']['system']}\n<</SYS>>\n\n{user_content}\n"


def _generate_rewrite(
    model: Any,
    tokenizer: Any,
    cfg: dict[str, Any],
    *,
    tone: str,
    original_text: str,
) -> str:
    prompt = _build_generation_prompt(tokenizer, cfg, tone, original_text)
    device = next(model.parameters()).device
    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=int(cfg["training"]["max_length"]),
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    prompt_len = inputs["input_ids"].shape[1]
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=int(cfg["training"].get("eval_max_new_tokens", 96)),
            do_sample=False,
            num_beams=1,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    gen_ids = output_ids[0, prompt_len:]
    return tokenizer.decode(gen_ids, skip_special_tokens=True).strip()


def _evaluate_generator(
    model: Any,
    tokenizer: Any,
    cfg: dict[str, Any],
    eval_examples: list[dict[str, str]],
) -> dict[str, float]:
    tones: list[str] = list(cfg["prompt"]["tones"])
    total = 0
    non_empty = 0
    exact = 0
    copied = 0
    token_f1_total = 0.0
    rouge_total = 0.0
    source_similarity_total = 0.0

    for example in eval_examples:
        original = example["original_text"]
        norm_original = _normalize_text(original)
        for tone in tones:
            prediction = _generate_rewrite(model, tokenizer, cfg, tone=tone, original_text=original)
            reference = example[tone]
            total += 1
            if prediction.strip():
                non_empty += 1
            norm_pred = _normalize_text(prediction)
            if norm_pred == _normalize_text(reference):
                exact += 1
            if norm_pred == norm_original:
                copied += 1
            token_f1_total += _token_f1(reference, prediction)
            rouge_total += _rouge_l_f1(reference, prediction)
            source_similarity_total += difflib.SequenceMatcher(
                None, norm_original, norm_pred
            ).ratio()

    if total == 0:
        return {}
    return {
        "generator_eval.samples": float(total),
        "generator_eval.non_empty_rate": non_empty / total,
        "generator_eval.exact_match_rate": exact / total,
        "generator_eval.copy_rate": copied / total,
        "generator_eval.avg_reference_token_f1": token_f1_total / total,
        "generator_eval.avg_reference_rouge_l_f1": rouge_total / total,
        "generator_eval.avg_source_similarity": source_similarity_total / total,
    }


def _pick_kwargs(callable_obj: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    params = set(inspect.signature(callable_obj.__init__).parameters) - {"self"}
    return {k: v for k, v in kwargs.items() if k in params}


def train(cfg: dict[str, Any], config_path: Path | None = None) -> None:
    base = Path(__file__).resolve().parent
    mcfg = cfg["model"]
    tcfg = cfg["training"]
    lcfg = cfg["lora"]

    model_name = mcfg["name"]
    dtype_name = str(mcfg.get("torch_dtype", "float32")).lower()
    dtype = {"float32": torch.float32, "bfloat16": torch.bfloat16, "float16": torch.float16}.get(
        dtype_name, torch.float32
    )

    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=bool(mcfg.get("trust_remote_code", False)),
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_examples, explicit_eval_examples, dataset_lineage = _load_generator_examples(cfg)
    vf = float(cfg["data"].get("val_fraction", 0.0))
    if explicit_eval_examples is not None:
        model_train_examples = train_examples
        model_eval_examples = explicit_eval_examples
    elif vf > 0:
        ds_full = Dataset.from_list(train_examples)
        split = ds_full.train_test_split(test_size=vf, seed=int(cfg["data"]["random_seed"]))
        model_train_examples = list(split["train"])
        model_eval_examples = list(split["test"])
    else:
        model_train_examples = train_examples
        model_eval_examples = None

    train_ds = Dataset.from_list(_examples_to_rows(cfg, tokenizer, model_train_examples))
    eval_ds = (
        Dataset.from_list(_examples_to_rows(cfg, tokenizer, model_eval_examples))
        if model_eval_examples
        else None
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=dtype,
        trust_remote_code=bool(mcfg.get("trust_remote_code", False)),
        low_cpu_mem_usage=True,
    )

    peft_config = LoraConfig(
        r=int(lcfg["r"]),
        lora_alpha=int(lcfg["alpha"]),
        lora_dropout=float(lcfg["dropout"]),
        target_modules=list(lcfg["target_modules"]),
        task_type=TaskType.CAUSAL_LM,
        bias="none",
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    out_dir = resolve_path(base, str(tcfg["output_dir"]))
    out_dir.mkdir(parents=True, exist_ok=True)

    max_len = int(tcfg["max_length"])
    sft_kwargs: dict[str, Any] = {
        "output_dir": str(out_dir),
        "num_train_epochs": float(tcfg["num_train_epochs"]),
        "per_device_train_batch_size": int(tcfg["per_device_train_batch_size"]),
        "gradient_accumulation_steps": int(tcfg["gradient_accumulation_steps"]),
        "learning_rate": float(tcfg["learning_rate"]),
        "warmup_ratio": float(tcfg["warmup_ratio"]),
        "logging_steps": int(tcfg["logging_steps"]),
        "save_steps": int(tcfg["save_steps"]),
        "save_total_limit": int(tcfg["save_total_limit"]),
        "no_cuda": True,
        "fp16": False,
        "bf16": False,
        "gradient_checkpointing": False,
        "dataloader_pin_memory": False,
        "report_to": [],
        "dataset_text_field": "text",
        "max_length": max_len,
        "packing": False,
    }
    sig_sft = inspect.signature(SFTConfig.__init__).parameters
    if eval_ds is not None:
        if "eval_strategy" in sig_sft:
            sft_kwargs["eval_strategy"] = "steps"
        elif "evaluation_strategy" in sig_sft:
            sft_kwargs["evaluation_strategy"] = "steps"
        sft_kwargs["eval_steps"] = max(1, int(tcfg["save_steps"]))
    else:
        if "eval_strategy" in sig_sft:
            sft_kwargs["eval_strategy"] = "no"
        elif "evaluation_strategy" in sig_sft:
            sft_kwargs["evaluation_strategy"] = "no"

    training_args = SFTConfig(**_pick_kwargs(SFTConfig, sft_kwargs))

    trainer_kw: dict[str, Any] = {
        "model": model,
        "args": training_args,
        "train_dataset": train_ds,
    }
    if eval_ds is not None:
        trainer_kw["eval_dataset"] = eval_ds
    sig_tr = inspect.signature(SFTTrainer.__init__).parameters
    if "processing_class" in sig_tr:
        trainer_kw["processing_class"] = tokenizer
    elif "tokenizer" in sig_tr:
        trainer_kw["tokenizer"] = tokenizer

    trainer = SFTTrainer(**_pick_kwargs(SFTTrainer, trainer_kw))

    mlflow.set_experiment(cfg.get("experiment_name", "llm_generator"))
    env_info = _training_environment()
    git_sha = _git_sha()
    t0 = time.perf_counter()

    with mlflow.start_run(run_name=cfg.get("run_name")):
        if config_path is not None:
            mlflow.set_tag("training.config_path", str(config_path))
        mlflow.set_tag("hyperparameter_tuning", "none")
        mlflow.set_tag("script", "train_llm.py")
        mlflow.set_tag("base_model", model_name)
        mlflow.set_tag("code_version_git_sha", git_sha)
        mlflow.set_tag("dataset_lineage", "Generator rewrite dataset; source details stored in llm_dataset_lineage.json")
        if dataset_lineage.get("dataset_manifest_version"):
            mlflow.set_tag("dataset_manifest_version", str(dataset_lineage["dataset_manifest_version"]))
        if cfg.get("description"):
            mlflow.set_tag("mlflow.note.content", str(cfg["description"])[:1000])
        mlflow.log_dict(env_info, "llm_training_environment.json")
        mlflow.log_params(
            {
                "model.name": model_name,
                "lora.r": lcfg["r"],
                "lora.alpha": lcfg["alpha"],
                "train_rows": len(train_ds),
                "val_rows": len(eval_ds) if eval_ds is not None else 0,
                "train_examples": len(model_train_examples),
                "eval_examples": len(model_eval_examples) if model_eval_examples is not None else 0,
                "max_length": max_len,
                "epochs": tcfg["num_train_epochs"],
                "lr": tcfg["learning_rate"],
                "batch": tcfg["per_device_train_batch_size"],
                "grad_accum": tcfg["gradient_accumulation_steps"],
            }
        )
        mlflow.log_param("lora.target_modules", ",".join(lcfg["target_modules"]))

        trainer.train()
        train_wall = time.perf_counter() - t0
        mlflow.log_metric("train_wall_seconds", train_wall)
        ne = float(tcfg["num_train_epochs"])
        if ne > 0:
            mlflow.log_metric("cost_avg_epoch_wall_seconds", train_wall / ne)
        mlflow.log_metric("training_gpu_hours", 0.0)

        if trainer.state.log_history:
            last = trainer.state.log_history[-1]
            for k, v in last.items():
                if isinstance(v, (int, float)) and k not in ("epoch",):
                    mlflow.log_metric(f"last_{k}", float(v))

        if model_eval_examples:
            gen_metrics = _evaluate_generator(trainer.model, tokenizer, cfg, model_eval_examples)
            if gen_metrics:
                mlflow.log_metrics(gen_metrics)

        trainer.save_model(str(out_dir))
        tokenizer.save_pretrained(str(out_dir))
        mlflow.log_artifacts(str(out_dir), artifact_path="lora_checkpoint")

        p = Path("llm_dataset_lineage.json")
        p.write_text(json.dumps(dataset_lineage, indent=2), encoding="utf-8")
        mlflow.log_artifact(str(p))
        p.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA fine-tune small LLM on CPU for tone rewriting.")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    cfg = _load_config(args.config)
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        mlflow.set_tracking_uri(uri)
    train(cfg, config_path=args.config)


if __name__ == "__main__":
    main()
