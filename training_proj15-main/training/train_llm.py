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
import inspect
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import mlflow
import torch
import yaml
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


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


def _resolve_path(base: Path, p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (base / pp)


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


def _jsonl_to_rows(cfg: dict[str, Any], tokenizer: Any) -> list[dict[str, str]]:
    base = Path(__file__).resolve().parent
    d = cfg["data"]
    path = _resolve_path(base, d["train_path"])
    tones: list[str] = list(cfg["prompt"]["tones"])
    system = str(cfg["prompt"]["system"])
    user_tmpl = str(cfg["prompt"]["user_template"])

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            orig = obj["original_text"]
            for tone in tones:
                if tone not in obj:
                    raise KeyError(f"Missing key {tone!r} in JSONL row")
                user = user_tmpl.format(tone=tone, original=orig)
                text = _build_supervised_text(
                    tokenizer,
                    system=system,
                    user_content=user,
                    assistant_content=obj[tone],
                )
                rows.append({"text": text})
    if d.get("max_samples"):
        rows = rows[: int(d["max_samples"])]
    if len(rows) < 2:
        raise ValueError("Need at least 2 training rows after expansion")
    return rows


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

    rows = _jsonl_to_rows(cfg, tokenizer)
    ds_full = Dataset.from_list(rows)
    vf = float(cfg["data"].get("val_fraction", 0.0))
    if vf > 0:
        split = ds_full.train_test_split(test_size=vf, seed=int(cfg["data"]["random_seed"]))
        train_ds = split["train"]
        eval_ds = split["test"]
    else:
        train_ds = ds_full
        eval_ds = None

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

    out_dir = _resolve_path(base, tcfg["output_dir"])
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

        trainer.save_model(str(out_dir))
        tokenizer.save_pretrained(str(out_dir))
        mlflow.log_artifacts(str(out_dir), artifact_path="lora_checkpoint")

        lineage = {
            "train_data": str(_resolve_path(base, cfg["data"]["train_path"])),
            "format": "JSONL with original_text + formal|friendly|neutral rewrites",
            "note": "Replace with your curated, versioned dataset and document lineage for grading.",
        }
        p = Path("llm_dataset_lineage.json")
        p.write_text(json.dumps(lineage, indent=2), encoding="utf-8")
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
