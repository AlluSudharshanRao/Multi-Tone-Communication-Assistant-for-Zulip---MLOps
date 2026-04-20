"""
Tone Generator — rewrites a message in three tones: formal, friendly, neutral.

DUMMY_MODE (default=true):
  Template-based rewrites; no torch/transformers required.

Real mode (DUMMY_MODE=false) — two backends (match training_proj15):

1) Seq2seq (default when GENERATOR_BACKEND unset and PEFT_MODEL_PATH empty)
   Flan-T5–style: AutoModelForSeq2SeqLM, prompts in TONE_PROMPTS.
   Env: MODEL_NAME=google/flan-t5-base (or path to fine-tuned seq2seq checkpoint)

2) Causal + optional LoRA (same stack as training/train_llm.py)
   Set GENERATOR_BACKEND=causal, or set PEFT_MODEL_PATH to a LoRA adapter dir.
   Uses the same system + user template as configs/llm_generator_small.yaml by default.
   Env:
     MODEL_NAME=HuggingFaceTB/SmolLM2-135M-Instruct  # base model
     PEFT_MODEL_PATH=/models/lora                     # optional; adapter from train_llm
     GEN_SYSTEM, GEN_USER_TEMPLATE                    # optional overrides
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

TONES = ["formal", "friendly", "neutral"]
DUMMY_MODE = os.environ.get("DUMMY_MODE", "true").lower() != "false"
MODEL_NAME = os.environ.get("MODEL_NAME", "google/flan-t5-base")
PEFT_MODEL_PATH = os.environ.get("PEFT_MODEL_PATH", "").strip()
GENERATOR_PEFT_MODEL_URI = os.environ.get("GENERATOR_PEFT_MODEL_URI", "").strip()
PEFT_MLFLOW_RUN_ID = os.environ.get("PEFT_MLFLOW_RUN_ID", "").strip()
PEFT_MLFLOW_ARTIFACT_PATH = os.environ.get("PEFT_MLFLOW_ARTIFACT_PATH", "lora_checkpoint").strip() or "lora_checkpoint"
MLFLOW_DOWNLOAD_DIR = os.environ.get("MLFLOW_DOWNLOAD_DIR", "/tmp/mlflow_artifacts").strip()

# Defaults aligned with training_proj15-main/training/configs/llm_generator_small.yaml
DEFAULT_GEN_SYSTEM = (
    "You rewrite short workplace chat messages. Follow the requested tone exactly. "
    "Output only the rewritten message, no quotes or preamble."
)
DEFAULT_GEN_USER_TEMPLATE = "Tone: {tone}\nMessage: {original}"

GEN_SYSTEM = os.environ.get("GEN_SYSTEM", DEFAULT_GEN_SYSTEM)
GEN_USER_TEMPLATE = os.environ.get("GEN_USER_TEMPLATE", DEFAULT_GEN_USER_TEMPLATE)

MAX_INPUT_LEN = int(os.environ.get("MAX_INPUT_LEN", "256"))
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "128"))
MAX_CAUSAL_INPUT_LEN = int(os.environ.get("MAX_CAUSAL_INPUT_LEN", "512"))
MAX_NEW_TOKENS_CAUSAL = int(os.environ.get("MAX_NEW_TOKENS_CAUSAL", "128"))
TRUST_REMOTE_CODE = os.environ.get("TRUST_REMOTE_CODE", "false").lower() == "true"


def _resolve_peft_model_path() -> str:
    if PEFT_MODEL_PATH:
        return PEFT_MODEL_PATH
    if not GENERATOR_PEFT_MODEL_URI and not PEFT_MLFLOW_RUN_ID:
        return ""
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        target_dir = Path(MLFLOW_DOWNLOAD_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        if GENERATOR_PEFT_MODEL_URI:
            downloaded = mlflow.artifacts.download_artifacts(
                artifact_uri=GENERATOR_PEFT_MODEL_URI,
                dst_path=str(target_dir),
            )
            logger.info(
                "Downloaded LoRA adapter via registry uri=%s -> %s",
                GENERATOR_PEFT_MODEL_URI,
                downloaded,
            )
        else:
            client = MlflowClient()
            downloaded = client.download_artifacts(
                run_id=PEFT_MLFLOW_RUN_ID,
                path=PEFT_MLFLOW_ARTIFACT_PATH,
                dst_path=str(target_dir),
            )
            logger.info(
                "Downloaded LoRA adapter from MLflow run=%s path=%s -> %s",
                PEFT_MLFLOW_RUN_ID,
                PEFT_MLFLOW_ARTIFACT_PATH,
                downloaded,
            )
        return downloaded
    except Exception as exc:
        logger.exception(
            "Failed to resolve LoRA adapter from MLflow (model_uri=%s run_id=%s path=%s)",
            GENERATOR_PEFT_MODEL_URI,
            PEFT_MLFLOW_RUN_ID,
            PEFT_MLFLOW_ARTIFACT_PATH,
        )
        raise RuntimeError("Unable to resolve PEFT model path from MLflow") from exc


def _generator_backend() -> str:
    explicit = os.environ.get("GENERATOR_BACKEND", "").strip().lower()
    if explicit in ("seq2seq", "causal"):
        return explicit
    if PEFT_MODEL_PATH or GENERATOR_PEFT_MODEL_URI:
        return "causal"
    return "seq2seq"


# ---------------------------------------------------------------------------
# Dummy: template-based rewriter (no model needed)
# ---------------------------------------------------------------------------

_SLANG = {
    r"\byo\b": "Hello",
    r"\bu\b": "you",
    r"\br\b": "are",
    r"\blol\b": "",
    r"\bomg\b": "",
    r"\bbtw\b": "by the way",
    r"\bgonna\b": "going to",
    r"\bwanna\b": "want to",
    r"\bgotta\b": "have to",
    r"\bcant\b": "cannot",
    r"\bdont\b": "do not",
    r"\bwont\b": "will not",
    r"\bim\b": "I am",
    r"\bits\b": "it has",
    r"!!+": ".",
    r"\?\?+": "?",
}


def _clean(text: str) -> str:
    t = text
    for pattern, replacement in _SLANG.items():
        t = re.sub(pattern, replacement, t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" .,")
    return t[0].upper() + t[1:] if t else text


class _DummyGenerator:
    def generate_all(self, text: str) -> dict:
        t_total = time.perf_counter()
        variants = {}
        cleaned = _clean(text)

        templates = {
            "formal": (
                f"{cleaned}. I would appreciate your prompt attention to this matter.",
                random.uniform(0.140, 0.200),
            ),
            "friendly": (
                f"Hey! Just wanted to check in — {cleaned.lower()}. Thanks so much!",
                random.uniform(0.140, 0.200),
            ),
            "neutral": (
                f"{cleaned}. Please address this when possible.",
                random.uniform(0.140, 0.200),
            ),
        }

        offensive = any(
            w in text.lower()
            for w in ["idiot", "stupid", "hate", "damn", "hell", "crap", "ass"]
        )

        for tone, (rewrite, sleep_s) in templates.items():
            time.sleep(sleep_s)
            variants[tone] = {
                "text": rewrite,
                "tone_latency_ms": round(sleep_s * 1000, 2),
            }

        total_latency_ms = (time.perf_counter() - t_total) * 1000
        return {
            "variants": variants,
            "offensive_content_flagged": offensive,
            "total_latency_ms": round(total_latency_ms, 2),
        }


# ---------------------------------------------------------------------------
# Real: seq2seq (Flan-T5 family)
# ---------------------------------------------------------------------------

TONE_PROMPTS = {
    "formal": (
        "Rewrite the following message in a formal, professional tone suitable "
        "for a workplace communication platform. Preserve all original meaning. "
        "Output only the rewritten message.\n\nOriginal: {text}\n\nFormal rewrite:"
    ),
    "friendly": (
        "Rewrite the following message in a warm, friendly, and polite tone. "
        "Preserve all original meaning. "
        "Output only the rewritten message.\n\nOriginal: {text}\n\nFriendly rewrite:"
    ),
    "neutral": (
        "Rewrite the following message in a clear, neutral, and professional tone. "
        "Preserve all original meaning. Remove slang and overly casual phrasing. "
        "Output only the rewritten message.\n\nOriginal: {text}\n\nNeutral rewrite:"
    ),
}


class _RealSeq2SeqGenerator:
    def __init__(self):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        from better_profanity import profanity

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading seq2seq generator: %s on %s", MODEL_NAME, self._device)
        self._tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
        ).to(self._device)
        self._model.eval()
        profanity.load_censor_words()
        self._profanity = profanity
        self._torch = torch
        logger.info("Seq2seq generator ready on %s", self._device)

    def generate_all(self, text: str) -> dict:
        t_total = time.perf_counter()
        variants = {}
        offensive = False

        for tone in TONES:
            prompt = TONE_PROMPTS[tone].format(text=text)
            inputs = self._tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=MAX_INPUT_LEN
            ).to(self._device)
            t0 = time.perf_counter()
            with self._torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    num_beams=4,
                    early_stopping=True,
                    no_repeat_ngram_size=3,
                )
            tone_latency_ms = (time.perf_counter() - t0) * 1000
            rewrite = self._tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
            if self._profanity.contains_profanity(rewrite):
                offensive = True
            variants[tone] = {"text": rewrite, "tone_latency_ms": round(tone_latency_ms, 2)}

        total_latency_ms = (time.perf_counter() - t_total) * 1000
        return {
            "variants": variants,
            "offensive_content_flagged": offensive,
            "total_latency_ms": round(total_latency_ms, 2),
        }


def _build_causal_prompt(tokenizer, system: str, user_content: str) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    return f"<<SYS>>\n{system}\n<</SYS>>\n\n{user_content}\n"


class _RealCausalGenerator:
    """Causal LM + optional PEFT adapter (training train_llm.py)."""

    def __init__(self):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from better_profanity import profanity

        resolved_peft_path = _resolve_peft_model_path()
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self._device == "cuda" else torch.float32

        logger.info(
            "Loading causal generator: base=%s peft=%s on %s",
            MODEL_NAME,
            resolved_peft_path or "(none — full weights at MODEL_NAME)",
            self._device,
        )

        self._tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME,
            trust_remote_code=TRUST_REMOTE_CODE,
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        base = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=dtype,
            trust_remote_code=TRUST_REMOTE_CODE,
            low_cpu_mem_usage=True,
        )
        if resolved_peft_path:
            self._model = PeftModel.from_pretrained(base, resolved_peft_path)
        else:
            self._model = base
        self._model.to(self._device)
        self._model.eval()

        profanity.load_censor_words()
        self._profanity = profanity
        self._torch = torch
        logger.info("Causal generator ready on %s", self._device)

    def generate_all(self, text: str) -> dict:
        t_total = time.perf_counter()
        variants = {}
        offensive = False

        for tone in TONES:
            user_content = GEN_USER_TEMPLATE.format(tone=tone, original=text)
            prompt = _build_causal_prompt(self._tokenizer, GEN_SYSTEM, user_content)
            inputs = self._tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=MAX_CAUSAL_INPUT_LEN,
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}
            input_len = inputs["input_ids"].shape[1]
            t0 = time.perf_counter()
            with self._torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS_CAUSAL,
                    pad_token_id=self._tokenizer.pad_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                    do_sample=False,
                    num_beams=1,
                )
            tone_latency_ms = (time.perf_counter() - t0) * 1000
            gen_ids = output_ids[0, input_len:]
            rewrite = self._tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
            if self._profanity.contains_profanity(rewrite):
                offensive = True
            variants[tone] = {"text": rewrite, "tone_latency_ms": round(tone_latency_ms, 2)}

        total_latency_ms = (time.perf_counter() - t_total) * 1000
        return {
            "variants": variants,
            "offensive_content_flagged": offensive,
            "total_latency_ms": round(total_latency_ms, 2),
        }


class ToneGenerator:
    """Factory: dummy vs real; real selects seq2seq (Flan-T5) or causal (+ optional LoRA)."""

    def __new__(cls):
        if DUMMY_MODE:
            logger.info("Generator starting in DUMMY_MODE (no model download)")
            return _DummyGenerator()

        backend = _generator_backend()
        if backend == "causal":
            logger.info(
                "Generator starting in REAL mode — causal LM (MODEL_NAME=%s, PEFT_MODEL_PATH=%r)",
                MODEL_NAME,
                PEFT_MODEL_PATH or GENERATOR_PEFT_MODEL_URI or PEFT_MLFLOW_RUN_ID or "",
            )
            return _RealCausalGenerator()

        logger.info("Generator starting in REAL mode — seq2seq (MODEL_NAME=%s)", MODEL_NAME)
        return _RealSeq2SeqGenerator()
