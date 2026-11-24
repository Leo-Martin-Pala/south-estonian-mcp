"""Offline local TartuNLP M2M100-418M-SMUGRI translator runner (fp16)."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any


MAX_INPUT_CHARS = 10_000
VALID_MT_LANGUAGES = {"vro", "seto", "et", "en", "fi", "ru", "hu", "lv", "no"}
TARGET_LANGS_FROM_SOUTH_ESTONIAN = {"et", "en", "fi", "ru", "hu", "lv", "no"}
ALIASES = {
    "voru": "vro",
    "võro": "vro",
    "võru": "vro",
    "vor": "vro",
    "setu": "seto",
    "est": "et",
    "estonian": "et",
    "eesti": "et",
    "eng": "en",
    "english": "en",
    "inglise": "en",
    "fin": "fi",
    "finnish": "fi",
    "soome": "fi",
    "rus": "ru",
    "russian": "ru",
    "vene": "ru",
    "hun": "hu",
    "hungarian": "hu",
    "ungari": "hu",
    "lav": "lv",
    "latvian": "lv",
    "läti": "lv",
    "nor": "no",
    "nb": "no",
    "norwegian": "no",
    "norra": "no",
}


def normalize_mt_lang(code: str) -> str:
    key = code.strip().lower()
    norm = ALIASES.get(key, key)
    if norm not in VALID_MT_LANGUAGES:
        raise ValueError(
            f"Unsupported MT language: {code!r}. "
            "Supported: vro, seto (source only), et, en, fi, ru, hu, lv, no."
        )
    return norm


def _split_near_middle(text: str) -> tuple[str, str]:
    middle = len(text) // 2
    boundary = text.rfind(" ", 0, middle + 1)
    if boundary < len(text) // 4:
        boundary = middle
    if boundary < 1:
        raise RuntimeError("Translation did not finish cleanly even after splitting.")
    return text[:boundary], text[boundary:]


def _input_chunks(text: str, max_chars: int = MAX_INPUT_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        boundary = remaining.rfind(" ", 0, max_chars + 1)
        if boundary < max_chars * 3 // 4:
            boundary = max_chars
        chunks.append(remaining[:boundary])
        remaining = remaining[boundary:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _natural_eos(tokens: list[int], eos_token_id: int, pad_token_id: int) -> bool:
    for index, token in enumerate(tokens[1:], 1):
        if token == eos_token_id:
            return all(value == pad_token_id for value in tokens[index + 1 :])
    return False


class SmugriMTRunner:
    """Thread-safe lazy offline loader for models/mt_smugri_fp16."""

    def __init__(self, model_dir: str | Path, *, device: str = "auto") -> None:
        self.model_dir = Path(model_dir)
        self.requested_device = device
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._device = None
        self._torch = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            if not (self.model_dir / "model.safetensors").exists():
                raise FileNotFoundError(
                    f"Local SMUGRI fp16 model not found at {self.model_dir}. "
                    "Run scripts/bundle_models.py first."
                )
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

            import torch
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

            device = self.requested_device
            if device == "auto":
                device = (
                    "mps"
                    if torch.backends.mps.is_available()
                    else ("cuda" if torch.cuda.is_available() else "cpu")
                )

            tok = M2M100Tokenizer.from_pretrained(str(self.model_dir), local_files_only=True)
            for token in tok.additional_special_tokens:
                if token.startswith("__") and token.endswith("__"):
                    lang = token[2:-2]
                    token_id = tok.convert_tokens_to_ids(token)
                    tok.lang_code_to_token[lang] = token
                    tok.lang_code_to_id[lang] = token_id
                    tok.lang_token_to_id[token] = token_id
                    tok.id_to_lang_token[token_id] = token
            if "vro" not in tok.lang_code_to_id:
                raise RuntimeError("Local SMUGRI tokenizer is missing __vro__ token mapping.")

            dtype = torch.float16 if device != "cpu" else torch.float32
            model = M2M100ForConditionalGeneration.from_pretrained(
                str(self.model_dir), local_files_only=True, dtype=dtype
            ).to(device)
            model.eval()

            self._torch = torch
            self._tokenizer = tok
            self._model = model
            self._device = device

    def _generate_batch(self, texts: list[str], src_token_lang: str, tgt_lang: str) -> tuple[list[list[int]], list[str]]:
        self._tokenizer.src_lang = src_token_lang
        encoded = self._tokenizer(
            texts, padding=True, return_tensors="pt", truncation=False, verbose=False
        )
        encoded = {k: v.to(self._device) for k, v in encoded.items()}
        forced_bos = self._tokenizer.get_lang_id(tgt_lang)
        with self._torch.inference_mode():
            out = self._model.generate(
                **encoded,
                forced_bos_token_id=forced_bos,
                num_beams=5,
                do_sample=False,
                max_new_tokens=max(256, encoded["input_ids"].shape[1] * 2 + 64),
                forced_eos_token_id=None,
            )
        decoded = self._tokenizer.batch_decode(out, skip_special_tokens=True)
        return out.tolist(), decoded

    def _finish_chunks(self, chunks: list[str], src_token_lang: str, tgt_lang: str) -> list[str]:
        token_rows, decoded = self._generate_batch(chunks, src_token_lang, tgt_lang)
        eos_id = self._tokenizer.eos_token_id
        pad_id = self._tokenizer.pad_token_id
        results: list[str] = []
        for source, tokens, text in zip(chunks, token_rows, decoded):
            if not _natural_eos(tokens, eos_id, pad_id):
                left, right = _split_near_middle(source)
                results.append(" ".join(self._finish_chunks([left, right], src_token_lang, tgt_lang)))
            else:
                results.append(text.strip())
        return results

    def translate(self, text: str, source_lang: str, target_lang: str) -> dict[str, Any]:
        src = normalize_mt_lang(source_lang)
        tgt = normalize_mt_lang(target_lang)

        if tgt == "seto":
            raise ValueError(
                "Local SMUGRI model cannot translate INTO Seto (seto target is disallowed). "
                "Supported directions: vro <-> et/en/fi/ru/hu/lv/no, and seto -> et/en/fi/ru/hu/lv/no."
            )
        if src == tgt:
            raise ValueError(f"Source and target language must differ (got {src!r}).")
        if src not in {"vro", "seto"} and tgt != "vro":
            raise ValueError(
                f"Unsupported pair {src} -> {tgt}. "
                "Supported directions: vro <-> et/en/fi/ru/hu/lv/no and seto -> et/en/fi/ru/hu/lv/no."
            )
        if src in {"vro", "seto"} and tgt not in TARGET_LANGS_FROM_SOUTH_ESTONIAN:
            raise ValueError(
                f"Unsupported pair {src} -> {tgt}. "
                f"Supported targets from {src}: {', '.join(sorted(TARGET_LANGS_FROM_SOUTH_ESTONIAN))}."
            )

        effective_src = "vro" if src == "seto" else src
        self._ensure_loaded()

        stripped = text.strip()
        if not stripped:
            return {
                "source_lang": src,
                "target_lang": tgt,
                "mt_model_source_lang": effective_src,
                "model": "tartuNLP/m2m100_418M_smugri (fp16)",
                "translated_text": "",
            }

        chunks = _input_chunks(stripped)
        with self._lock:
            translated_chunks = self._finish_chunks(chunks, effective_src, tgt)

        return {
            "source_lang": src,
            "target_lang": tgt,
            "mt_model_source_lang": effective_src,
            "model": "tartuNLP/m2m100_418M_smugri (fp16)",
            "translated_text": " ".join(translated_chunks),
        }
