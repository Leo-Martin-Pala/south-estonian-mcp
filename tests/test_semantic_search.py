from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import libsql
import numpy as np

from vro_mcp.db import SouthEstonianStore, _vector_rrf_weight


def _unit_vec(seed: int, dim: int = 8) -> list[float]:
    arr = np.zeros(dim, dtype=np.float32)
    arr[seed % dim] = 1.0
    return arr.tolist()


def _mix_vec(a: list[float], b: list[float], alpha: float) -> list[float]:
    arr = alpha * np.asarray(a, dtype=np.float32) + (1.0 - alpha) * np.asarray(b, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return (arr / norm).tolist() if norm > 1e-12 else arr.tolist()


class _FakeNano:
    def __init__(self, vec: list[float]) -> None:
        self._vec = np.asarray(vec, dtype=np.float32)
        self.dim = len(vec)

    def encode_query(self, _text: str) -> np.ndarray:
        return self._vec


class SemanticSearchFixTests(unittest.TestCase):
    def test_vector_rrf_weight_curve(self) -> None:
        self.assertEqual(_vector_rrf_weight(0.85), 1.0)
        self.assertEqual(_vector_rrf_weight(0.55), 1.0)
        self.assertAlmostEqual(_vector_rrf_weight(0.45), 0.625, places=4)
        self.assertAlmostEqual(_vector_rrf_weight(0.35), 0.25, places=4)
        self.assertLess(_vector_rrf_weight(0.20), 0.10)
        self.assertEqual(_vector_rrf_weight(0.0), 0.0)

    def test_dictionary_semantic_hybrid_fts_dedup_fallback_and_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_se.db"
            conn = libsql.connect(str(db_path))
            conn.executescript(
                """
                CREATE TABLE dict_entries (
                    id INTEGER PRIMARY KEY,
                    entry_id TEXT NOT NULL,
                    lang TEXT NOT NULL,
                    headword TEXT NOT NULL,
                    pos TEXT,
                    source_slug TEXT NOT NULL
                );
                CREATE TABLE dict_definitions (
                    id INTEGER PRIMARY KEY,
                    entry_rowid INTEGER NOT NULL,
                    lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    definition_text TEXT NOT NULL,
                    norm_def TEXT NOT NULL,
                    sense TEXT,
                    def_vec F8_BLOB(8)
                );
                CREATE VIRTUAL TABLE dict_fts USING fts5(
                    headword,
                    definition_text,
                    lang UNINDEXED,
                    entry_rowid UNINDEXED,
                    tokenize='unicode61'
                );
                """
            )
            q_vec = _unit_vec(0)
            strong_vec = _mix_vec(_unit_vec(0), _unit_vec(1), 0.9)
            weak_vec = _mix_vec(_unit_vec(0), _unit_vec(2), 0.2)
            # Entry 1: polysemous (2 definitions) with strong vector + FTS match
            # Entry 2: no def_vec at all (newly repaired definition), FTS match only
            # Entry 3: weak vector only, no FTS match
            conn.executemany(
                "INSERT INTO dict_entries (id, entry_id, lang, headword, pos, source_slug) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (1, "e1", "vro", "vesi", "n", "synaq"),
                    (2, "e2", "vro", "lättevesi", "n", "synaq"),
                    (3, "e3", "vro", "kivi", "n", "synaq"),
                ],
            )
            conn.execute(
                "INSERT INTO dict_definitions VALUES (1, 1, 'vro', 'et', 'vesi, joogivesi', 'vesi joogivesi', '1', vector8(?))",
                (json.dumps(strong_vec),),
            )
            conn.execute(
                "INSERT INTO dict_definitions VALUES (2, 1, 'vro', 'et', 'vesi (järv)', 'vesi järv', '2', vector8(?))",
                (json.dumps(strong_vec),),
            )
            conn.execute(
                "INSERT INTO dict_definitions VALUES (3, 2, 'vro', 'et', 'allika vesi', 'allika vesi', NULL, NULL)"
            )
            conn.execute(
                "INSERT INTO dict_definitions VALUES (4, 3, 'vro', 'et', 'kivi', 'kivi', NULL, vector8(?))",
                (json.dumps(weak_vec),),
            )
            conn.executemany(
                "INSERT INTO dict_fts (headword, definition_text, lang, entry_rowid) VALUES (?, ?, ?, ?)",
                [
                    ("vesi", "vesi, joogivesi", "vro", 1),
                    ("vesi", "vesi (järv)", "vro", 1),
                    ("lättevesi", "allika vesi", "vro", 2),
                    ("kivi", "kivi", "vro", 3),
                ],
            )
            conn.execute(
                "CREATE INDEX idx_dict_def_vec ON dict_definitions(libsql_vector_idx(def_vec, 'metric=cosine'))"
            )
            conn.commit()
            conn.close()

            store = SouthEstonianStore(db_path)

            # Hybrid query_text="vesi": entry 1 (hybrid) > entry 2 (fts, even with NULL def_vec!) > entry 3 (weak vector)
            hits = store.search_dictionary_semantic(q_vec, query_text="vesi", lang="vro", limit=3)
            self.assertEqual([h["headword"] for h in hits], ["vesi", "lättevesi", "kivi"])
            self.assertEqual(hits[0]["match"], "hybrid")
            self.assertEqual(hits[1]["match"], "fts")
            self.assertEqual(hits[2]["match"], "vector")
            self.assertIn("warnings", hits[2])
            self.assertTrue(any("low semantic similarity" in w for w in hits[2]["warnings"]))
            # Scores strictly non-increasing
            self.assertGreaterEqual(hits[0]["score"], hits[1]["score"])
            self.assertGreaterEqual(hits[1]["score"], hits[2]["score"])

            # Pure vector query (no FTS match): score == vector_score
            pure_hits = store.search_dictionary_semantic(q_vec, query_text="nonexistentterm", lang="vro", limit=2)
            self.assertEqual([h["headword"] for h in pure_hits], ["vesi", "kivi"])
            self.assertEqual(pure_hits[0]["score"], pure_hits[0]["vector_score"])
            self.assertNotIn("warnings", pure_hits[0])
            self.assertIn("warnings", pure_hits[1])

    def test_search_corpus_hybrid_score_monotonic_and_weak_vector_damped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_corpus.db"
            conn = libsql.connect(str(db_path))
            conn.executescript(
                """
                CREATE TABLE corpus_units (
                    id INTEGER PRIMARY KEY,
                    unit_id TEXT NOT NULL,
                    lang TEXT NOT NULL,
                    unit_level TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    unit_idx INTEGER NOT NULL,
                    source_slug TEXT NOT NULL,
                    text TEXT NOT NULL,
                    lid_lang TEXT,
                    lid_conf INTEGER,
                    orig_vec F8_BLOB(8)
                );
                CREATE VIRTUAL TABLE corpus_fts USING fts5(
                    text,
                    tokenize='unicode61'
                );
                """
            )
            q_vec = _unit_vec(0)
            weak_vec = _mix_vec(_unit_vec(0), _unit_vec(3), 0.2)
            conn.execute(
                "INSERT INTO corpus_units VALUES (1, 'u1', 'vro', 'sentence', 'd1', 0, 'uma_leht', 'savvusann om hää', 'vro', 990, NULL)"
            )
            conn.execute(
                "INSERT INTO corpus_units VALUES (2, 'u2', 'vro', 'sentence', 'd1', 1, 'uma_leht', 'mõtsan kasussõ puu', 'vro', 990, vector8(?))",
                (json.dumps(weak_vec),),
            )
            conn.execute("INSERT INTO corpus_fts (rowid, text) VALUES (1, 'savvusann om hää')")
            conn.execute("INSERT INTO corpus_fts (rowid, text) VALUES (2, 'mõtsan kasussõ puu')")
            conn.execute(
                "CREATE INDEX idx_corpus_orig_vec ON corpus_units(libsql_vector_idx(orig_vec, 'metric=cosine'))"
            )
            conn.commit()
            conn.close()

            store = SouthEstonianStore(db_path)
            hits = store.search_corpus("savvusann", query_vec=q_vec, lang="vro", mode="hybrid", limit=2)
            # Strong FTS hit must outrank rank-1 weak vector hit (cos ~ 0.24)
            self.assertEqual([h["unit_id"] for h in hits], ["u1", "u2"])
            self.assertIn("score", hits[0])
            self.assertIn("score", hits[1])
            self.assertGreater(hits[0]["score"], hits[1]["score"])
            self.assertIn("warnings", hits[1])
            self.assertTrue(any("low semantic similarity" in w for w in hits[1]["warnings"]))


if __name__ == "__main__":
    unittest.main()
