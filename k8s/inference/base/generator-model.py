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
     ENCODER_REPETITION_PENALTY, REPETITION_PENALTY  # seq2seq + causal (defaults tuned for Flan-T5)
     SEQ2SEQ_NUM_BEAMS, SEQ2SEQ_NO_REPEAT_NGRAM      # beam / n-gram repeat control
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Iterable

logger = logging.getLogger(__name__)

TONES = ["formal", "friendly", "neutral"]
DUMMY_MODE = os.environ.get("DUMMY_MODE", "true").lower() != "false"
MODEL_NAME = os.environ.get("MODEL_NAME", "google/flan-t5-base")
PEFT_MODEL_PATH = os.environ.get("PEFT_MODEL_PATH", "").strip()

# Defaults aligned with training_proj15-main/training/configs/llm_generator_small.yaml
DEFAULT_GEN_SYSTEM = (
    "You rewrite short workplace chat messages for a workplace chat app. "
    "Match the requested tone clearly (word choice and register must differ across formal vs friendly vs neutral). "
    "Keep the same intent; fix obvious spelling and missing apostrophes (e.g. whats → what's). "
    "Output only the rewritten message — no labels, quotes, or preamble."
)
DEFAULT_GEN_USER_TEMPLATE = "Tone: {tone}\nMessage: {original}"

GEN_SYSTEM = os.environ.get("GEN_SYSTEM", DEFAULT_GEN_SYSTEM)
GEN_USER_TEMPLATE = os.environ.get("GEN_USER_TEMPLATE", DEFAULT_GEN_USER_TEMPLATE)

MAX_INPUT_LEN = int(os.environ.get("MAX_INPUT_LEN", "256"))
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "128"))
MAX_CAUSAL_INPUT_LEN = int(os.environ.get("MAX_CAUSAL_INPUT_LEN", "512"))
MAX_NEW_TOKENS_CAUSAL = int(os.environ.get("MAX_NEW_TOKENS_CAUSAL", "128"))
TRUST_REMOTE_CODE = os.environ.get("TRUST_REMOTE_CODE", "false").lower() == "true"
# Seq2seq (Flan-T5): discourage copying the encoder prompt verbatim (HF generation kwargs).
ENCODER_REPETITION_PENALTY = float(os.environ.get("ENCODER_REPETITION_PENALTY", "1.18"))
REPETITION_PENALTY = float(os.environ.get("REPETITION_PENALTY", "1.08"))
SEQ2SEQ_NUM_BEAMS = int(os.environ.get("SEQ2SEQ_NUM_BEAMS", "4"))
SEQ2SEQ_NO_REPEAT_NGRAM = int(os.environ.get("SEQ2SEQ_NO_REPEAT_NGRAM", "2"))


def _generator_backend() -> str:
    explicit = os.environ.get("GENERATOR_BACKEND", "").strip().lower()
    if explicit in ("seq2seq", "causal"):
        return explicit
    if PEFT_MODEL_PATH:
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
    r"\bwhats\b": "what's",
    r"\bwheres\b": "where's",
    r"\bhows\b": "how's",
    r"!!+": ".",
    r"\?\?+": "?",
}


def _clean(text: str) -> str:
    t = text
    for pattern, replacement in _SLANG.items():
        t = re.sub(pattern, replacement, t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" .,")
    return t[0].upper() + t[1:] if t else text


def _ensure_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return text
    if text[-1] not in ".!?":
        text += "?"
    return text[0].upper() + text[1:]


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def _jaccard_similarity(a: str, b: str) -> float:
    wa = _word_set(a)
    wb = _word_set(b)
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa | wb), 1)


def _contains_slang(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "hey man",
        "yo",
        "lol",
        "omg",
        "wanna",
        "gonna",
        "gotta",
        "whats up",
        "what's up",
        "u ",
        " r ",
    ]
    return any(m in lowered for m in markers)


def _looks_like_greeting(text: str) -> bool:
    lowered = re.sub(r"[!?.,]+", "", text.lower()).strip()
    return lowered in {
        "hey man whats up",
        "hey man what's up",
        "hey whats up",
        "hey what's up",
        "hi whats up",
        "hi what's up",
        "hello whats up",
        "hello what's up",
        "hey how are you",
        "hi how are you",
    }


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = _normalized(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _normalize_informal_request(text: str) -> str:
    value = f" {text.strip()} "
    replacements = [
        (r"\bhey man\b", "hello"),
        (r"\byo\b", ""),
        (r"\bpls\b", "please"),
        (r"\bplz\b", "please"),
        (r"\basap\b", "as soon as possible"),
        (r"\bu\b", "you"),
        (r"\bur\b", "your"),
        (r"\br\b", "are"),
        (r"\bcant\b", "can't"),
        (r"\bwont\b", "won't"),
        (r"\bim\b", "I'm"),
    ]
    for pattern, repl in replacements:
        value = re.sub(pattern, repl, value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" ,")
    value = re.sub(r"\bjust\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" ,")
    return _ensure_sentence(value)


def _requestify(text: str, prefix: str) -> str:
    stripped = re.sub(r"[.?!]+$", "", text).strip()
    if not stripped:
        return _ensure_sentence(prefix)
    lowered = stripped.lower()
    request_verbs = (
        "send ",
        "check ",
        "fix ",
        "review ",
        "share ",
        "look ",
        "take ",
        "let ",
        "update ",
    )
    if lowered.startswith(request_verbs):
        return _ensure_sentence(f"{prefix} {lowered}")
    if lowered.startswith("can you ") or lowered.startswith("could you "):
        return _ensure_sentence(stripped)
    return _ensure_sentence(stripped)


def _formal_candidates(cleaned: str) -> list[str]:
    if _looks_like_greeting(cleaned):
        return [
            "Hello, how are you?",
            "Hello, I hope you're doing well.",
            "Good morning, how are you?",
        ]
    normalized = _normalize_informal_request(cleaned)
    lowered = normalized.lower()
    return _dedupe_keep_order(
        [
            _requestify(normalized, "Could you please"),
            f"{normalized} Could you please take a look when you have a moment?",
            f"{normalized} Please let me know when convenient.",
        ]
    )


def _friendly_candidates(cleaned: str) -> list[str]:
    if _looks_like_greeting(cleaned):
        return [
            "Hey, how's it going?",
            "Hey! How are you doing?",
            "Hi! What's up?",
        ]
    normalized = _normalize_informal_request(cleaned)
    return [
        f"Hey, just checking in — {_requestify(normalized, 'could you').lower()}",
        f"Hi! {normalized}",
        f"Hey, hope you're doing well. {normalized}",
    ]


def _neutral_candidates(cleaned: str) -> list[str]:
    if _looks_like_greeting(cleaned):
        return [
            "Hi, how are you?",
            "Hi there, how are you doing?",
            "Hello, how are you?",
        ]
    normalized = _normalize_informal_request(cleaned)
    return [
        _requestify(normalized, "Can you"),
        f"Hi, {_requestify(normalized, 'can you').lower()}",
        f"{normalized} Let me know when you can.",
    ]


def _fallback_rewrite_texts(cleaned: str) -> dict[str, str]:
    """Deterministic per-tone lines when the LM returns a weak rewrite."""
    candidates = {
        "formal": _formal_candidates(cleaned),
        "friendly": _friendly_candidates(cleaned),
        "neutral": _neutral_candidates(cleaned),
    }
    return {
        tone: _ensure_sentence(options[0])
        for tone, options in candidates.items()
    }


def _normalized(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _rewrite_is_degenerate(original: str, rewrite: str) -> bool:
    r = rewrite.strip()
    if not r:
        return True
    if _normalized(original) == _normalized(r):
        return True
    if _jaccard_similarity(original, rewrite) > 0.88:
        return True
    rl = r.lower()
    if "original:" in rl and "rewrite" in rl and len(r) > len(original) + 40:
        return True
    return False


def _tone_specific_badness(original: str, rewrite: str, tone: str) -> bool:
    lowered = rewrite.lower()
    if tone == "formal" and _contains_slang(lowered):
        return True
    if tone == "formal" and any(phrase in lowered for phrase in ["hey man", "what's up", "whats up"]):
        return True
    if tone == "friendly" and lowered.startswith("dear "):
        return True
    if tone == "neutral" and ("thanks so much" in lowered or "prompt attention" in lowered):
        return True
    if _jaccard_similarity(original, rewrite) > 0.84 and _contains_slang(original):
        return True
    return False


def _pick_better_fallback(original: str, tone: str, fallbacks: dict[str, str], used: set[str]) -> str:
    cleaned = _clean(original)
    candidate_bank = {
        "formal": _formal_candidates(cleaned),
        "friendly": _friendly_candidates(cleaned),
        "neutral": _neutral_candidates(cleaned),
    }
    for candidate in candidate_bank[tone]:
        candidate = _ensure_sentence(candidate)
        key = _normalized(candidate)
        if key not in used:
            used.add(key)
            return candidate
    fallback = _ensure_sentence(fallbacks[tone])
    used.add(_normalized(fallback))
    return fallback


def _finalize_variants(original: str, raw_variants: dict[str, dict[str, float | str]]) -> dict[str, dict[str, float | str]]:
    fallbacks = _fallback_rewrite_texts(_clean(original))
    used: set[str] = set()
    finalized: dict[str, dict[str, float | str]] = {}
    for tone in TONES:
        variant = raw_variants[tone]
        rewrite = _ensure_sentence(str(variant["text"]))
        if _rewrite_is_degenerate(original, rewrite) or _tone_specific_badness(original, rewrite, tone):
            rewrite = _pick_better_fallback(original, tone, fallbacks, used)
        else:
            normalized = _normalized(rewrite)
            if normalized in used:
                rewrite = _pick_better_fallback(original, tone, fallbacks, used)
            else:
                used.add(normalized)
        finalized[tone] = {
            "text": rewrite,
            "tone_latency_ms": variant["tone_latency_ms"],
        }
    return finalized


class _DummyGenerator:
    def generate_all(self, text: str) -> dict:
        t_total = time.perf_counter()
        variants = {}
        cleaned = _clean(text)

        lines = _fallback_rewrite_texts(cleaned)
        templates = {
            "formal": (lines["formal"], random.uniform(0.140, 0.200)),
            "friendly": (lines["friendly"], random.uniform(0.140, 0.200)),
            "neutral": (lines["neutral"], random.uniform(0.140, 0.200)),
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
        variants = _finalize_variants(text, variants)

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
        "Task: rewrite for a workplace chat in a formal, respectful, professional tone. "
        "Keep the same intent and facts. Use different wording than the original (no copy-paste). "
        "Fix obvious spelling and apostrophes. "
        "Reply with only the rewritten message — no preamble, quotes, or labels.\n\n"
        "Message:\n{text}\n\nFormal:"
    ),
    "friendly": (
        "Task: rewrite for a workplace chat in a warm, friendly, polite tone. "
        "Keep the same intent and facts. Use different wording than the original (no copy-paste). "
        "Fix obvious spelling and apostrophes. "
        "Reply with only the rewritten message — no preamble, quotes, or labels.\n\n"
        "Message:\n{text}\n\nFriendly:"
    ),
    "neutral": (
        "Task: rewrite for a workplace chat in a clear, neutral, concise professional tone. "
        "Remove heavy slang; keep the same intent and facts. "
        "Use different wording than the original (no copy-paste). Fix obvious spelling and apostrophes. "
        "Reply with only the rewritten message — no preamble, quotes, or labels.\n\n"
        "Message:\n{text}\n\nNeutral:"
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
                    num_beams=SEQ2SEQ_NUM_BEAMS,
                    early_stopping=True,
                    no_repeat_ngram_size=SEQ2SEQ_NO_REPEAT_NGRAM,
                    encoder_repetition_penalty=ENCODER_REPETITION_PENALTY,
                    repetition_penalty=REPETITION_PENALTY,
                )
            tone_latency_ms = (time.perf_counter() - t0) * 1000
            rewrite = self._tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
            if self._profanity.contains_profanity(rewrite):
                offensive = True
            variants[tone] = {"text": rewrite, "tone_latency_ms": round(tone_latency_ms, 2)}
        variants = _finalize_variants(text, variants)

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

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self._device == "cuda" else torch.float32

        logger.info(
            "Loading causal generator: base=%s peft=%s on %s",
            MODEL_NAME,
            PEFT_MODEL_PATH or "(none — full weights at MODEL_NAME)",
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
        if PEFT_MODEL_PATH:
            self._model = PeftModel.from_pretrained(base, PEFT_MODEL_PATH)
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
                    repetition_penalty=REPETITION_PENALTY,
                )
            tone_latency_ms = (time.perf_counter() - t0) * 1000
            gen_ids = output_ids[0, input_len:]
            rewrite = self._tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
            if self._profanity.contains_profanity(rewrite):
                offensive = True
            variants[tone] = {"text": rewrite, "tone_latency_ms": round(tone_latency_ms, 2)}
        variants = _finalize_variants(text, variants)

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
                PEFT_MODEL_PATH or "",
            )
            return _RealCausalGenerator()

        logger.info("Generator starting in REAL mode — seq2seq (MODEL_NAME=%s)", MODEL_NAME)
        return _RealSeq2SeqGenerator()
