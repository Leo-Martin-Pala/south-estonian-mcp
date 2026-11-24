from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

import libsql

from .config import Settings
from .correction import CorrectionSuggester
from .db import (
    PUBLIC_DIRECTIONS,
    SouthEstonianStore,
    normalize_db_text,
    normalize_public_direction,
)
from .estonian_leakage import (
    SOUTH_ESTONIAN_LANGS,
    EstonianLeakageLinter,
    normalize_language_code,
)
from .giella import GIELLA_CAPABILITIES, GiellaAdapter, normalize_giella_lang
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
CORPUS_POLICY_ID = "south-estonian-public-v2"
CORE_RESOURCE_TOPICS: dict[str, str] = {
    "overview": "01-overview-and-orthography.md",
    "nouns": "02-noun-morphology-and-cases.md",
    "verbs": "03-verb-conjugation-and-negation.md",
    "vocabulary": "04-distinctive-vocabulary-and-false-friends.md",
    "sources": "05-corpus-and-dialect-sources.md",
    "guide": "06-translator-and-editor-guide.md",
}
CANONICAL_RESOURCE_TOPICS: dict[str, str] = {
    **CORE_RESOURCE_TOPICS,
    "pronouns": "07-pronouns.md",
    "comparison": "08-comparison.md",
    "numerals": "09-numerals.md",
    "inflection-tables": "10-inflection-tables.md",
    "paradigms": "11-paradigms.md",
}
_RESOURCE_TOPIC_BY_FILE = {fname: topic for topic, fname in CANONICAL_RESOURCE_TOPICS.items()}
RESOURCE_TOPICS: dict[str, str] = {
    **CANONICAL_RESOURCE_TOPICS,
    "orthography": "01-overview-and-orthography.md",
    "overview-and-orthography": "01-overview-and-orthography.md",
    "01": "01-overview-and-orthography.md",
    "01-overview-and-orthography": "01-overview-and-orthography.md",
    "noun-cases": "02-noun-morphology-and-cases.md",
    "noun-morphology": "02-noun-morphology-and-cases.md",
    "noun-morphology-and-cases": "02-noun-morphology-and-cases.md",
    "02": "02-noun-morphology-and-cases.md",
    "02-noun-morphology-and-cases": "02-noun-morphology-and-cases.md",
    "verb-conjugation": "03-verb-conjugation-and-negation.md",
    "verb-conjugation-and-negation": "03-verb-conjugation-and-negation.md",
    "03": "03-verb-conjugation-and-negation.md",
    "03-verb-conjugation-and-negation": "03-verb-conjugation-and-negation.md",
    "lexicon": "04-distinctive-vocabulary-and-false-friends.md",
    "false-friends": "04-distinctive-vocabulary-and-false-friends.md",
    "distinctive-vocabulary": "04-distinctive-vocabulary-and-false-friends.md",
    "distinctive-vocabulary-and-false-friends": "04-distinctive-vocabulary-and-false-friends.md",
    "04": "04-distinctive-vocabulary-and-false-friends.md",
    "04-distinctive-vocabulary-and-false-friends": "04-distinctive-vocabulary-and-false-friends.md",
    "corpus": "05-corpus-and-dialect-sources.md",
    "dialect-sources": "05-corpus-and-dialect-sources.md",
    "corpus-and-dialect-sources": "05-corpus-and-dialect-sources.md",
    "05": "05-corpus-and-dialect-sources.md",
    "05-corpus-and-dialect-sources": "05-corpus-and-dialect-sources.md",
    "translator": "06-translator-and-editor-guide.md",
    "translator-prompt": "06-translator-and-editor-guide.md",
    "translator-guide": "06-translator-and-editor-guide.md",
    "translator-and-editor-guide": "06-translator-and-editor-guide.md",
    "06": "06-translator-and-editor-guide.md",
    "06-translator-and-editor-guide": "06-translator-and-editor-guide.md",
    "asõsõnaq": "07-pronouns.md",
    "07": "07-pronouns.md",
    "07-pronouns": "07-pronouns.md",
    "adjectives": "08-comparison.md",
    "adjective-comparison": "08-comparison.md",
    "08": "08-comparison.md",
    "08-comparison": "08-comparison.md",
    "numbers": "09-numerals.md",
    "arvsõnaq": "09-numerals.md",
    "09": "09-numerals.md",
    "09-numerals": "09-numerals.md",
    "inflection_tables": "10-inflection-tables.md",
    "tables": "10-inflection-tables.md",
    "declension": "10-inflection-tables.md",
    "conjugation": "10-inflection-tables.md",
    "käänamistabel": "10-inflection-tables.md",
    "10": "10-inflection-tables.md",
    "10-inflection-tables": "10-inflection-tables.md",
    "inflection-types": "11-paradigms.md",
    "inflection_types": "11-paradigms.md",
    "tyybiq": "11-paradigms.md",
    "11": "11-paradigms.md",
    "11-paradigms": "11-paradigms.md",
}


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
    total_unknown = 0
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
            total_unknown += 1
            if len(unknown) >= max_findings:
                current = None
                continue
            current = {"word": word, "suggestions": []}
            unknown.append(current)
            continue
        if current is None or stripped.startswith("Corrections for "):
            continue
        match = _SPELL_SUGGESTION_RE.match(stripped)
        if match and len(current["suggestions"]) < SUGGESTION_LIMIT:
            current["suggestions"].append(match.group("form"))
    return {
        "unknown": unknown,
        "returned": len(unknown),
        "total_unknown": total_unknown,
    }


def _parse_grammar_lines(lines: list[str], limit: int | None = None) -> dict[str, Any]:
    max_findings = _finding_limit(limit)
    errors: list[dict[str, Any]] = []
    total_errors = 0
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
            total_errors += 1
            if len(errors) >= max_findings:
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
    return {
        "errors": errors,
        "returned": len(errors),
        "total_errors": total_errors,
    }


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
        self._init_lock = threading.Lock()
        self.giella = GiellaAdapter(
            settings.analyzer_cmd,
            settings.generator_cmd,
            settings.speller_cmd,
            settings.grammar_cmd,
            giella_share_dir=settings.giella_share_dir,
        )
        self.neurotolge = NeurotolgeClient(settings.neurotolge_base_url)
        self.estonian_leakage = EstonianLeakageLinter()
        self._south_estonian_store: SouthEstonianStore | None = None
        self.correction_suggester = CorrectionSuggester(self._get_south_estonian(), self.giella)
        self._nano_runner: Any | None = None
        self._classifier_runner: Any | None = None
        self._mt_runner: Any | None = None
        self._linters: dict[str, EstonianLeakageLinter] = {}

    def _get_lock(self) -> threading.Lock:
        lock = getattr(self, "_init_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._init_lock = lock
        return lock

    def _get_south_estonian(self) -> SouthEstonianStore:
        store = getattr(self, "_south_estonian_store", None)
        if store is None:
            with self._get_lock():
                store = getattr(self, "_south_estonian_store", None)
                if store is None:
                    store = SouthEstonianStore(self.settings.south_estonian_db)
                    self._south_estonian_store = store
        return store

    def _get_nano(self) -> Any:
        runner = getattr(self, "_nano_runner", None)
        if runner is None:
            with self._get_lock():
                runner = getattr(self, "_nano_runner", None)
                if runner is None:
                    from .runners.embeddings import VoyageNanoRunner

                    runner = VoyageNanoRunner(self.settings.models_dir / "voyage_4_nano")
                    self._nano_runner = runner
        return runner

    def _get_classifier(self) -> Any:
        runner = getattr(self, "_classifier_runner", None)
        if runner is None:
            with self._get_lock():
                runner = getattr(self, "_classifier_runner", None)
                if runner is None:
                    from .runners.classifier import LanguageClassifierRunner

                    runner = LanguageClassifierRunner(self.settings.models_dir / "language_id")
                    self._classifier_runner = runner
        return runner

    def _get_mt(self) -> Any:
        runner = getattr(self, "_mt_runner", None)
        if runner is None:
            with self._get_lock():
                runner = getattr(self, "_mt_runner", None)
                if runner is None:
                    from .runners.local_mt import SmugriMTRunner

                    runner = SmugriMTRunner(self.settings.models_dir / "mt_smugri_fp16")
                    self._mt_runner = runner
        return runner

    def _get_linter(self, lang: str | None = None) -> tuple[str, EstonianLeakageLinter]:
        if lang is None or not str(lang).strip():
            return "vro", self.estonian_leakage
        canon = normalize_language_code(lang)
        with self._get_lock():
            cache = getattr(self, "_linters", None)
            if cache is None:
                cache = {}
                self._linters = cache
            linter = cache.get(canon)
            if linter is None:
                linter = EstonianLeakageLinter(lang=canon, rules_dir=self.settings.rules_dir)
                cache[canon] = linter
            return canon, linter

    def _load_paradigms(self, lang: str) -> dict[str, Any]:
        with self._get_lock():
            cache = getattr(self, "_paradigms_cache", None)
            if cache is None:
                cache = {}
                self._paradigms_cache = cache
            if lang in cache:
                return cache[lang]
            path = self.settings.resources_dir / lang / "paradigms.json"
            if not path.exists():
                cache[lang] = {}
                return {}
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                types = data.get("types", {}) if isinstance(data, dict) else {}
            except Exception:
                types = {}
            cache[lang] = types
            return types

    def _attach_paradigms(self, results_by_word: dict[str, Any]) -> None:
        for entries in results_by_word.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                elang = entry.get("lang")
                infl_type = entry.get("inflection_type")
                if not elang or not infl_type:
                    continue
                types_map = self._load_paradigms(str(elang))
                if not types_map:
                    continue
                tokens = [t.strip() for t in re.split(r"[,;/\s]+", str(infl_type)) if t.strip()]
                matched = [types_map[t] for t in tokens if t in types_map]
                if len(matched) == 1:
                    entry["paradigm"] = matched[0]
                elif len(matched) > 1:
                    entry["paradigm"] = matched

    def lookup_word(
        self,
        words: str | list[str],
        direction: str | None = None,
        limit: int | None = None,
        lang: str | None = None,
        target_lang: str | None = None,
        include_inflections: bool = True,
        include_examples: bool = True,
        include_raw: bool = False,
        include_paradigm: bool = False,
        source_slug: str | None = None,
    ) -> dict[str, Any]:
        if direction is not None and direction.strip():
            canonical_direction = normalize_public_direction(direction)
            if canonical_direction is None:
                return {
                    "error": "invalid_direction",
                    "direction": direction,
                    "valid_directions": list(PUBLIC_DIRECTIONS),
                    "detail": "Leave direction unset for full concept lookup.",
                }
            src_d, tgt_d = canonical_direction.split("-", 1)
            if not lang:
                lang = tgt_d if src_d in ("en", "et") else src_d
            if not target_lang:
                target_lang = src_d if src_d in ("en", "et") else tgt_d
        return self.lookup_words(
            words,
            lang=lang,
            target_lang=target_lang,
            include_inflections=include_inflections,
            include_examples=include_examples,
            include_raw=include_raw,
            include_paradigm=include_paradigm,
            limit=limit,
            source_slug=source_slug,
        )

    def lookup_legacy_word(
        self, words: str | list[str], direction: str | None = None, limit: int | None = None,
    ) -> dict[str, Any]:
        results = self.lookup_word(words, direction=direction, lang="vro", limit=limit,
                                   include_inflections=False, include_examples=False)
        if "error" in results:
            return results
        canonical_direction = normalize_public_direction(direction)
        for query, entries in results.items():
            if query == "_dropped":
                continue
            concepts = []
            for entry in entries:
                concept = {"vro": [entry["headword"], *entry.get("variants", [])]}
                for definition in entry.get("definitions", []):
                    lang = definition["target_lang"]
                    if lang in {"et", "en"}:
                        concept.setdefault(lang, []).append(definition["text"])
                if canonical_direction:
                    source, target = canonical_direction.split("-")
                    if source not in concept or target not in concept:
                        continue
                    concept["direction"] = canonical_direction
                concepts.append(concept)
            results[query] = concepts
        return results

    def lint_estonian_leakage(self, words: str | list[str]) -> dict[str, Any]:
        items, dropped = _prepare_batch(words, LEAKAGE_CAP)
        out = self.estonian_leakage.lint_words(items)
        if dropped:
            out["note"] = f"Capped at {LEAKAGE_CAP} inputs; {dropped} extra dropped."
        return out

    def find_estonian_leakage(self, text: str, limit: int = 200) -> dict[str, Any]:
        max_rows = _output_limit(limit, default=200, maximum=500)
        return self.estonian_leakage.find_in_text(text, limit=max_rows)

    def lookup_words(
        self,
        words: str | list[str],
        lang: str | None = None,
        target_lang: str | None = None,
        include_inflections: bool = True,
        include_examples: bool = True,
        include_raw: bool = False,
        include_paradigm: bool = False,
        limit: int | None = None,
        source_slug: str | None = None,
    ) -> dict[str, Any]:
        word_list, dropped = _prepare_batch(words, LOOKUP_CAP)
        per = _per_item_limit(limit, batched=len(word_list) > 1)
        try:
            results = self._get_south_estonian().lookup_words(
                word_list,
                lang=lang,
                target_lang=target_lang,
                include_inflections=include_inflections,
                include_examples=include_examples,
                include_raw=include_raw,
                limit=per,
                source_slug=source_slug,
            )
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except (FileNotFoundError, Exception) as exc:
            if isinstance(exc, FileNotFoundError) or not self.settings.south_estonian_db.exists():
                return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)
            raise
        out: dict[str, Any] = results
        if include_paradigm:
            self._attach_paradigms(out)
        if dropped:
            out["_dropped"] = dropped
        return out

    def search_dictionary_semantic(
        self,
        query: str,
        lang: str | None = None,
        target_lang: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        cleaned = (query or "").strip()
        if not cleaned:
            return {"error": "missing_parameter", "detail": "Provide a non-empty `query`."}
        try:
            norm_lang = normalize_language_code(lang, default=None) if (lang and lang.strip()) else None
            try:
                q_vec = self._get_nano().encode_query(cleaned)
            except (FileNotFoundError, ImportError):
                q_vec = None
            hits = self._get_south_estonian().search_dictionary_semantic(
                q_vec,
                query_text=cleaned,
                lang=norm_lang,
                target_lang=target_lang,
                limit=limit,
            )
            return {"query": cleaned, "lang": norm_lang, "mode": "hybrid" if q_vec is not None else "fts", "results": hits}
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except FileNotFoundError as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)

    def find_cognates(
        self,
        word: str | None = None,
        lang: str | None = None,
        concept: str | None = None,
        limit: int = 15,
    ) -> dict[str, Any]:
        if (word is None or not str(word).strip()) and (concept is None or not str(concept).strip()):
            return {"error": "missing_parameter", "detail": "Provide `word` or `concept`."}
        try:
            return self._get_south_estonian().find_cognates(
                word=word,
                lang=lang,
                concept=concept,
                limit=limit,
            )
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except FileNotFoundError as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)

    def get_word_usage_examples(
        self,
        words: str | list[str],
        lang: str | None = None,
        limit: int = 5,
        max_snippet_chars: int | None = None,
        expand_inflections: bool = False,
    ) -> dict[str, Any]:
        word_list, dropped = _prepare_batch(words, USAGE_CAP)
        per = _per_item_limit(limit, batched=len(word_list) > 1)
        try:
            store = self._get_south_estonian()
            results = {
                w: store.get_word_usage_examples(
                    w,
                    lang=lang,
                    limit=per,
                    max_snippet_chars=max_snippet_chars,
                    expand_inflections=expand_inflections,
                )
                for w in word_list
            }
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except FileNotFoundError as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)
        out: dict[str, Any] = results
        if dropped:
            out["_dropped"] = dropped
        return out

    def search_corpus(
        self,
        query: str,
        lang: str | None = None,
        mode: str = "hybrid",
        source_slug: str | None = None,
        unit_level: str | None = None,
        include_context: bool = False,
        limit: int = 10,
    ) -> dict[str, Any]:
        cleaned = (query or "").strip()
        if not cleaned:
            return {"error": "missing_parameter", "detail": "Provide a non-empty `query`."}
        mode_norm = mode.casefold().strip()
        if mode_norm not in ("fts", "vector", "hybrid"):
            return {"error": "invalid_parameter", "detail": "mode must be 'fts', 'vector', or 'hybrid'."}
        try:
            norm_lang = normalize_language_code(lang, default=None) if (lang and lang.strip()) else None
            q_vec = None
            if mode_norm != "fts":
                try:
                    q_vec = self._get_nano().encode_query(cleaned)
                except (FileNotFoundError, ImportError) as exc:
                    if mode_norm == "vector":
                        return {"available": False, "error": "embedding_model_unavailable", "detail": str(exc)}
                    mode_norm = "fts"
            results = self._get_south_estonian().search_corpus(
                cleaned,
                query_vec=q_vec,
                lang=norm_lang,
                mode=mode_norm,
                source_slug=source_slug,
                unit_level=unit_level,
                include_context=include_context,
                limit=limit,
            )
            return {
                "query": cleaned,
                "lang": norm_lang,
                "mode": mode_norm,
                "count": len(results),
                "results": results,
            }
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except FileNotFoundError as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)

    def search_parallel_examples(
        self,
        query: str,
        lang: str | None = None,
        target_lang: str | None = None,
        mode: str = "hybrid",
        origin_filter: str | None = None,
        include_context: bool = False,
        limit: int = 10,
    ) -> dict[str, Any]:
        cleaned = (query or "").strip()
        if not cleaned:
            return {"error": "missing_parameter", "detail": "Provide a non-empty `query`."}
        mode_norm = mode.casefold().strip()
        if mode_norm not in ("fts", "vector", "hybrid"):
            return {"error": "invalid_parameter", "detail": "mode must be 'fts', 'vector', or 'hybrid'."}
        try:
            norm_lang = normalize_language_code(lang, default=None) if (lang and lang.strip()) else None
            q_vec = None
            if mode_norm != "fts":
                try:
                    q_vec = self._get_nano().encode_query(cleaned)
                except (FileNotFoundError, ImportError) as exc:
                    if mode_norm == "vector":
                        return {"available": False, "error": "embedding_model_unavailable", "detail": str(exc)}
                    mode_norm = "fts"
            results = self._get_south_estonian().search_parallel_examples(
                cleaned,
                query_vec=q_vec,
                lang=norm_lang,
                target_lang=target_lang,
                mode=mode_norm,
                origin_filter=origin_filter,
                include_context=include_context,
                limit=limit,
            )
            return {
                "query": cleaned,
                "lang": norm_lang,
                "target_lang": target_lang,
                "mode": mode_norm,
                "count": len(results),
                "results": results,
            }
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except FileNotFoundError as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)

    def classify_language(
        self,
        text: str,
        context_before: str | None = None,
        context_after: str | None = None,
        source_lang_prior: str | None = None,
        mode: str = "auto",
        document_mode: bool = False,
        top_k: int = 4,
    ) -> dict[str, Any]:
        cleaned = (text or "").strip()
        if not cleaned:
            return {"error": "missing_parameter", "detail": "Provide non-empty `text`."}
        prior = source_lang_prior.casefold().strip() if source_lang_prior and source_lang_prior.strip() else None
        if prior and prior != "et":
            try:
                prior = normalize_language_code(prior)
            except ValueError as exc:
                return {"error": "invalid_parameter", "detail": str(exc)}
        try:
            clf = self._get_classifier()
            if document_mode:
                return clf.classify_document(cleaned, source_lang_prior=prior, top_k=top_k)
            return clf.classify(
                cleaned,
                context_before=context_before,
                context_after=context_after,
                source_lang_prior=prior,
                mode=mode,
                top_k=top_k,
            )
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except (FileNotFoundError, ImportError) as exc:
            return {"available": False, "error": "language_id_model_unavailable", "detail": str(exc)}

    def check_purity_with_rules(
        self,
        words: str | list[str] | None = None,
        text: str | None = None,
        lang: str = "vro",
        mode: str = "auto",
        detail: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        if words is None and (text is None or not str(text).strip()):
            return {"error": "missing_parameter", "detail": "Provide `words` or `text`."}
        try:
            canon_lang, linter = self._get_linter(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except FileNotFoundError as exc:
            return {"available": False, "error": "leakage_rules_unavailable", "detail": str(exc)}

        mode_norm = mode.casefold().strip()
        use_text = mode_norm == "text" or (mode_norm == "auto" and text is not None and words is None)
        if use_text:
            scan_text = str(text if text is not None else words)
            max_rows = _output_limit(limit, default=100, maximum=500)
            scan = linter.find_in_text(scan_text, limit=max_rows)
            out: dict[str, Any] = {
                "lang": canon_lang,
                "ruleset_id": linter.ruleset["ruleset_id"],
                **scan,
            }
            if detail:
                flagged = scan.get("flagged_words", [])
                out["details"] = linter.lint_words(flagged[:40]) if flagged else {}
            return out

        items, dropped = _prepare_batch(words if words is not None else text, LEAKAGE_CAP)
        linted = linter.lint_words(items)
        out = {
            "lang": canon_lang,
            "ruleset_id": linter.ruleset["ruleset_id"],
            "results": linted,
        }
        if dropped:
            out["note"] = f"Capped at {LEAKAGE_CAP} inputs; {dropped} extra dropped."
        return out

    def translate_mt(
        self,
        text: str,
        source_lang: str = "vro",
        target_lang: str = "et",
        backend: str = "auto",
    ) -> dict[str, Any]:
        cleaned = (text or "").strip()
        if not cleaned:
            return {"error": "missing_parameter", "detail": "Provide non-empty `text`."}
        mode = (backend or "auto").strip().lower()
        if mode not in {"auto", "api", "local"}:
            return {
                "error": "invalid_parameter",
                "detail": "backend must be 'auto', 'api', or 'local'.",
            }

        src_norm = (source_lang or "vro").strip().lower()
        tgt_norm = (target_lang or "et").strip().lower()
        if tgt_norm in {"seto", "setu"}:
            return {
                "error": "unsupported_direction",
                "detail": (
                    "Neural MT cannot translate INTO Seto (seto target is disallowed). "
                    "Supported directions: vro <-> et/en/fi/ru/hu/lv/no, and seto -> et/en/fi/ru/hu/lv/no."
                ),
            }

        is_seto_source = src_norm in {"seto", "setu"}

        def _run_local() -> dict[str, Any]:
            res = self._get_mt().translate(cleaned, source_lang=source_lang, target_lang=target_lang)
            res["backend"] = "local_smugri_fp16"
            return res

        def _run_api() -> dict[str, Any]:
            api_res = self.neurotolge.translate(cleaned, source_lang=source_lang, target_lang=target_lang)
            if "error" in api_res:
                return api_res
            return {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "backend": "neurotolge_api",
                "translated_text": api_res.get("text") or "",
                "text": api_res.get("text") or "",
            }

        if mode == "local" or is_seto_source:
            if mode == "api" and is_seto_source:
                return {
                    "error": "unsupported_direction",
                    "detail": "Neurotõlge API does not support 'seto' source directly; use backend='auto' or 'local'.",
                }
            try:
                return _run_local()
            except ValueError as exc:
                return {"error": "unsupported_direction", "detail": str(exc)}
            except (FileNotFoundError, ImportError) as exc:
                return {"available": False, "error": "mt_model_unavailable", "detail": str(exc)}

        api_res = _run_api()
        if "error" not in api_res or mode == "api":
            return api_res

        if api_res.get("error") == "unsupported_translation_pair":
            return api_res

        try:
            local_res = _run_local()
            local_res["fallback_from"] = "neurotolge_api"
            local_res["fallback_used"] = True
            local_res["api_error"] = api_res.get("error")
            return local_res
        except ValueError as exc:
            return {"error": "unsupported_direction", "detail": str(exc)}
        except (FileNotFoundError, ImportError):
            return api_res

    def _available_topics_for_lang(self, canon_lang: str) -> list[str]:
        lang_dir = self.settings.resources_dir / canon_lang
        return [
            topic
            for topic, fname in CANONICAL_RESOURCE_TOPICS.items()
            if (lang_dir / fname).exists()
        ]

    def get_grammar_resource(self, lang: str = "vro", topic: str = "overview") -> dict[str, Any]:
        try:
            canon_lang = normalize_language_code(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        topic_key = (topic or "overview").casefold().strip()
        filename = RESOURCE_TOPICS.get(topic_key)
        if filename is None:
            return {
                "error": "invalid_topic",
                "lang": canon_lang,
                "topic": topic,
                "valid_topics": list(CANONICAL_RESOURCE_TOPICS),
                "available_topics": self._available_topics_for_lang(canon_lang),
            }
        path = self.settings.resources_dir / canon_lang / filename
        if not path.exists():
            return {
                "available": False,
                "error": "resource_not_found",
                "lang": canon_lang,
                "topic": topic_key,
                "available_topics": self._available_topics_for_lang(canon_lang),
                "path": str(path),
            }
        canon_topic = _RESOURCE_TOPIC_BY_FILE[filename]
        return {
            "lang": canon_lang,
            "topic": canon_topic,
            "uri": f"southestonian://language/{canon_lang}/{canon_topic}",
            "filename": filename,
            "content": path.read_text(encoding="utf-8"),
        }

    def get_translation_guide(self, lang: str = "vro") -> dict[str, Any]:
        return self.get_grammar_resource(lang=lang, topic="guide")

    def get_language_stats(self, lang: str | None = None) -> dict[str, Any]:
        try:
            return self._get_south_estonian().get_language_stats(lang=lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        except FileNotFoundError as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)

    def find_usage_examples(
        self,
        words: str | list[str],
        source_type: str | None = None,
        limit: int = 3,
        max_snippet_chars: int | None = None,
    ) -> dict[str, Any]:
        word_list, dropped = _prepare_batch(words, USAGE_CAP)
        per = _per_item_limit(limit, batched=len(word_list) > 1)
        try:
            store = self._get_south_estonian()
            results = {
                w: store.find_usage_examples(
                    w,
                    source_type=source_type,
                    limit=per,
                    max_snippet_chars=max_snippet_chars,
                )
                for w in word_list
            }
        except (FileNotFoundError, sqlite3.Error) as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)
        except Exception as exc:
            if not self.settings.south_estonian_db.exists():
                return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)
            raise
        out: dict[str, Any] = results
        if dropped:
            out["_dropped"] = dropped
        return out

    def word_exists_in_bag(
        self,
        words: str | list[str],
        *,
        lang: str | None = None,
        include_languages: bool = False,
    ) -> dict[str, Any]:
        items, dropped = _prepare_batch(words, EXISTS_CAP)
        try:
            rows = self._get_south_estonian().word_exists_in_bag_many(
                items,
                lang=lang,
                include_languages=include_languages,
            )
        except Exception as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)

        if include_languages:
            out: dict[str, Any] = {
                original: {
                    "total_count": int(result.get("total_count", 0)),
                    "languages": list(result.get("languages") or []),
                }
                for original, result in rows.items()
            }
        else:
            out = {
                original: int(result.get("total_count", 0))
                for original, result in rows.items()
            }
        if dropped:
            out["_dropped"] = dropped
        return out

    def count_text(self, text: str) -> dict[str, int]:
        return _count_text(text)

    def find_unknown_words(
        self,
        text: str,
        *,
        lang: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        try:
            return self._get_south_estonian().find_unknown_words(text, lang=lang, limit=limit)
        except Exception as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)

    def find_unrecognized_words(
        self,
        text: str,
        prefilter: bool = False,
        limit: int = 50,
        lang: str = "vro",
        prefilter_lang: str | None = None,
    ) -> dict[str, Any]:
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        max_rows = _output_limit(limit)
        eff_prefilter_lang = prefilter_lang if prefilter_lang is not None else canon_lang
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
                known = self._get_south_estonian().known_words_in_bag(
                    counts.keys(),
                    lang=eff_prefilter_lang,
                )
            except ValueError as exc:
                return {"error": "invalid_parameter", "detail": str(exc)}
            except Exception as exc:
                return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)

        candidate_keys = [
            key
            for key in sorted(counts, key=lambda item: (-counts[item], item))
            if key not in known
        ]
        if not candidate_keys:
            return {"unrecognized": [], "checked": 0, "prefiltered": prefilter, "lang": canon_lang}

        candidate_surfaces = [first_seen[key] for key in candidate_keys]
        analysis = self.giella.analyze_words(candidate_surfaces, lang=canon_lang)
        if not analysis.get("available"):
            analysis.update(
                {
                    "checked": len(candidate_surfaces),
                    "unrecognized": [],
                    "prefiltered": prefilter,
                    "lang": canon_lang,
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
            "lang": canon_lang,
        }

    def lint_text(
        self,
        text: str,
        *,
        lang: str = "vro",
        checks: list[str] | None = None,
        detail: bool = False,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Run a low-context or detailed multi-check lint pass over a South Estonian text."""
        cleaned = (text or "").strip()
        if not cleaned:
            return {"error": "missing_parameter", "detail": "Provide non-empty `text`."}
        try:
            canon_lang = normalize_language_code(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}

        valid_checks = ("purity", "unknown", "spell", "grammar", "analyzer")
        giella_check_cap = {"spell": "speller", "grammar": "grammar", "analyzer": "analyzer"}
        lang_caps = set(GIELLA_CAPABILITIES.get(canon_lang, ()))
        if checks is None:
            if canon_lang in GIELLA_CAPABILITIES:
                requested = ["purity", "unknown", "spell", "grammar"]
            else:
                requested = ["purity", "unknown"]
        else:
            requested = []
            for item in checks:
                key = str(item).casefold().strip()
                if key not in valid_checks:
                    return {
                        "error": "invalid_parameter",
                        "detail": f"Unsupported check {item!r}. Expected subset of: {', '.join(valid_checks)}.",
                    }
                if key not in requested:
                    requested.append(key)

        max_items = _output_limit(limit, default=25, maximum=200)
        finding_cap = _finding_limit(min(max_items, FINDING_LIMIT_MAX))

        out: dict[str, Any] = {
            "lang": canon_lang,
            "stats": _count_text(cleaned),
            "checks_run": [],
        }
        skipped: dict[str, str] = {}

        for check in requested:
            required_cap = giella_check_cap.get(check)
            if required_cap is not None and required_cap not in lang_caps:
                supported = [
                    lcode for lcode, caps in GIELLA_CAPABILITIES.items() if required_cap in caps
                ]
                skipped[check] = (
                    f"GiellaLT {check} check is not available for {canon_lang} "
                    f"(supported for: {', '.join(supported)})."
                )
                continue

            if check == "purity":
                res = self.check_purity_with_rules(
                    text=cleaned,
                    lang=canon_lang,
                    mode="text",
                    detail=detail,
                    limit=max_items,
                )
                out["checks_run"].append("purity")
                if res.get("error"):
                    out["purity"] = res
                elif detail:
                    out["purity"] = {
                        "flagged_words": res.get("flagged_words", []),
                        "details": res.get("details", {}),
                    }
                else:
                    out["purity_flagged"] = res.get("flagged_words", [])

            elif check == "unknown":
                res = self.find_unknown_words(cleaned, lang=canon_lang, limit=max_items)
                out["checks_run"].append("unknown")
                if res.get("error"):
                    out["unknown"] = res
                else:
                    out["unknown_words"] = res.get("unknown", [])

            elif check == "spell":
                res = self.spellcheck(cleaned, lang=canon_lang, limit=finding_cap)
                out["checks_run"].append("spell")
                if res.get("available") is False or res.get("error"):
                    out["spell"] = res
                elif detail:
                    out["spell"] = res
                else:
                    out["spell_unknown"] = [item["word"] for item in res.get("unknown", [])]
                    if res.get("total_unknown", 0) > res.get("returned", 0):
                        out["spell_total_unknown"] = res["total_unknown"]

            elif check == "grammar":
                res = self.grammar_check(cleaned, lang=canon_lang, limit=finding_cap)
                out["checks_run"].append("grammar")
                if res.get("available") is False or res.get("error"):
                    out["grammar"] = res
                elif detail:
                    out["grammar"] = res
                else:
                    out["grammar_errors"] = [
                        {"word": e["word"], "code": e["code"], "suggestions": e.get("suggestions", [])[:2]}
                        for e in res.get("errors", [])
                    ]
                    if res.get("total_errors", 0) > res.get("returned", 0):
                        out["grammar_total_errors"] = res["total_errors"]

            elif check == "analyzer":
                res = self.find_unrecognized_words(cleaned, lang=canon_lang, prefilter=False, limit=max_items)
                out["checks_run"].append("analyzer")
                if res.get("available") is False or res.get("error"):
                    out["analyzer"] = res
                else:
                    out["unrecognized_words"] = res.get("unrecognized", [])

        if skipped:
            out["skipped_checks"] = skipped
        return out

    def analyze_word(self, words: str | list[str], *, lang: str = "vro") -> dict[str, Any]:
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        items, dropped = _prepare_batch(words, ANALYZE_CAP)
        result = self.giella.analyze_words(items, lang=canon_lang)
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

    def suggest_correction(
        self,
        form: str | None = None,
        word: str | None = None,
        *,
        lang: str = "vro",
    ) -> dict[str, Any]:
        value = form if form is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `form` or `word`."}
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        try:
            result = self.correction_suggester.suggest_correction(value, lang=canon_lang)
        except sqlite3.Error as exc:
            return self._db_unavailable("south_estonian", self.settings.south_estonian_db, exc)
        if result.get("valid") is not False:
            return result
        try:
            bag_entry = self._get_south_estonian().word_exists_in_bag_many([value], lang=canon_lang).get(value, {})
        except Exception:
            return result
        seen = int(bag_entry.get("total_count", 0)) > 0
        result["seen_in_word_bag"] = seen
        if seen:
            result["note"] = (
                "Not analyzer-confirmed, but present in the word bag; "
                "word-bag presence means seen, not necessarily standard."
            )
        return result

    def generate_forms(
        self,
        lemma: str,
        tags: str | None = None,
        *,
        lang: str = "vro",
    ) -> dict[str, Any]:
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        result = self.giella.generate_forms(lemma, tags=tags, lang=canon_lang)
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

    def generate_paradigm(
        self,
        lemma: str,
        pos: str | None = None,
        *,
        lang: str = "vro",
    ) -> dict[str, Any]:
        """Generate a full inflection/conjugation table for a lemma in one FST pass."""
        cleaned = (lemma or "").strip()
        if not cleaned:
            return {"error": "missing_parameter", "detail": "Provide a non-empty `lemma`."}
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}

        pos_map = {
            "n": "N",
            "noun": "N",
            "a": "A",
            "adj": "A",
            "adjective": "A",
            "v": "V",
            "verb": "V",
        }
        resolved_pos: str | None = None
        if pos is not None:
            resolved_pos = pos_map.get(str(pos).strip().casefold())
            if resolved_pos is None:
                return {
                    "error": "invalid_parameter",
                    "detail": f"Unsupported pos {pos!r}. Expected 'N' (noun), 'A' (adjective), or 'V' (verb).",
                }

        resolved_lemma = cleaned
        if resolved_pos is None:
            analysis = self.giella.analyze_words([cleaned], lang=canon_lang)
            if analysis.get("available"):
                lines = analysis.get("results", {}).get(cleaned, {}).get("lines", [])
                best: tuple[int, str, str] | None = None
                for line in lines:
                    if line.rstrip().endswith("+?"):
                        continue
                    parts = line.split("\t")
                    if len(parts) < 2:
                        continue
                    tags = parts[1].split("+")
                    if len(tags) < 2 or tags[1] not in ("N", "A", "V"):
                        continue
                    cand_lemma, cand_pos = tags[0], tags[1]
                    is_guess = "+Guess+" in parts[1]
                    is_exact = cand_lemma.casefold() == cleaned.casefold()
                    rank = (1 if is_guess else 0, 0 if is_exact else 1)
                    if best is None or rank < (best[0] // 2, best[0] % 2):
                        best = (rank[0] * 2 + rank[1], cand_lemma, cand_pos)
                if best is not None:
                    resolved_lemma, resolved_pos = best[1], best[2]

        if resolved_pos is None:
            resolved_pos = "V" if cleaned.casefold().endswith(("ma", "mä")) else "N"

        cases = ("Nom", "Gen", "Par", "Ill", "Ine", "Ela", "All", "Ade", "Abl", "Tra", "Ter", "Ess", "Abe", "Com")
        persons = ("Sg1", "Sg2", "Sg3", "Pl1", "Pl2", "Pl3")

        slot_specs: list[tuple[str, str, str]] = []
        if resolved_pos in ("N", "A"):
            for case in cases:
                slot_specs.append(("singular", case, f"{resolved_lemma}+{resolved_pos}+Sg+{case}"))
            for case in cases:
                slot_specs.append(("plural", case, f"{resolved_lemma}+{resolved_pos}+Pl+{case}"))
            if resolved_pos == "A":
                slot_specs.extend(
                    [
                        ("comparison", "CompSgNom", f"{resolved_lemma}+A+Comp+Sg+Nom"),
                        ("comparison", "CompSgGen", f"{resolved_lemma}+A+Comp+Sg+Gen"),
                        ("comparison", "SuperlSgNom", f"{resolved_lemma}+A+Superl+Sg+Nom"),
                    ]
                )
        else:
            slot_specs.extend(
                [
                    ("non_finite", "Inf", f"{resolved_lemma}+V+Inf"),
                    ("non_finite", "Sup_mA", f"{resolved_lemma}+V+Inf/mA"),
                    ("non_finite", "Sup_mA", f"{resolved_lemma}+V+Ma"),
                    ("non_finite", "ActPrfPrc", f"{resolved_lemma}+V+Act+PrfPrc"),
                    ("non_finite", "PssPrfPrc", f"{resolved_lemma}+V+Pss+PrfPrc"),
                ]
            )
            for p in persons:
                slot_specs.append(("present", p, f"{resolved_lemma}+V+Act+Ind+Prs+{p}"))
            for p in persons:
                slot_specs.append(("past", p, f"{resolved_lemma}+V+Act+Ind+Prt+{p}"))
            for p in persons:
                slot_specs.append(("conditional", p, f"{resolved_lemma}+V+Act+Cond+Prs+{p}"))
            slot_specs.extend(
                [
                    ("imperative", "Sg2", f"{resolved_lemma}+V+Act+Imprt+Sg2"),
                    ("imperative", "Pl2", f"{resolved_lemma}+V+Act+Imprt+Pl2"),
                    ("connegative", "IndConNeg", f"{resolved_lemma}+V+Act+Ind+ConNeg"),
                    ("passive", "Prs", f"{resolved_lemma}+V+Pss+Ind+Prs"),
                    ("passive", "Prt", f"{resolved_lemma}+V+Pss+Ind+Prt"),
                ]
            )

        gen = self.giella.generate_many([q for _, _, q in slot_specs], lang=canon_lang)
        if not gen.get("available"):
            return gen

        results = gen.get("results", {})
        sections: dict[str, dict[str, list[str]]] = {}
        total_forms = 0
        for section, slot, query in slot_specs:
            forms = results.get(query, [])
            if not forms:
                continue
            bucket = sections.setdefault(section, {}).setdefault(slot, [])
            for form in forms:
                if form not in bucket:
                    bucket.append(form)
                    total_forms += 1

        out: dict[str, Any] = {
            "lemma": resolved_lemma,
            "pos": resolved_pos,
            "lang": canon_lang,
            "form_count": total_forms,
        }
        out.update(sections)
        return out

    def spellcheck(self, text: str, *, lang: str = "vro", limit: int | None = None) -> dict[str, Any]:
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        result = self.giella.spellcheck(text, lang=canon_lang)
        if not result.get("available"):
            return result
        return _parse_spellcheck_lines(result.get("lines", []), limit=limit)

    def grammar_check(self, text: str, *, lang: str = "vro", limit: int | None = None) -> dict[str, Any]:
        try:
            canon_lang = normalize_giella_lang(lang)
        except ValueError as exc:
            return {"error": "invalid_parameter", "detail": str(exc)}
        result = self.giella.grammar_check(text, lang=canon_lang)
        if not result.get("available"):
            return result
        if "findings" in result:
            findings = result["findings"]
            errors = findings[:_finding_limit(limit)]
            return {"errors": errors, "returned": len(errors), "total_errors": len(findings)}
        return _parse_grammar_lines(result.get("lines", []), limit=limit)

    def check_setup(self) -> dict[str, Any]:
        model_checks = {
            "voyage_4_nano": self._dir_availability(
                "voyage_4_nano",
                self.settings.models_dir / "voyage_4_nano",
                ("config.json", "model.safetensors"),
            ),
            "language_id": self._dir_availability(
                "language_id",
                self.settings.models_dir / "language_id",
                (
                    "ensemble_final_standalone/ensemble.json",
                    "ensemble_final_context/ensemble.json",
                    "xlm_roberta_context/best/model.safetensors",
                    "linear_lbfgs/model.joblib",
                ),
            ),
            "mt_smugri_fp16": self._dir_availability(
                "mt_smugri_fp16",
                self.settings.models_dir / "mt_smugri_fp16",
                ("config.json", "model.safetensors"),
            ),
        }
        resources_ok = all(
            (self.settings.resources_dir / lcode / fname).exists()
            for lcode in SOUTH_ESTONIAN_LANGS
            for fname in CORE_RESOURCE_TOPICS.values()
        )
        rules_ok = all(
            (self.settings.rules_dir / f"{lcode}-leakage-rules.json").exists()
            for lcode in SOUTH_ESTONIAN_LANGS
        )
        detailed = {
            "databases": {
                "south_estonian": self._libsql_availability(
                    "south_estonian",
                    self.settings.south_estonian_db,
                    {
                        "dict_entries": {"id", "lang", "headword", "lookup_key"},
                        "corpus_units": {"id", "unit_id", "lang", "text", "orig_vec"},
                        "corpus_translations": {"id", "lang", "translated_text", "tr_vec"},
                    },
                ),
            },
            "models": model_checks,
            "giella": self.giella.availability(),
            "assets": {
                "resources": {"available": resources_ok, "path": str(self.settings.resources_dir)},
                "rules": {"available": rules_ok, "path": str(self.settings.rules_dir)},
            },
        }
        compact = self._compact_setup(detailed)
        compact["giella_languages"] = {
            lcode: {
                cap: (True if info.get("available") else info)
                for cap, info in caps.items()
            }
            for lcode, caps in self.giella.availability_by_language().items()
        }
        compact["corpus_policy"] = CORPUS_POLICY_ID
        return compact

    @classmethod
    def _libsql_availability(
        cls,
        name: str,
        path: Any,
        required_schema: dict[str, set[str]],
    ) -> dict[str, Any]:
        path_obj = Path(path)
        if not path_obj.exists():
            return cls._db_unavailable(name, path_obj, FileNotFoundError(f"missing database: {path_obj}"))
        try:
            with closing(libsql.connect(str(path_obj))) as conn:
                for table, required_columns in required_schema.items():
                    row = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE name = ? LIMIT 1",
                        (table,),
                    ).fetchone()
                    if row is None:
                        raise RuntimeError(f"missing required table: {table}")
                    columns = {item[1] for item in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                    missing = sorted(required_columns - columns)
                    if missing:
                        raise RuntimeError(f"{table} missing required column(s): {', '.join(missing)}")
                first_table = next(iter(required_schema))
                conn.execute(f"SELECT 1 FROM {first_table} LIMIT 1").fetchone()
        except Exception as exc:
            return cls._db_unavailable(name, path_obj, exc)
        return {"available": True, "path": str(path_obj)}

    @staticmethod
    def _dir_availability(name: str, path: Path, required_files: tuple[str, ...]) -> dict[str, Any]:
        missing = [fname for fname in required_files if not (path / fname).exists()]
        if not path.exists() or missing:
            return {
                "available": False,
                "error": f"{name}_unavailable",
                "path": str(path),
                "missing": missing,
            }
        return {"available": True, "path": str(path)}

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

    @staticmethod
    def _compact_setup(detailed: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        compact: dict[str, dict[str, Any]] = {}
        for group, items in detailed.items():
            compact[group] = {}
            for name, info in items.items():
                compact[group][name] = True if info.get("available") else info
        return compact
