"""Lazy-loaded offline inference runners for embeddings, language ID, and local MT."""
from __future__ import annotations

from vro_mcp.runners.classifier import LanguageClassifierRunner
from vro_mcp.runners.embeddings import VoyageNanoRunner
from vro_mcp.runners.local_mt import SmugriMTRunner

__all__ = [
    "VoyageNanoRunner",
    "LanguageClassifierRunner",
    "SmugriMTRunner",
]
