"""Offline local South Estonian ensemble language classifier."""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

import numpy as np

LABELS: tuple[str, ...] = (
    "et",
    "vro",
    "seto",
    "mulgi",
    "tartu",
    "kraasna",
    "leivu",
    "lutsi",
    "old_south_estonian",
    "other_language",
    "mixed",
    "non_linguistic",
)
LABEL_INDEX = {label: idx for idx, label in enumerate(LABELS)}
SOUTH_ESTONIAN_LABELS: tuple[str, ...] = (
    "vro",
    "seto",
    "mulgi",
    "tartu",
    "kraasna",
    "leivu",
    "lutsi",
)

LANG_ALIASES = {
    "voru": "vro",
    "võro": "vro",
    "võru": "vro",
    "vor": "vro",
    "est": "et",
    "estonian": "et",
    "eesti": "et",
    "setu": "seto",
    "mulk": "mulgi",
    "tarto": "tartu",
    "kraasna_estonian": "kraasna",
    "leivu_estonian": "leivu",
    "lutsi_estonian": "lutsi",
}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")


def normalize_lang_hint(lang: str | None) -> str | None:
    if not lang:
        return None
    key = lang.strip().lower()
    return LANG_ALIASES.get(key, key)


def _temperature_scale(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    logits = np.log(np.clip(probabilities, 1e-12, 1.0)) / float(temperature)
    logits -= logits.max(axis=1, keepdims=True)
    probs = np.exp(logits)
    return probs / probs.sum(axis=1, keepdims=True)


def _render_context(row: dict[str, str], config: dict[str, Any]) -> str:
    n = int(config["characters_each_side"])
    before = row.get("context_before") or ""
    after = row.get("context_after") or ""
    if config.get("mode") == "target_with_context_pair":
        return f"{row['text']} </s></s> <before> {before[-n:]} <after> {after[:n]}"
    central = f" <central> {row['text']} </central> " * int(config.get("target_repeats", 1))
    return f"{central} <before> {before[-n:]} <after> {after[:n]}"


def _apply_prior(
    probs: np.ndarray,
    source_lang_prior: str | None,
    *,
    prior_boost: float = 3.5,
    south_est_threshold: float = 0.45,
) -> tuple[np.ndarray, bool]:
    prior = normalize_lang_hint(source_lang_prior)
    if prior not in SOUTH_ESTONIAN_LABELS:
        return probs, False
    south_sum = float(sum(probs[LABEL_INDEX[lbl]] for lbl in SOUTH_ESTONIAN_LABELS))
    if south_sum < south_threshold_value(south_est_threshold):
        return probs, False
    adjusted = probs.astype(np.float64, copy=True)
    adjusted[LABEL_INDEX[prior]] *= float(prior_boost)
    total = float(adjusted.sum())
    if total > 0:
        adjusted /= total
    return adjusted, True


def south_threshold_value(v: float) -> float:
    return float(v)


def _select_device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class LanguageClassifierRunner:
    """Thread-safe lazy loader for standalone and contextual South Estonian LID ensembles."""

    def __init__(self, models_dir: str | Path) -> None:
        self.models_dir = Path(models_dir)
        self._lock = threading.Lock()
        self._member_cache: dict[tuple[str, str], Any] = {}
        self._ensembles: dict[str, list[tuple[str, float, Any]]] = {}

    def _resolve_path(self, raw_path: str) -> Path:
        p = Path(raw_path)
        return p if p.is_absolute() else (self.models_dir / p).resolve()

    def _load_member(self, kind: str, model_dir: Path, *, calibrated: bool = True, prepared: bool = False):
        cache_key = (f"{kind}:cal={calibrated}:prep={prepared}", str(model_dir))
        if cache_key in self._member_cache:
            return self._member_cache[cache_key]

        input_config = model_dir / "input_config.json"
        if not prepared and input_config.exists():
            config = json.loads(input_config.read_text(encoding="utf-8"))
            raw = self._load_member(kind, model_dir, calibrated=calibrated, prepared=True)

            def predict_with_context(rows: list[dict[str, str]]) -> np.ndarray:
                return raw([{**r, "text": _render_context(r, config)} for r in rows])

            self._member_cache[cache_key] = predict_with_context
            return predict_with_context

        calibration = model_dir / "calibration.json"
        if calibrated and calibration.exists():
            raw = self._load_member(kind, model_dir, calibrated=False, prepared=True)
            temperature = float(json.loads(calibration.read_text(encoding="utf-8"))["temperature"])

            def predict_calibrated(rows: list[dict[str, str]]) -> np.ndarray:
                return _temperature_scale(raw(rows), temperature)

            self._member_cache[cache_key] = predict_calibrated
            return predict_calibrated

        if kind == "fasttext":
            import fasttext

            bin_path = model_dir / ("model.bin" if (model_dir / "model.bin").exists() else "model.ftz")
            ft_model = fasttext.load_model(str(bin_path))

            def predict_fasttext(rows: list[dict[str, str]]) -> np.ndarray:
                result = np.zeros((len(rows), len(LABELS)), dtype=np.float64)
                for i, row in enumerate(rows):
                    clean = " ".join(row["text"].split())
                    for score, label in ft_model.f.predict(clean, len(LABELS), 0.0, "strict"):
                        name = label.removeprefix("__label__")
                        if name in LABEL_INDEX:
                            result[i, LABEL_INDEX[name]] = float(score)
                sums = result.sum(axis=1, keepdims=True)
                sums = np.where(sums > 1e-12, sums, 1.0)
                return result / sums

            self._member_cache[cache_key] = predict_fasttext
            return predict_fasttext

        if kind == "linear":
            import joblib

            lin_model = joblib.load(model_dir / "model.joblib")

            def predict_linear(rows: list[dict[str, str]]) -> np.ndarray:
                probs = lin_model.predict_proba([r["text"] for r in rows])
                result = np.zeros((len(rows), len(LABELS)), dtype=np.float64)
                for i, label in enumerate(lin_model.classes_):
                    if label in LABEL_INDEX:
                        result[:, LABEL_INDEX[label]] = probs[:, i]
                return result

            self._member_cache[cache_key] = predict_linear
            return predict_linear

        if kind == "glotlid":
            import fasttext
            import torch

            cfg = json.loads((model_dir / "configuration.json").read_text(encoding="utf-8"))
            pretrained_path = self._resolve_path(cfg["pretrained"])
            ft = fasttext.load_model(str(pretrained_path))
            matrix = ft.get_input_matrix()
            state = np.load(model_dir / "adaptation.npz")
            matrix[state["ids"]] = state["vectors"]

            hidden = int(cfg.get("hidden", 0))
            dim = matrix.shape[1]
            embedding = torch.nn.EmbeddingBag.from_pretrained(
                torch.as_tensor(matrix), freeze=True, mode="mean", sparse=True
            )
            if hidden:
                head = torch.nn.Sequential(
                    torch.nn.Linear(dim, hidden),
                    torch.nn.GELU(),
                    torch.nn.Dropout(0.15),
                    torch.nn.Linear(hidden, len(LABELS)),
                )
            else:
                head = torch.nn.Linear(dim, len(LABELS))
            head.load_state_dict(
                torch.load(model_dir / "head.pt", weights_only=True, map_location="cpu")
            )
            embedding.eval()
            head.eval()
            eos = ft.get_word_id("</s>")

            def encode_features(text: str) -> list[int]:
                ids: list[int] = []
                for word in text.split():
                    ids.extend(ft.get_subwords(word)[1].tolist())
                if eos >= 0:
                    ids.append(eos)
                return ids or ([eos] if eos >= 0 else [0])

            def predict_glotlid(rows: list[dict[str, str]]) -> np.ndarray:
                items = [encode_features(r["text"]) for r in rows]
                out: list[np.ndarray] = []
                with torch.inference_mode():
                    for start in range(0, len(items), 64):
                        batch = items[start : start + 64]
                        offsets = np.cumsum([0] + [len(b) for b in batch[:-1]])
                        indices = [idx for b in batch for idx in b]
                        vec = embedding(
                            torch.tensor(indices, dtype=torch.long),
                            torch.tensor(offsets, dtype=torch.long),
                        )
                        out.append(head(vec).softmax(-1).numpy())
                return np.concatenate(out, axis=0)

            self._member_cache[cache_key] = predict_glotlid
            return predict_glotlid

        if kind == "transformer":
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            device = _select_device()
            best_dir = model_dir / "best" if (model_dir / "best").exists() else model_dir
            cfg = (
                json.loads((model_dir / "configuration.json").read_text(encoding="utf-8"))
                if (model_dir / "configuration.json").exists()
                else {}
            )
            max_length = int(cfg.get("max_length", 192))
            dtype = torch.float16 if device != "cpu" else torch.float32
            model = AutoModelForSequenceClassification.from_pretrained(
                str(best_dir), local_files_only=True, dtype=dtype
            ).to(device)
            model.eval()
            tok = AutoTokenizer.from_pretrained(
                str(best_dir), local_files_only=True, fix_mistral_regex=False
            )

            def predict_transformer(rows: list[dict[str, str]]) -> np.ndarray:
                out: list[np.ndarray] = []
                with torch.inference_mode():
                    for start in range(0, len(rows), 16):
                        chunk = rows[start : start + 16]
                        batch = tok(
                            [r["text"] for r in chunk],
                            padding="max_length" if device == "mps" else True,
                            truncation=True,
                            max_length=max_length,
                            return_tensors="pt",
                        )
                        logits = model(**{k: v.to(device) for k, v in batch.items()}).logits
                        out.append(logits.softmax(-1).float().cpu().numpy())
                return np.concatenate(out, axis=0)

            self._member_cache[cache_key] = predict_transformer
            return predict_transformer

        raise ValueError(f"Unsupported classifier member kind: {kind!r}")

    def _get_ensemble(self, ensemble_mode: str) -> list[tuple[str, float, Any]]:
        if ensemble_mode in self._ensembles:
            return self._ensembles[ensemble_mode]
        with self._lock:
            if ensemble_mode in self._ensembles:
                return self._ensembles[ensemble_mode]
            dirname = (
                "ensemble_final_context"
                if ensemble_mode == "context"
                else "ensemble_final_standalone"
            )
            manifest = self.models_dir / dirname / "ensemble.json"
            if not manifest.exists():
                raise FileNotFoundError(
                    f"Language classifier manifest missing: {manifest}. "
                    "Run scripts/bundle_models.py first."
                )
            cfg = json.loads(manifest.read_text(encoding="utf-8"))
            members: list[tuple[str, float, Any]] = []
            for m in cfg["members"]:
                weight = float(m["weight"])
                if weight <= 0:
                    continue
                predictor_fn = self._load_member(m["kind"], self._resolve_path(m["path"]))
                members.append((str(m.get("name") or m["kind"]), weight, predictor_fn))
            self._ensembles[ensemble_mode] = members
            return members

    def _predict_rows(
        self, rows: list[dict[str, str]], ensemble_mode: str
    ) -> tuple[np.ndarray, dict[str, tuple[float, np.ndarray]]]:
        members = self._get_ensemble(ensemble_mode)
        per_member: dict[str, tuple[float, np.ndarray]] = {}
        with self._lock:
            for name, weight, fn in members:
                per_member[name] = (weight, np.asarray(fn(rows), dtype=np.float64))
        probs = sum(weight * mat for weight, mat in per_member.values())
        return np.asarray(probs, dtype=np.float64), per_member

    def classify(
        self,
        text: str,
        *,
        context_before: str | None = None,
        context_after: str | None = None,
        source_lang_prior: str | None = None,
        mode: str = "auto",
        top_k: int = 4,
    ) -> dict[str, Any]:
        if mode not in {"auto", "standalone", "context"}:
            raise ValueError("mode must be 'auto', 'standalone', or 'context'")
        if mode == "auto":
            ensemble_mode = (
                "context" if (context_before is not None or context_after is not None) else "standalone"
            )
        else:
            ensemble_mode = mode

        row = {
            "text": text,
            "context_before": context_before or "",
            "context_after": context_after or "",
        }
        raw_matrix, per_member = self._predict_rows([row], ensemble_mode)
        raw_vec = raw_matrix[0]
        raw_top_idx = int(np.argmax(raw_vec))

        adj_vec, prior_applied = _apply_prior(raw_vec, source_lang_prior)
        top_idx = int(np.argmax(adj_vec))
        limit = max(1, min(top_k, len(LABELS)))
        order = np.argsort(-adj_vec)[:limit]

        member_predictions: dict[str, Any] = {}
        for name, (weight, mat) in per_member.items():
            vec = mat[0]
            m_top = int(np.argmax(vec))
            m_order = np.argsort(-vec)[:limit]
            member_predictions[name] = {
                "weight": weight,
                "predicted_lang": LABELS[m_top],
                "confidence": round(float(vec[m_top]), 4),
                "top_probabilities": [
                    {"lang": LABELS[i], "prob": round(float(vec[i]), 4)} for i in m_order
                ],
            }

        return {
            "text": text,
            "mode": ensemble_mode,
            "predicted_lang": LABELS[top_idx],
            "confidence": round(float(adj_vec[top_idx]), 4),
            "prior_applied": prior_applied,
            "source_lang_prior": normalize_lang_hint(source_lang_prior),
            "raw_predicted_lang": LABELS[raw_top_idx],
            "raw_confidence": round(float(raw_vec[raw_top_idx]), 4),
            "top_probabilities": [
                {"lang": LABELS[i], "prob": round(float(adj_vec[i]), 4)} for i in order
            ],
            "member_predictions": member_predictions,
        }

    def classify_document(
        self,
        text: str,
        *,
        source_lang_prior: str | None = None,
        top_k: int = 4,
    ) -> dict[str, Any]:
        spans: list[tuple[int, int, str]] = []
        pos = 0
        for match in _SENTENCE_SPLIT_RE.finditer(text):
            end = match.start()
            chunk = text[pos:end].strip()
            if chunk:
                spans.append((pos, end, chunk))
            pos = match.end()
        if pos < len(text):
            tail = text[pos:].strip()
            if tail:
                spans.append((pos, len(text), tail))

        if not spans:
            return {
                "mode": "context",
                "sentence_count": 0,
                "dominant_lang": "non_linguistic",
                "confidence": 0.0,
                "sentences": [],
                "distribution": {},
            }

        ensemble_mode = "context" if len(spans) > 1 else "standalone"
        rows = [
            {
                "text": chunk,
                "context_before": text[max(0, start - 150) : start],
                "context_after": text[end : min(len(text), end + 150)],
            }
            for start, end, chunk in spans
        ]
        raw_matrix, _ = self._predict_rows(rows, ensemble_mode)
        results: list[dict[str, Any]] = []
        lang_counts: dict[str, int] = {}
        avg_probs = np.zeros(len(LABELS), dtype=np.float64)

        for (start, end, chunk), raw_vec in zip(spans, raw_matrix):
            adj_vec, prior_applied = _apply_prior(raw_vec, source_lang_prior)
            avg_probs += adj_vec
            top_idx = int(np.argmax(adj_vec))
            pred = LABELS[top_idx]
            lang_counts[pred] = lang_counts.get(pred, 0) + 1
            order = np.argsort(-adj_vec)[: max(1, min(top_k, len(LABELS)))]
            results.append(
                {
                    "index": len(results),
                    "start": start,
                    "end": end,
                    "text": chunk,
                    "predicted_lang": pred,
                    "confidence": round(float(adj_vec[top_idx]), 4),
                    "prior_applied": prior_applied,
                    "top_probabilities": [
                        {"lang": LABELS[i], "prob": round(float(adj_vec[i]), 4)} for i in order
                    ],
                }
            )

        avg_probs /= len(spans)
        dom_idx = int(np.argmax(avg_probs))
        return {
            "mode": ensemble_mode,
            "sentence_count": len(results),
            "dominant_lang": LABELS[dom_idx],
            "confidence": round(float(avg_probs[dom_idx]), 4),
            "source_lang_prior": normalize_lang_hint(source_lang_prior),
            "lang_sentence_counts": lang_counts,
            "sentences": results,
        }
