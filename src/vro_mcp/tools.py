from __future__ import annotations

import json
import sqlite3
import re
from typing import Any

from .config import Settings
from .correction import CorrectionSuggester
from .db import (
    PUBLIC_DIRECTIONS,
    CorpusStore,
    DictionaryStore,
    WordBagStore,
    normalize_db_text,
    normalize_public_direction,
)
from .estonian_leakage import EstonianLeakageLinter
from .giella import GiellaAdapter
from .neurotolge import NeurotolgeClient
from .tokenization import tokenize

# Per-tool input caps. The dictionary/corpus tools return heavy payloads, so
# they are capped low; the word-bag and analyzer tools return tiny per-item
# results and can take many more inputs in one call.
LOOKUP_CAP = 15
USAGE_CAP = 15
EXISTS_CAP = 100
ANALYZE_CAP = 100
LEAKAGE_CAP = 100
UNRECOGNIZED_LIMIT = 500
_SPELL_SUGGESTION_RE = re.compile(r"^(?P<form>.+?)\s+(?P<score>-?\d+(?:\.\d+)?)$")
_COUNT_WORD_RE = re.compile(
    r"[^\W_]+(?:(?:['ʼ´’‘-][^\W_]+)|(?:[.,][0-9]+))*",
    re.UNICODE,
)
_SENTENCE_END_RE = re.compile(r"[.!?…]+(?:[\"')\]\}»”’]+)?(?=\s|$)")
SUGGESTION_LIMIT = 3
FINDING_LIMIT_DEFAULT = 10
FINDING_LIMIT_MAX = 50


def _prepare_batch(value: str | list[str] | None, cap: int) -> tuple[list[str], int]:
    """Normalise a single string or a list into a stripped, de-duplicated,
    order-preserving list capped at ``cap``. Returns (kept, dropped_count)."""
    if value is None:
        items: list[str] = []
    elif isinstance(value, str):
        items = [value]
    else:
        items = list(value)

    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items:
        text = item.strip() if isinstance(item, str) else str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)

    dropped = max(0, len(cleaned) - cap)
    return cleaned[:cap], dropped


def _per_item_limit(limit: int | None, batched: bool) -> int:
    """Per-query result limit: smaller defaults/ceilings when batching to keep
    the combined payload manageable."""
    ceiling = 10 if batched else 50
    if limit is None:
        return 3 if batched else 10
    return max(1, min(int(limit), ceiling))


def _output_limit(limit: int | None, default: int = 50, maximum: int = UNRECOGNIZED_LIMIT) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), maximum))


def _finding_limit(limit: int | None) -> int:
    if limit is None:
        return FINDING_LIMIT_DEFAULT
    return max(1, min(int(limit), FINDING_LIMIT_MAX))


def _parse_spellcheck_lines(lines: list[str], limit: int | None = None) -> dict[str, Any]:
    max_findings = _finding_limit(limit)
    unknown: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    seen_words: set[str] = set()
    truncated = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('"') and " is NOT in the lexicon" in stripped:
            word = stripped.split('"', 2)[1]
            if word in seen_words:
                current = None
                continue
            seen_words.add(word)
            if len(unknown) >= max_findings:
                current = None
                truncated = True
                continue
            current = {"word": word, "suggestions": []}
            unknown.append(current)
            continue
        if current is None or stripped.startswith("Corrections for "):
            continue
        match = _SPELL_SUGGESTION_RE.match(stripped)
        if match and len(current["suggestions"]) < SUGGESTION_LIMIT:
            current["suggestions"].append(match.group("form"))
    out: dict[str, Any] = {"unknown": unknown}
    if truncated:
        out["truncated"] = True
    return out


def _parse_grammar_lines(lines: list[str], limit: int | None = None) -> dict[str, Any]:
    max_findings = _finding_limit(limit)
    errors: list[dict[str, Any]] = []
    truncated = False
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return {"lines": lines}
        if not isinstance(payload, dict):
            return {"lines": lines}
        for item in payload.get("errs", []):
            if not isinstance(item, list) or len(item) < 7:
                continue
            if len(errors) >= max_findings:
                truncated = True
                continue
            suggestions = item[5] if isinstance(item[5], list) else []
            errors.append(
                {
                    "word": item[0],
                    "span": [item[1], item[2]],
                    "code": item[4],
                    "suggestions": suggestions[:SUGGESTION_LIMIT],
                }
            )
    out: dict[str, Any] = {"errors": errors}
    if truncated:
        out["truncated"] = True
    return out


def _count_text(text: str) -> dict[str, int]:
    words = len(_COUNT_WORD_RE.findall(text))
    sentence_marks = len(_SENTENCE_END_RE.findall(text))
    estimated_sentences = max(1, sentence_marks) if words else 0
    return {
        "characters": len(text),
        "words": words,
        "estimated_sentences": estimated_sentences,
    }


class VroTools:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.dictionary = DictionaryStore(settings.dictionary_db)
        self.corpus = CorpusStore(settings.corpus_db)
        self.word_bag = WordBagStore(settings.word_bag_db)
        self.giella = GiellaAdapter(
            settings.analyzer_cmd,
            settings.generator_cmd,
            settings.speller_cmd,
            settings.grammar_cmd,
        )
        self.neurotolge = NeurotolgeClient(settings.neurotolge_base_url)
        self.estonian_leakage = EstonianLeakageLinter()
        self.correction_suggester = CorrectionSuggester(self.dictionary, self.giella)

    def lookup_word(
        self,
        words: str | list[str],
        direction: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        word_list, dropped = _prepare_batch(words, LOOKUP_CAP)
        per = _per_item_limit(limit, batched=len(word_list) > 1)
        canonical_direction = normalize_public_direction(direction)
        if direction is not None and direction.strip() and canonical_direction is None:
            return {
                "error": "invalid_direction",
                "direction": direction,
                "valid_directions": list(PUBLIC_DIRECTIONS),
                "detail": "Leave direction unset for full concept lookup.",
            }
        try:
            results = {
                w: self.dictionary.lookup_word(w, direction=canonical_direction, limit=per)
                for w in word_list
            }
        except sqlite3.Error as exc:
            return self._db_unavailable("dictionary", self.settings.dictionary_db, exc)
        out: dict[str, Any] = results
        if dropped:
            out["_dropped"] = dropped
        return out

    def find_usage_examples(
        self,
        words: str | list[str],
        source_type: str | None = None,
        limit: int = 3,
    ) -> dict[str, Any]:
        word_list, dropped = _prepare_batch(words, USAGE_CAP)
        per = _per_item_limit(limit, batched=len(word_list) > 1)
        try:
            results = {
                w: self.corpus.find_usage_examples(w, source_type=source_type, limit=per)
                for w in word_list
            }
        except sqlite3.Error as exc:
            return self._db_unavailable("corpus", self.settings.corpus_db, exc)
        out: dict[str, Any] = results
        if dropped:
            out["_dropped"] = dropped
        return out

    def word_exists_in_bag(
        self,
        words: str | list[str],
    ) -> dict[str, Any]:
        items, dropped = _prepare_batch(words, EXISTS_CAP)
        try:
            rows = self.word_bag.exists_many(items)
        except sqlite3.Error as exc:
            return self._db_unavailable("word_bag", self.settings.word_bag_db, exc)
        out: dict[str, Any] = {
            original: int(result.get("total_count", 0))
            for original, result in rows.items()
        }
        if dropped:
            out["_dropped"] = dropped
        return out

    def count_text(self, text: str) -> dict[str, int]:
        return _count_text(text)

    def find_unknown_words(self, text: str, limit: int = 50) -> dict[str, Any]:
        try:
            return self.word_bag.find_unknown_words(text, limit=limit)
        except sqlite3.Error as exc:
            return self._db_unavailable("word_bag", self.settings.word_bag_db, exc)

    def find_unrecognized_words(
        self,
        text: str,
        prefilter: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        max_rows = _output_limit(limit)
        tokens = tokenize(text)
        counts: dict[str, int] = {}
        first_seen: dict[str, str] = {}
        for token in tokens:
            normalised = normalize_db_text(token)
            if not normalised:
                continue
            counts[normalised] = counts.get(normalised, 0) + 1
            first_seen.setdefault(normalised, token)

        known: set[str] = set()
        if prefilter and counts:
            try:
                known = self.word_bag._known_words(counts.keys())
            except sqlite3.Error as exc:
                return self._db_unavailable("word_bag", self.settings.word_bag_db, exc)

        candidate_keys = [
            key
            for key in sorted(counts, key=lambda item: (-counts[item], item))
            if key not in known
        ]
        if not candidate_keys:
            return {"unrecognized": [], "checked": 0, "prefiltered": prefilter}

        candidate_surfaces = [first_seen[key] for key in candidate_keys]
        analysis = self.giella.analyze_words(candidate_surfaces)
        if not analysis.get("available"):
            analysis.update(
                {
                    "checked": len(candidate_surfaces),
                    "unrecognized": [],
                    "prefiltered": prefilter,
                }
            )
            return analysis

        results = analysis.get("results", {})
        unrecognized = [
            surface
            for surface in candidate_surfaces
            if not results.get(surface, {}).get("recognized", False)
        ]
        return {
            "unrecognized": unrecognized[:max_rows],
            "checked": len(candidate_surfaces),
            "prefiltered": prefilter,
        }

    def analyze_word(self, words: str | list[str]) -> dict[str, Any]:
        items, dropped = _prepare_batch(words, ANALYZE_CAP)
        result = self.giella.analyze_words(items)
        if not result.get("available"):
            return result
        raw_results = result.get("results", {})
        out: dict[str, Any] = {}
        for item in items:
            lines = raw_results.get(item, {}).get("lines", [])
            out[item] = [
                parts[1]
                for line in lines
                if not line.rstrip().endswith("+?")
                if len(parts := line.split("\t")) >= 2
            ]
        if dropped:
            out["_dropped"] = dropped
        return out

    def lint_estonian_leakage(self, words: str | list[str]) -> dict[str, Any]:
        items, dropped = _prepare_batch(words, LEAKAGE_CAP)
        out = self.estonian_leakage.lint_words(items)
        if dropped:
            out["note"] = f"Capped at {LEAKAGE_CAP} inputs; {dropped} extra dropped."
        return out

    def find_estonian_leakage(self, text: str, limit: int = 200) -> dict[str, Any]:
        max_rows = _output_limit(limit, default=200, maximum=500)
        return self.estonian_leakage.find_in_text(text, limit=max_rows)

    def suggest_correction(self, form: str) -> dict[str, Any]:
        try:
            return self.correction_suggester.suggest_correction(form)
        except sqlite3.Error as exc:
            return self._db_unavailable("dictionary", self.settings.dictionary_db, exc)

    def generate_forms(
        self,
        lemma: str,
        tags: str | None = None,
    ) -> dict[str, Any]:
        result = self.giella.generate_forms(lemma, tags=tags)
        if not result.get("available"):
            return result
        forms = []
        for line in result.get("lines", []):
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].strip() != "0":
                continue
            if len(parts) >= 2 and parts[1].strip() and not parts[1].strip().endswith("+?"):
                forms.append(parts[1].strip())
        return {"forms": forms}

    def spellcheck_vro(self, text: str, limit: int | None = None) -> dict[str, Any]:
        result = self.giella.spellcheck_vro(text)
        if not result.get("available"):
            return result
        return _parse_spellcheck_lines(result.get("lines", []), limit=limit)

    def grammar_check_vro(self, text: str, limit: int | None = None) -> dict[str, Any]:
        result = self.giella.grammar_check_vro(text)
        if not result.get("available"):
            return result
        return _parse_grammar_lines(result.get("lines", []), limit=limit)

    def translate_vro(
        self,
        text: str,
        source_lang: str | None = None,
        target_lang: str | None = None,
    ) -> dict[str, Any]:
        return self.neurotolge.translate(text, source_lang=source_lang, target_lang=target_lang)

    def check_setup(self) -> dict[str, Any]:
        detailed = {
            "databases": {
                "dictionary": self._db_availability(
                    "dictionary",
                    self.settings.dictionary_db,
                    {"entries": {"entry_id", "source", "language", "word", "info"}},
                ),
                "corpus": self._db_availability(
                    "corpus",
                    self.settings.corpus_db,
                    {
                        "segments": {
                            "id",
                            "public_id",
                            "source_slug",
                            "source_type",
                            "document_id",
                            "segment_index",
                            "text",
                        },
                        "segments_fts": {"text"},
                    },
                ),
                "word_bag": self._db_availability(
                    "word_bag",
                    self.settings.word_bag_db,
                    {"words": {"word", "total_count"}},
                ),
            },
            "giella": self.giella.availability(),
        }
        return self._compact_setup(detailed)

    @staticmethod
    def _db_unavailable(name: str, path: Any, exc: Exception) -> dict[str, Any]:
        return {
            "available": False,
            "error": f"{name}_db_unavailable",
            "database": name,
            "path": str(path),
            "reason": str(exc),
            "setup_hint": (
                "Populate local data with `make data` and `make giella`, or hydrate "
                "Modal data with `make deploy-release` / `make deploy-local-force`."
            ),
        }

    @classmethod
    def _db_availability(
        cls,
        name: str,
        path: Any,
        required_schema: dict[str, set[str]],
    ) -> dict[str, Any]:
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
                for table, required_columns in required_schema.items():
                    row = conn.execute(
                        "select 1 from sqlite_master where name = ? limit 1",
                        (table,),
                    ).fetchone()
                    if row is None:
                        raise sqlite3.OperationalError(f"missing required table: {table}")
                    columns = {
                        item[1]
                        for item in conn.execute(f"pragma table_info({table})")
                    }
                    missing = sorted(required_columns - columns)
                    if missing:
                        raise sqlite3.OperationalError(
                            f"{table} missing required column(s): {', '.join(missing)}"
                        )
                first_table = next(iter(required_schema))
                conn.execute(f"select 1 from {first_table} limit 1").fetchone()
        except sqlite3.Error as exc:
            return cls._db_unavailable(name, path, exc)
        return {"available": True, "path": str(path)}

    @staticmethod
    def _compact_setup(detailed: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        compact: dict[str, dict[str, Any]] = {}
        for group, items in detailed.items():
            compact[group] = {}
            for name, info in items.items():
                compact[group][name] = True if info.get("available") else info
        return compact
