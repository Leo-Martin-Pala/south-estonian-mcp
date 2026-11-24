"""Offline local Voyage-4-Nano runner (512-dim Matryoshka embeddings)."""
from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np


DEFAULT_DIM = 512


def _select_device(requested: str = "auto") -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def vector8_json(vec: np.ndarray | list[float], dim: int = DEFAULT_DIM) -> str:
    """Truncate to `dim`, L2-renormalize, and format as JSON literal for libSQL vector8()."""
    arr = np.asarray(vec, dtype=np.float32)[:dim]
    norm = float(np.linalg.norm(arr))
    if norm > 1e-12:
        arr = arr / norm
    return "[" + ",".join(f"{float(x):.5f}" for x in arr) + "]"


class VoyageNanoRunner:
    """Thread-safe lazy loader for local models/voyage_4_nano."""

    def __init__(
        self,
        model_dir: str | Path,
        *,
        dim: int = DEFAULT_DIM,
        device: str = "auto",
        batch_size: int = 32,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.dim = dim
        self.requested_device = device
        self.batch_size = batch_size
        self.cache_dir = Path(cache_dir) if cache_dir else self.model_dir.parent / ".hf_modules_cache"
        self._lock = threading.Lock()
        self._model = None
        self._device = None
        self._prompts: dict[str, str] = {}

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            if not (self.model_dir / "model.safetensors").exists():
                raise FileNotFoundError(
                    f"Local Voyage-4-Nano weights not found at {self.model_dir}. "
                    "Run scripts/bundle_models.py first."
                )
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("HF_MODULES_CACHE", str(self.cache_dir))

            import torch
            from sentence_transformers import SentenceTransformer

            device = _select_device(self.requested_device)
            dtype = torch.bfloat16 if device != "cpu" else torch.float32
            model = SentenceTransformer(
                str(self.model_dir),
                trust_remote_code=True,
                device=device,
                truncate_dim=self.dim,
                local_files_only=True,
                model_kwargs={"attn_implementation": "sdpa", "dtype": dtype},
            )
            self._device = device
            self._prompts = {
                role: model.prompts[role]
                for role in ("query", "document")
                if role in getattr(model, "prompts", {})
            }
            if "query" not in self._prompts:
                self._prompts["query"] = "Represent the query for retrieving supporting documents: "
            if "document" not in self._prompts:
                self._prompts["document"] = "Represent the document for retrieval: "
            self._model = model

    def encode(self, texts: list[str], role: str = "query") -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        self._ensure_loaded()
        if role not in self._prompts:
            raise ValueError(f"Unsupported VoyageNanoRunner role: {role!r}")
        prompt = self._prompts[role]
        # Serialize encode calls because SentenceTransformer/PyTorch MPS backend is not multi-thread safe.
        with self._lock:
            vecs = self._model.encode(
                texts,
                prompt=prompt,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        arr = np.asarray(vecs, dtype=np.float32)[:, : self.dim]
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms > 1e-12, norms, 1.0)
        return (arr / norms).astype(np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        return self.encode([text], role="query")[0]

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self.encode(texts, role="query")

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return self.encode(texts, role="document")
