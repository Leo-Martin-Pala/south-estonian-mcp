from __future__ import annotations

import json
import re
import threading
import unicodedata
from contextlib import closing, contextmanager
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterator

import libsql

from .estonian_leakage import SOUTH_ESTONIAN_LANGS, normalize_language_code
from .tokenization import tokenize


_DIRECTION_ALIASES = {
    "en-vro": "en-vro",
    "en_vro": "en-vro",
    "vro-en": "vro-en",
    "vro_en": "vro-en",
    "et-vro": "et-vro",
    "et_vro": "et-vro",
    "vro-et": "vro-et",
    "vro_et": "vro-et",
}

_DIRECTION_PAIRS = {
    "en-vro": ("en", "vro"),
    "et-vro": ("et", "vro"),
    "vro-en": ("vro", "en"),
    "vro-et": ("vro", "et"),
}
PUBLIC_DIRECTIONS = tuple(_DIRECTION_PAIRS)

DEFAULT_SNIPPET_CHARS = 260
MIN_SNIPPET_CHARS = 80
MAX_SNIPPET_CHARS = 1000
_COMBINING_ACUTE = "\u0301"
_PALATALIZABLE = set("bcdfghjklmnpqrstvwxzBCDFGHJKLMNPQRSTVWXZ")


def _limit(value: int | None, default: int = 10, maximum: int = 50) -> int:
    if value is None:
        return default
    return max(1, min(int(value), maximum))


def _snippet_char_limit(value: int | None) -> int:
    if value is None:
        return DEFAULT_SNIPPET_CHARS
    return max(MIN_SNIPPET_CHARS, min(int(value), MAX_SNIPPET_CHARS))


def _document_excerpt(text: str, query: str, limit: int = MAX_SNIPPET_CHARS) -> str:
    if len(text) <= limit:
        return text
    match = re.search(re.escape(query), text, re.IGNORECASE)
    start = max(0, match.start() - limit // 3) if match else 0
    end = start + limit - 2
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def normalize_public_direction(value: str | None) -> str | None:
    if value is None:
        return None
    direction = value.strip().lower().replace(" ", "")
    if not direction:
        return None
    return _DIRECTION_ALIASES.get(direction)


_LOOKUP_STRIP_CHARS = set("\u0300\u0302\u030c\u032c\u0327\u02bc´’'`|+._~")


def normalize_db_text(value: str) -> str:
    """Normalize text for lookup while preserving base characters (strips palatal marks & boundary markers)."""
    text = unicodedata.normalize("NFD", (value or "").strip())
    out: list[str] = []
    for ch in text:
        if ch == _COMBINING_ACUTE and out and out[-1] in _PALATALIZABLE:
            continue
        if ch in _LOOKUP_STRIP_CHARS:
            continue
        out.append(ch)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", "".join(out))).strip().lower()


def _normalise_word(value: str) -> str:
    return normalize_db_text(value)


def _text_words(text: str) -> list[str]:
    return [_normalise_word(token) for token in tokenize(text)]


_GLOSS_WS_RE = re.compile(r"\s+")
_GLOSS_PUNCT_STRIP = " \t\r\n.,;:!?\"'()[]{}«»„”–-"
_FTS_TOKEN_RE = re.compile(r"[^\W\d_]+")

_QUALITY_WARNING_LABELS: tuple[tuple[str, str, int], ...] = (
    ("q_overall", "overall quality concern", 350),
    ("q_meaning", "possible meaning mismatch", 350),
    ("q_omission", "possible omission", 350),
    ("q_addition", "possible addition", 350),
    ("q_facts", "possible number/name mismatch", 350),
    ("q_naturalness", "unnatural phrasing", 350),
    ("q_repetition", "repetition risk", 350),
    ("q_artifacts", "translation system artifacts", 350),
    ("q_intrusion", "Estonian/source intrusion", 350),
    ("q_integrity", "target text integrity issue", 350),
    ("q_uncertain", "high rater uncertainty", 450),
)


def _norm_gloss(text: str) -> str:
    return _GLOSS_WS_RE.sub(" ", text).strip().casefold().strip(_GLOSS_PUNCT_STRIP)


_MATCH_TIER_PRIORITY: dict[str, int] = {
    "headword": 0,
    "inflection": 1,
    "definition": 2,
    "fts": 3,
}
_ARCHIVE_DICT_SLUGS = frozenset({"eki_ems_dictionary", "eki_vms_dictionary"})
WIKIPEDIA_DICTIONARY_SOURCE = "fiu_vrowiki_dictionary"
PUBLIC_SOURCES = json.loads(Path(__file__).with_name("sources-public.json").read_text(encoding="utf-8"))
USAGE_SOURCE_SLUGS = {
    "wiki_article": "fiu_vrowiki",
    "tei_literature": "ilukirjanduskorpus",
    "parallel_corpus_vro_side": "paraleelkorpus",
}


def source_attribution(slug: str, url: str | None = None) -> dict[str, str]:
    source = PUBLIC_SOURCES.get(slug)
    if not source:
        return {}
    return {
        "source_url": url or source["url"],
        "license": source["license"],
        "license_url": source["license_url"],
        "credit": source["credit"],
    }


def _rank_dict_entry(
    entry: dict[str, Any],
    *,
    gloss_key: str,
) -> tuple[int, int, int, int, int, int, int, int, int]:
    """Sort key (ascending = better) for ranking hydrated dictionary entries.

    Relies on Python's stable sort to preserve original SQL order on ties.
    """
    tier = _MATCH_TIER_PRIORITY.get(str(entry.get("matched_via") or "fts"), 3)
    headword = str(entry.get("headword") or "").strip()
    is_punctuated = 0 if headword == headword.strip(_GLOSS_PUNCT_STRIP) else 1

    defs = entry.get("definitions") or []
    exact_def_idx = len(defs) if defs else 9999
    sub_gloss_rank = 2
    min_def_len = 9999
    if defs:
        min_def_len = min(len(str(d.get("text") or "")) for d in defs)
    if gloss_key:
        word_re = re.compile(rf"(?<!\w){re.escape(gloss_key)}(?!\w|-)")
        for idx, d in enumerate(defs):
            raw_txt = str(d.get("text") or "")
            norm_txt = _norm_gloss(raw_txt)
            if norm_txt == gloss_key:
                exact_def_idx = min(exact_def_idx, idx)
                sub_gloss_rank = 0
                break
            parts = [_norm_gloss(p) for p in re.split(r"[;,]", raw_txt) if p.strip()]
            if gloss_key in parts:
                sub_gloss_rank = min(sub_gloss_rank, 0)
            elif word_re.search(raw_txt.casefold()):
                sub_gloss_rank = min(sub_gloss_rank, 1)

    has_localities = 1 if entry.get("localities") else 0
    is_archive = 1 if entry.get("source_slug") in _ARCHIVE_DICT_SLUGS else 0
    richness_penalty = -(
        (1 if entry.get("examples") else 0)
        + (1 if entry.get("inflections") else 0)
        + (1 if entry.get("variants") else 0)
    )
    return (
        tier,
        int(entry.get("source_slug") == WIKIPEDIA_DICTIONARY_SOURCE),
        is_punctuated,
        exact_def_idx,
        sub_gloss_rank,
        min_def_len,
        has_localities,
        is_archive,
        richness_penalty,
    )


def _deduplicate_dict_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate/near-duplicate headwords (e.g. 'imä' vs 'imä,') per language."""
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        key = (
            str(entry.get("lang") or ""),
            _norm_gloss(str(entry.get("headword") or "")),
            str(entry.get("homonym") or ""),
            str(entry["entry_id"]) if entry.get("source_slug") == WIKIPEDIA_DICTIONARY_SOURCE else "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _build_fts_query(query: str, *, use_or: bool = False) -> str:
    tokens = _FTS_TOKEN_RE.findall(query or "")
    if not tokens:
        return ""
    # Deduplicate while preserving order to keep long queries bounded
    seen: list[str] = []
    for tok in tokens:
        low = tok.casefold()
        if low not in seen:
            seen.append(low)
        if len(seen) >= 12:
            break
    sep = " OR " if use_or else " "
    return sep.join(f'"{t}"' for t in seen)


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except json.JSONDecodeError:
            pass
    return [stripped]


_LOW_SIMILARITY_WARNING_THRESHOLD = 0.55


def _vector_rrf_weight(cos_sim: float) -> float:
    """Scale RRF contribution by cosine similarity so weak vector hits don't dilute strong FTS hits."""
    if cos_sim >= 0.55:
        return 1.0
    if cos_sim >= 0.35:
        return 0.25 + 0.75 * ((cos_sim - 0.35) / 0.20)
    return 0.15 * max(0.0, cos_sim / 0.35)


def _coerce_vec_json(vec: str | Any | None) -> str | None:
    if vec is None:
        return None
    if isinstance(vec, str):
        return vec
    if hasattr(vec, "tolist"):
        vec = vec.tolist()
    return json.dumps([float(x) for x in vec])


def _lid_warning(lang: str, lid_lang: str | None, lid_conf: int | None) -> str | None:
    if lid_lang and lid_conf is not None and lid_lang != lang and lid_conf >= 700:
        return f"LID suggests {lid_lang} ({lid_conf / 10:.0f}% confidence)"
    return None


def _translation_warnings(row_vals: dict[str, int | None]) -> list[str]:
    warnings: list[str] = []
    for col, label, threshold in _QUALITY_WARNING_LABELS:
        val = row_vals.get(col)
        if val is not None and val >= threshold:
            warnings.append(f"{label} ({val / 1000:.2f})")
    return warnings


class SouthEstonianStore:
    """Read-only libSQL store for unified South Estonian dictionaries, corpus, parallel examples, and frequencies."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._meta_lock = threading.Lock()
        self._schema_columns: dict[str, set[str]] = {}
        self._marked_dictionary_keys: dict[str, set[str]] | None = None

    def _file_signature(self) -> tuple[int, int]:
        if not self.db_path.exists():
            raise FileNotFoundError(f"South Estonian libSQL database not found: {self.db_path}")
        st = self.db_path.stat()
        return (st.st_mtime_ns, st.st_size)

    def _connect(self) -> libsql.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"South Estonian libSQL database not found: {self.db_path}")
        return libsql.connect(str(self.db_path))

    @contextmanager
    def _connection(self) -> Iterator[libsql.Connection]:
        if "_connect" in self.__dict__:
            with closing(self._connect()) as conn:
                yield conn
            return
        sig = self._file_signature()
        conn: libsql.Connection | None = getattr(self._local, "conn", None)
        cached_sig = getattr(self._local, "sig", None)
        if conn is None or cached_sig != sig:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
                with self._meta_lock:
                    self._schema_columns.clear()
                    self._marked_dictionary_keys = None
            conn = self._connect()
            self._local.conn = conn
            self._local.sig = sig
        yield conn

    def close(self) -> None:
        conn: libsql.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None
            self._local.sig = None

    def _table_columns(self, conn: libsql.Connection, table: str) -> set[str]:
        cached = self._schema_columns.get(table)
        if cached is not None:
            return cached
        with self._meta_lock:
            cached = self._schema_columns.get(table)
            if cached is None:
                cached = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                self._schema_columns[table] = cached
            return cached

    def _corpus_attribution(self, conn: libsql.Connection, slug: str, doc_id: str) -> dict[str, str]:
        if slug not in PUBLIC_SOURCES:
            return {}
        row = None
        if self._table_columns(conn, "corpus_documents"):
            row = conn.execute(
                "SELECT title, author, source_url FROM corpus_documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        attribution = source_attribution(slug, row[2] if row else None)
        if row and row[0]:
            attribution["title"] = row[0]
        if row and row[1]:
            attribution["author"] = row[1]
        return attribution

    def _dictionary_lookup_keys(self, conn: libsql.Connection, key: str) -> list[str]:
        """Include marked keys from older datasets without altering source spellings.

        Cache only the exceptional keys; subsequent lookups still use the normal
        dictionary indexes.
        """
        marked = self._marked_dictionary_keys
        if marked is None:
            with self._meta_lock:
                marked = self._marked_dictionary_keys
                if marked is None:
                    aliases: dict[str, set[str]] = {}
                    for table in ("dict_entries", "dict_inflections"):
                        for (stored_key,) in conn.execute(
                            f"SELECT DISTINCT lookup_key FROM {table} WHERE instr(lookup_key, ?) > 0",
                            ("\u032c",),
                        ).fetchall():
                            aliases.setdefault(normalize_db_text(stored_key), set()).add(stored_key)
                    self._marked_dictionary_keys = aliases
                    marked = aliases
        return [key, *sorted(marked.get(key, set()) - {key})]

    def _normalize_lang(self, lang: str | None) -> str | None:
        if lang is None or not str(lang).strip():
            return None
        return normalize_language_code(lang, default=None)

    def _hydrate_dict_entries(
        self,
        conn: libsql.Connection,
        entry_rows: list[tuple[Any, ...]],
        *,
        target_lang: str | None = None,
        include_inflections: bool = True,
        include_examples: bool = True,
        include_raw: bool = False,
        include_evidence: bool = False,
        match_meta: dict[int, tuple[str, str | None]] | None = None,
    ) -> list[dict[str, Any]]:
        if not entry_rows:
            return []
        rowids = [int(r[0]) for r in entry_rows]
        placeholders = ",".join("?" for _ in rowids)
        tgt_norm = target_lang.casefold().strip() if target_lang and target_lang.strip() else None

        defs_by_entry: dict[int, list[dict[str, Any]]] = {rid: [] for rid in rowids}
        def_columns = self._table_columns(conn, "dict_definitions")
        evidence_column = "source_evidence" if "source_evidence" in def_columns else "NULL"
        def_sql = (
            f"SELECT entry_rowid, target_lang, definition_text, sense, {evidence_column} "
            f"FROM dict_definitions WHERE entry_rowid IN ({placeholders})"
        )
        def_params: list[Any] = list(rowids)
        if tgt_norm:
            def_sql += " AND target_lang = ?"
            def_params.append(tgt_norm)
        def_sql += " ORDER BY id"
        for erid, dtgt, dtext, sense, evidence in conn.execute(def_sql, tuple(def_params)).fetchall():
            item: dict[str, Any] = {"target_lang": dtgt, "text": dtext}
            if sense:
                item["sense"] = sense
            if evidence:
                item["source_evidence"] = _parse_json_list(evidence)
            defs_by_entry[int(erid)].append(item)

        lang_by_entry = {int(r[0]): r[2] for r in entry_rows}
        infl_by_entry: dict[int, list[dict[str, Any]]] = {rid: [] for rid in rowids}
        infl_totals: dict[int, int] = {rid: 0 for rid in rowids}
        raw_infl_by_entry: dict[int, list[str]] = {rid: [] for rid in rowids}
        raw_infl_seen: dict[int, set[str]] = {rid: set() for rid in rowids}
        if include_inflections or include_raw:
            # Older released datasets lack source evidence columns.
            infl_columns = self._table_columns(conn, "dict_inflections")
            raw_column = "raw_text" if "raw_text" in infl_columns else "NULL"
            metadata_column = "metadata_json" if (include_evidence and "metadata_json" in infl_columns) else "NULL"
            for erid, form, gtag, notation, raw, metadata_json in conn.execute(
                f"SELECT entry_rowid, form, grammatical_tag, notation, {raw_column}, {metadata_column} "
                f"FROM dict_inflections WHERE entry_rowid IN ({placeholders}) ORDER BY id",
                tuple(rowids),
            ).fetchall():
                erid_int = int(erid)
                if raw:
                    raw_str = str(raw).strip()
                    if raw_str and raw_str not in raw_infl_seen[erid_int]:
                        raw_infl_seen[erid_int].add(raw_str)
                        raw_infl_by_entry[erid_int].append(raw_str)
                if include_raw or not include_inflections:
                    continue
                bucket = infl_by_entry[erid_int]
                infl_totals[erid_int] += 1
                if len(bucket) >= 35:
                    continue
                item = {"form": form}
                if gtag:
                    item["grammatical_tag"] = gtag
                if notation and (lang_by_entry.get(erid_int) == "lutsi" or notation != "practical"):
                    item["notation"] = notation
                if include_evidence:
                    if raw:
                        item["raw"] = raw
                    if metadata_json:
                        source_fields = json.loads(metadata_json)
                        if isinstance(source_fields, dict):
                            item["source_details"] = source_fields
                bucket.append(item)

        raw_entry_by_id: dict[int, str] = {}
        if include_raw:
            entry_columns = self._table_columns(conn, "dict_entries")
            raw_entry_col = next((c for c in ("raw_entry", "raw_text") if c in entry_columns), None)
            if raw_entry_col:
                for erid, raw_val in conn.execute(
                    f"SELECT id, {raw_entry_col} FROM dict_entries WHERE id IN ({placeholders})",
                    tuple(rowids),
                ).fetchall():
                    if raw_val and str(raw_val).strip():
                        raw_entry_by_id[int(erid)] = str(raw_val).strip()

        ex_by_entry: dict[int, list[dict[str, Any]]] = {rid: [] for rid in rowids}
        needs_examples_for_raw = include_raw and any(int(r[0]) not in raw_entry_by_id for r in entry_rows)
        if include_examples or needs_examples_for_raw:
            try:
                for erid, src_txt, tr_txt, ex_tgt, loc in conn.execute(
                    f"SELECT entry_rowid, source_text, target_text, target_lang, locality "
                    f"FROM dict_examples WHERE entry_rowid IN ({placeholders}) ORDER BY id",
                    tuple(rowids),
                ).fetchall():
                    bucket = ex_by_entry[int(erid)]
                    if len(bucket) >= 12:
                        continue
                    item = {"source_text": src_txt}
                    if tr_txt:
                        item["target_text"] = tr_txt
                    if ex_tgt:
                        item["target_lang"] = ex_tgt
                    if loc:
                        item["locality"] = loc
                    bucket.append(item)
            except Exception:
                pass

        results: list[dict[str, Any]] = []
        for erid, entry_id, lang, headword, _lk, homonym, pos, infl_type, variants, localities, xref, notes, src_slug, src_url in entry_rows:
            erid_i = int(erid)
            defs = defs_by_entry.get(erid_i, [])
            if tgt_norm and not defs:
                continue
            archived_article = ""
            if src_slug == "synaq" and notes:
                note_prefix, archive_marker, archive_text = notes.partition(" | Synaq archived article: ")
                if archive_marker:
                    notes, archived_article = note_prefix, archive_text
                elif notes.startswith("Synaq archived article: "):
                    notes, archived_article = None, notes.removeprefix("Synaq archived article: ")
            if include_raw:
                raw_entry = raw_entry_by_id.get(erid_i) or archived_article
                if not raw_entry:
                    parts: list[str] = [headword]
                    raw_infls = raw_infl_by_entry.get(erid_i, [])
                    if raw_infls:
                        parts.append(f"<{'; '.join(raw_infls)}>")
                    if defs:
                        parts.append("; ".join(d["text"] for d in defs))
                    exs = ex_by_entry.get(erid_i, [])
                    if exs:
                        ex_strs = [
                            f"{ex['source_text']} — {ex['target_text']}" if ex.get("target_text") else ex["source_text"]
                            for ex in exs
                        ]
                        parts.append(" | ".join(ex_strs))
                    raw_entry = " ".join(parts)
                raw_result: dict[str, Any] = {
                    "entry_id": entry_id,
                    "lang": lang,
                    "headword": headword,
                    "source_slug": src_slug,
                    "raw_entry": raw_entry,
                }
                if raw_infl_by_entry[erid_i]:
                    raw_result["raw_inflections"] = raw_infl_by_entry[erid_i]
                results.append(raw_result)
                continue
            payload: dict[str, Any] = {
                "entry_id": entry_id,
                "lang": lang,
                "headword": headword,
                "definitions": defs,
                "source_slug": src_slug,
            }
            if pos:
                payload["pos"] = pos
            if homonym:
                payload["homonym"] = homonym
            if infl_type:
                payload["inflection_type"] = infl_type
            var_list = _parse_json_list(variants)
            if var_list:
                payload["variants"] = var_list
            loc_list = _parse_json_list(localities)
            if loc_list:
                payload["localities"] = loc_list
            xref_list = _parse_json_list(xref)
            if xref_list:
                payload["cross_references"] = xref_list
            if notes:
                payload["notes"] = notes
            payload.update(source_attribution(src_slug, src_url))
            if src_url:
                payload["source_url"] = src_url
            if include_inflections and infl_by_entry.get(erid_i):
                payload["inflections"] = infl_by_entry[erid_i]
                if infl_totals[erid_i] > len(infl_by_entry[erid_i]):
                    payload["inflections_total"] = infl_totals[erid_i]
                    payload["inflections_truncated"] = True
            if raw_infl_by_entry.get(erid_i):
                payload["raw_inflections"] = raw_infl_by_entry[erid_i]
            if include_examples and ex_by_entry.get(erid_i):
                payload["examples"] = ex_by_entry[erid_i]
            if match_meta and erid_i in match_meta:
                via, mform = match_meta[erid_i]
                payload["matched_via"] = via
                if mform:
                    payload["matched_form"] = mform
            results.append(payload)
        return results

    def lookup_words(
        self,
        words: str | list[str],
        *,
        lang: str | None = None,
        target_lang: str | None = None,
        include_inflections: bool = True,
        include_examples: bool = True,
        include_raw: bool = False,
        limit: int = 10,
        source_slug: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        cleaned = [str(w).strip() for w in ([words] if isinstance(words, str) else words) if str(w).strip()]
        if not cleaned:
            return {}
        norm_lang = self._normalize_lang(lang)
        tgt_norm = target_lang.casefold().strip() if target_lang and target_lang.strip() else None
        source = (source_slug or "").strip()
        related_source_filter = (
            " AND EXISTS (SELECT 1 FROM dict_entries e WHERE e.id = entry_rowid AND e.source_slug = ?)"
            if source else ""
        )
        effective_limit = max(1, min(int(limit), 50))
        pool_limit = min(max(effective_limit * 4, 24), 120)
        out: dict[str, list[dict[str, Any]]] = {}

        with self._connection() as conn:
            for term in cleaned:
                key = normalize_db_text(term)
                lookup_keys = self._dictionary_lookup_keys(conn, key)
                key_placeholders = ",".join("?" for _ in lookup_keys)
                gloss_key = _norm_gloss(term)
                ranked_rowids: list[int] = []
                seen_rowids: set[int] = set()
                match_meta: dict[int, tuple[str, str | None]] = {}

                def _add_ids(rows: list[tuple[Any, ...]], via: str) -> None:
                    for r in rows:
                        rid = int(r[0])
                        if rid in seen_rowids:
                            continue
                        seen_rowids.add(rid)
                        ranked_rowids.append(rid)
                        mform = str(r[1]) if len(r) > 1 and r[1] is not None else None
                        match_meta[rid] = (via, mform)
                        if len(ranked_rowids) >= pool_limit:
                            break

                # 1. Exact headword lookup_key
                sql_hw = f"SELECT id, NULL FROM dict_entries WHERE lookup_key IN ({key_placeholders})"
                params_hw: list[Any] = list(lookup_keys)
                if norm_lang:
                    sql_hw += " AND lang = ?"
                    params_hw.append(norm_lang)
                if source:
                    sql_hw += " AND source_slug = ?"
                    params_hw.append(source)
                sql_hw += " ORDER BY lang, id LIMIT ?"
                params_hw.append(pool_limit)
                _add_ids(conn.execute(sql_hw, tuple(params_hw)).fetchall(), "headword")

                # 2. Inflected forms (e.g. UPA & practical paradigms, inflections)
                if len(ranked_rowids) < pool_limit and key:
                    sql_inf = f"SELECT entry_rowid, form FROM dict_inflections WHERE lookup_key IN ({key_placeholders})"
                    params_inf: list[Any] = list(lookup_keys)
                    if norm_lang:
                        sql_inf += " AND lang = ?"
                        params_inf.append(norm_lang)
                    if source:
                        sql_inf += related_source_filter
                        params_inf.append(source)
                    sql_inf += " ORDER BY id LIMIT ?"
                    params_inf.append(pool_limit)
                    _add_ids(conn.execute(sql_inf, tuple(params_inf)).fetchall(), "inflection")

                # 3. Reverse lookup by exact normalized gloss
                if len(ranked_rowids) < pool_limit and gloss_key:
                    sql_def = "SELECT entry_rowid, definition_text FROM dict_definitions WHERE norm_def = ?"
                    params_def: list[Any] = [gloss_key]
                    if norm_lang:
                        sql_def += " AND lang = ?"
                        params_def.append(norm_lang)
                    if tgt_norm:
                        sql_def += " AND target_lang = ?"
                        params_def.append(tgt_norm)
                    if source:
                        sql_def += related_source_filter
                        params_def.append(source)
                    sql_def += " ORDER BY id LIMIT ?"
                    params_def.append(pool_limit)
                    _add_ids(conn.execute(sql_def, tuple(params_def)).fetchall(), "definition")

                # 4. FTS5 fallback if still short
                if len(ranked_rowids) < effective_limit * 2:
                    fts_q = _build_fts_query(term)
                    if fts_q:
                        sql_fts = "SELECT entry_rowid, NULL FROM dict_fts WHERE dict_fts MATCH ?"
                        params_fts: list[Any] = [fts_q]
                        if norm_lang:
                            sql_fts += " AND lang = ?"
                            params_fts.append(norm_lang)
                        if source:
                            sql_fts += related_source_filter
                            params_fts.append(source)
                        sql_fts += " ORDER BY bm25(dict_fts) LIMIT ?"
                        params_fts.append(pool_limit)
                        _add_ids(conn.execute(sql_fts, tuple(params_fts)).fetchall(), "fts")

                if not ranked_rowids:
                    out[term] = []
                    continue

                ph = ",".join("?" for _ in ranked_rowids)
                raw_map = {
                    int(row[0]): row
                    for row in conn.execute(
                        f"SELECT id, entry_id, lang, headword, lookup_key, homonym, pos, inflection_type, variants, localities, cross_references, notes, source_slug, source_url "
                        f"FROM dict_entries WHERE id IN ({ph})",
                        tuple(ranked_rowids),
                    ).fetchall()
                }
                ordered_rows = [raw_map[rid] for rid in ranked_rowids if rid in raw_map]
                hydrated = self._hydrate_dict_entries(
                    conn,
                    ordered_rows,
                    target_lang=tgt_norm,
                    include_inflections=include_inflections,
                    include_examples=include_examples,
                    include_raw=include_raw,
                    match_meta=match_meta,
                )
                ranked = sorted(hydrated, key=lambda e: _rank_dict_entry(e, gloss_key=gloss_key))
                results = ranked if include_raw else _deduplicate_dict_entries(ranked)
                out[term] = results[:effective_limit]
        return out

    def lookup_word(
        self,
        word: str,
        *,
        lang: str | None = None,
        target_lang: str | None = None,
        include_inflections: bool = True,
        include_examples: bool = True,
        include_raw: bool = False,
        limit: int = 10,
        source_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        cleaned = word.strip()
        if not cleaned:
            return []
        return self.lookup_words(
            [cleaned],
            lang=lang,
            target_lang=target_lang,
            include_inflections=include_inflections,
            include_examples=include_examples,
            include_raw=include_raw,
            limit=limit,
            source_slug=source_slug,
        ).get(cleaned, [])

    def search_dictionary_semantic(
        self,
        query_vec: str | Any,
        *,
        query_text: str | None = None,
        lang: str | None = None,
        target_lang: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        vec_json = _coerce_vec_json(query_vec)
        if not vec_json and not query_text:
            raise ValueError("Provide a query vector or lexical query.")
        norm_lang = self._normalize_lang(lang)
        tgt_norm = target_lang.casefold().strip() if target_lang and target_lang.strip() else None
        effective_limit = max(1, min(int(limit), 50))
        overfetch = max(effective_limit * 20, 200) if (norm_lang or tgt_norm) else max(effective_limit * 10, 120)

        def _dedup_vec_rows(
            raw_rows: list[tuple[Any, ...]],
        ) -> list[tuple[int, str, str, str | None, float]]:
            seen: set[int] = set()
            deduped: list[tuple[int, str, str, str | None, float]] = []
            for erid, _l, dtgt, dtext, sense, dist in raw_rows:
                erid_i = int(erid)
                if erid_i in seen:
                    continue
                seen.add(erid_i)
                deduped.append((erid_i, dtgt, dtext, sense, max(0.0, 1.0 - float(dist))))
            return deduped

        with self._connection() as conn:
            vec_entries = []
            if vec_json:
                filters = ["dd.def_vec IS NOT NULL"]
                params: list[Any] = [vec_json, vec_json, overfetch]
                if norm_lang:
                    filters.append("dd.lang = ?")
                    params.append(norm_lang)
                if tgt_norm:
                    filters.append("dd.target_lang = ?")
                    params.append(tgt_norm)
                params.append(max(effective_limit * 5, 50))
                where_sql = " AND ".join(filters)
                rows = conn.execute(
                    f"""
                    SELECT dd.entry_rowid, dd.lang, dd.target_lang, dd.definition_text, dd.sense,
                           vector_distance_cos(dd.def_vec, vector8(?)) AS dist
                    FROM vector_top_k('idx_dict_def_vec', vector8(?), ?) AS vt
                    JOIN dict_definitions dd ON dd.id = vt.id
                    WHERE {where_sql}
                    ORDER BY dist ASC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
                vec_entries = _dedup_vec_rows(rows)

                # Fallback exact scan within filtered slice if DiskANN top-k starved a low-resource
                # language or polysemous entries collapsed below effective_limit after deduplication.
                if len(vec_entries) < effective_limit and (norm_lang or tgt_norm):
                    fb_filters = ["def_vec IS NOT NULL"]
                    fb_params: list[Any] = [vec_json]
                    if norm_lang:
                        fb_filters.append("lang = ?")
                        fb_params.append(norm_lang)
                    if tgt_norm:
                        fb_filters.append("target_lang = ?")
                        fb_params.append(tgt_norm)
                    fb_params.append(max(effective_limit * 5, 50))
                    fb_rows = conn.execute(
                        f"""
                        SELECT entry_rowid, lang, target_lang, definition_text, sense,
                               vector_distance_cos(def_vec, vector8(?)) AS dist
                        FROM dict_definitions
                        WHERE {' AND '.join(fb_filters)}
                        ORDER BY dist ASC
                        LIMIT ?
                        """,
                        tuple(fb_params),
                    ).fetchall()
                    vec_entries = _dedup_vec_rows(fb_rows)

            # Optional FTS5 lexical channel when query_text is provided (hybrid RRF)
            fts_entries: list[tuple[int, str, str, str | None]] = []
            cleaned_q = (query_text or "").strip()
            if cleaned_q:
                fts_raw: list[tuple[Any, ...]] = []
                for use_or in (False, True):
                    fts_q = _build_fts_query(cleaned_q, use_or=use_or)
                    if not fts_q:
                        break
                    fts_sql = (
                        "SELECT entry_rowid, definition_text, bm25(dict_fts) AS rank "
                        "FROM dict_fts WHERE dict_fts MATCH ?"
                    )
                    fts_params: list[Any] = [fts_q]
                    if norm_lang:
                        fts_sql += " AND lang = ?"
                        fts_params.append(norm_lang)
                    fts_sql += " ORDER BY rank ASC LIMIT ?"
                    fts_params.append(max(effective_limit * 5, 50))
                    fts_raw = conn.execute(fts_sql, tuple(fts_params)).fetchall()
                    if fts_raw or use_or:
                        break

                if fts_raw:
                    fts_order: list[tuple[int, str]] = []
                    seen_fts: set[int] = set()
                    for erid, dtext, _rank in fts_raw:
                        erid_i = int(erid)
                        if erid_i in seen_fts:
                            continue
                        seen_fts.add(erid_i)
                        fts_order.append((erid_i, str(dtext or "")))
                    ph_fts = ",".join("?" for _ in fts_order)
                    def_sql = (
                        f"SELECT entry_rowid, target_lang, definition_text, sense "
                        f"FROM dict_definitions WHERE entry_rowid IN ({ph_fts})"
                    )
                    def_params: list[Any] = [erid_i for erid_i, _ in fts_order]
                    if tgt_norm:
                        def_sql += " AND target_lang = ?"
                        def_params.append(tgt_norm)
                    def_sql += " ORDER BY id"
                    defs_by_erid: dict[int, list[tuple[str, str, str | None]]] = {}
                    for erid, dtgt, dtext, sense in conn.execute(def_sql, tuple(def_params)).fetchall():
                        defs_by_erid.setdefault(int(erid), []).append((dtgt, dtext, sense))
                    for erid_i, matched_dtext in fts_order:
                        cand_defs = defs_by_erid.get(erid_i)
                        if not cand_defs:
                            continue
                        chosen_def = next((d for d in cand_defs if d[1] == matched_dtext), cand_defs[0])
                        fts_entries.append((erid_i, chosen_def[0], chosen_def[1], chosen_def[2]))

            # Fuse vector and FTS channels with confidence-weighted RRF
            fused: dict[int, dict[str, Any]] = {}
            rrf_scores: dict[int, float] = {}
            for rank_i, (erid_i, dtgt, dtext, sense, cos_sim) in enumerate(vec_entries):
                rrf_scores[erid_i] = rrf_scores.get(erid_i, 0.0) + (
                    _vector_rrf_weight(cos_sim) / (60.0 + rank_i + 1)
                )
                fused[erid_i] = {
                    "target_lang": dtgt,
                    "definition": dtext,
                    "sense": sense,
                    "vector_score": cos_sim,
                    "match": "vector",
                }
            for rank_i, (erid_i, dtgt, dtext, sense) in enumerate(fts_entries):
                rrf_scores[erid_i] = rrf_scores.get(erid_i, 0.0) + (1.0 / (60.0 + rank_i + 1))
                if erid_i in fused:
                    fused[erid_i]["match"] = "hybrid"
                else:
                    fused[erid_i] = {
                        "target_lang": dtgt,
                        "definition": dtext,
                        "sense": sense,
                        "match": "fts",
                    }

            if not fused:
                return []

            has_fts = bool(fts_entries)
            top_erids = sorted(fused.keys(), key=lambda r: rrf_scores[r], reverse=True)[:effective_limit]
            ph = ",".join("?" for _ in top_erids)
            url_column = "source_url" if "source_url" in self._table_columns(conn, "dict_entries") else "NULL"
            entry_map = {
                int(r[0]): r
                for r in conn.execute(
                    f"SELECT id, entry_id, lang, headword, pos, source_slug, {url_column} FROM dict_entries WHERE id IN ({ph})",
                    tuple(top_erids),
                ).fetchall()
            }
            out: list[dict[str, Any]] = []
            for erid_i in top_erids:
                erow = entry_map.get(erid_i)
                if erow is None:
                    continue
                meta = fused[erid_i]
                _id, entry_id, elang, hw, pos, src_slug, src_url = erow
                vec_score = meta.get("vector_score")
                score_val = (
                    round(rrf_scores[erid_i], 5)
                    if has_fts
                    else round(float(vec_score or 0.0), 4)
                )
                item: dict[str, Any] = {
                    "entry_id": entry_id,
                    "lang": elang,
                    "headword": hw,
                    "target_lang": meta["target_lang"],
                    "definition": meta["definition"],
                    "score": score_val,
                    "match": meta["match"],
                    "source_slug": src_slug,
                    **source_attribution(src_slug, src_url),
                }
                if vec_score is not None:
                    item["vector_score"] = round(float(vec_score), 4)
                if meta["match"] == "vector" and vec_score is not None and float(vec_score) < _LOW_SIMILARITY_WARNING_THRESHOLD:
                    item["warnings"] = [
                        f"low semantic similarity ({float(vec_score):.2f}); no exact lexical match"
                    ]
                if pos:
                    item["pos"] = pos
                if meta["sense"]:
                    item["sense"] = meta["sense"]
                out.append(item)
            return out

    def find_cognates(
        self,
        word: str | None = None,
        *,
        lang: str | None = None,
        concept: str | None = None,
        limit: int = 15,
    ) -> dict[str, Any]:
        norm_lang = self._normalize_lang(lang)
        effective_limit = max(1, min(int(limit), 30))
        with self._connection() as conn:
            concepts: list[tuple[str, str]] = []
            seen_concepts: set[tuple[str, str]] = set()

            if word and word.strip():
                key = normalize_db_text(word.strip())
                entry_ids: list[int] = []
                sql_e = "SELECT id FROM dict_entries WHERE lookup_key = ?"
                pe: list[Any] = [key]
                if norm_lang:
                    sql_e += " AND lang = ?"
                    pe.append(norm_lang)
                entry_ids.extend(int(r[0]) for r in conn.execute(sql_e, tuple(pe)).fetchall())

                if not entry_ids and key:
                    sql_i = "SELECT DISTINCT entry_rowid FROM dict_inflections WHERE lookup_key = ?"
                    pi: list[Any] = [key]
                    if norm_lang:
                        sql_i += " AND lang = ?"
                        pi.append(norm_lang)
                    entry_ids.extend(int(r[0]) for r in conn.execute(sql_i, tuple(pi)).fetchall())

                if entry_ids:
                    ph = ",".join("?" for _ in entry_ids)
                    for ck, cl in conn.execute(
                        f"SELECT DISTINCT concept_key, concept_lang FROM dict_cognates WHERE entry_rowid IN ({ph}) LIMIT ?",
                        (*entry_ids, effective_limit),
                    ).fetchall():
                        pair = (ck, cl)
                        if pair not in seen_concepts:
                            seen_concepts.add(pair)
                            concepts.append(pair)

                # Also check if caller passed an Estonian/English concept word directly in `word`
                gkey = _norm_gloss(word.strip())
                if not concepts and gkey:
                    for ck, cl in conn.execute(
                        "SELECT DISTINCT concept_key, concept_lang FROM dict_cognates WHERE concept_key = ? LIMIT ?",
                        (gkey, effective_limit),
                    ).fetchall():
                        pair = (ck, cl)
                        if pair not in seen_concepts:
                            seen_concepts.add(pair)
                            concepts.append(pair)

            if concept and concept.strip():
                gkey = _norm_gloss(concept.strip())
                for ck, cl in conn.execute(
                    "SELECT DISTINCT concept_key, concept_lang FROM dict_cognates WHERE concept_key = ? LIMIT ?",
                    (gkey, effective_limit),
                ).fetchall():
                    pair = (ck, cl)
                    if pair not in seen_concepts:
                        seen_concepts.add(pair)
                        concepts.append(pair)
                if not concepts and gkey:
                    for ck, cl in conn.execute(
                        "SELECT DISTINCT concept_key, concept_lang FROM dict_cognates WHERE concept_key LIKE ? LIMIT ?",
                        (f"%{gkey}%", effective_limit),
                    ).fetchall():
                        pair = (ck, cl)
                        if pair not in seen_concepts:
                            seen_concepts.add(pair)
                            concepts.append(pair)

            groups: list[dict[str, Any]] = []
            _STEM_SKELETON_TRANS = str.maketrans({
                "g": "k",
                "b": "p",
                "d": "t",
                "ä": "a",
                "ö": "o",
                "ü": "u",
                "õ": "o",
                "w": "v",
                "q": "",
            })

            def _stem_norm(hw_str: str) -> str:
                s = normalize_db_text(hw_str)
                return re.sub(r"[\s.\-'()]", "", s)

            def _stem_skeleton(stem: str) -> str:
                # Fold common South Estonian / Finnic sound correspondences:
                # optional initial h- (hõbõh/õbe), voiced/voiceless stops, vowel harmony.
                s = stem.translate(_STEM_SKELETON_TRANS)
                if len(s) >= 3 and s.startswith("h"):
                    s = s[1:]
                return s

            def _stem_similar(a: str, b: str) -> bool:
                if not a or not b:
                    return False
                if a == b:
                    return True
                sa, sb = _stem_skeleton(a), _stem_skeleton(b)
                if sa == sb:
                    return True
                min_len = min(len(sa), len(sb))
                if min_len < 2:
                    return False
                # Match on onset (either raw first 2 chars or correspondence-folded first 2 chars)
                # or strong whole-stem similarity for short roots with onset vowel/h shifts.
                onset_match = (len(a) >= 2 and len(b) >= 2 and a[:2] == b[:2]) or (sa[:2] == sb[:2])
                ratio = max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, sa, sb).ratio())
                if onset_match:
                    return ratio >= (0.50 if min_len <= 5 else 0.62)
                return min_len >= 3 and ratio >= 0.72

            for ck, cl in concepts[:effective_limit]:
                by_lang: dict[str, list[dict[str, Any]]] = {}
                for rlang, headword, pos, dtext, entry_id, src_slug in conn.execute(
                    "SELECT dc.lang, dc.headword, dc.pos, dc.definition_text, de.entry_id, de.source_slug "
                    "FROM dict_cognates dc "
                    "LEFT JOIN dict_entries de ON de.id = dc.entry_rowid "
                    "WHERE dc.concept_key = ? AND dc.concept_lang = ? ORDER BY dc.lang, dc.id",
                    (ck, cl),
                ).fetchall():
                    item: dict[str, Any] = {"headword": headword, "definition": dtext}
                    if pos:
                        item["pos"] = pos
                    if entry_id:
                        item["entry_id"] = entry_id
                    if src_slug:
                        item["source_slug"] = src_slug
                        item.update(source_attribution(src_slug))
                    by_lang.setdefault(rlang, []).append(item)
                if by_lang:
                    # Find stems attested in >= 2 languages (or matching query_word)
                    anchor_stems: list[str] = []
                    if word and word.strip():
                        q_stem = _stem_norm(word.strip())
                        if q_stem:
                            anchor_stems.append(q_stem)
                    lang_stems: list[tuple[str, str]] = [
                        (rlang, _stem_norm(it["headword"]))
                        for rlang, items in by_lang.items()
                        for it in items
                    ]
                    for i, (l1, s1) in enumerate(lang_stems):
                        if any(l2 != l1 and _stem_similar(s1, s2) for l2, s2 in lang_stems[i + 1 :]):
                            anchor_stems.append(s1)

                    cognates_by_lang: dict[str, list[dict[str, Any]]] = {}
                    semantic_by_lang: dict[str, list[dict[str, Any]]] = {}
                    for rlang, items in by_lang.items():
                        for it in items:
                            st = _stem_norm(it["headword"])
                            if anchor_stems and any(_stem_similar(st, anc) for anc in anchor_stems):
                                cognates_by_lang.setdefault(rlang, []).append(it)
                            else:
                                semantic_by_lang.setdefault(rlang, []).append(it)

                    group_obj: dict[str, Any] = {
                        "concept": ck,
                        "concept_lang": cl,
                        "language_count": len(by_lang),
                    }
                    if cognates_by_lang:
                        group_obj["cognates"] = cognates_by_lang
                    if semantic_by_lang:
                        group_obj["semantic_equivalents"] = semantic_by_lang
                    groups.append(group_obj)
            return {
                "query_word": word.strip() if word else None,
                "query_concept": concept.strip() if concept else None,
                "lang_filter": norm_lang,
                "concept_count": len(groups),
                "cognate_sets": groups,
            }

    def get_word_usage_examples(
        self,
        word: str,
        *,
        lang: str | None = None,
        limit: int = 10,
        max_snippet_chars: int | None = None,
        expand_inflections: bool = False,
    ) -> dict[str, Any]:
        cleaned = word.strip()
        if not cleaned:
            return {"word": "", "frequencies": [], "examples": []}
        norm_lang = self._normalize_lang(lang)
        key = normalize_db_text(cleaned)
        effective_limit = max(1, min(int(limit), 30))
        snippet_limit = _snippet_char_limit(max_snippet_chars) if max_snippet_chars is not None else None

        with self._connection() as conn:
            result = self._word_form_usage(
                conn, cleaned, key, norm_lang, effective_limit, snippet_limit,
                mark_matches=expand_inflections,
            )
            if not expand_inflections or not key or (effective_limit == 1 and result["examples"]):
                return result

            lookup_keys = self._dictionary_lookup_keys(conn, key)
            placeholders = ",".join("?" for _ in lookup_keys)
            sql = (
                "SELECT de.lang, di.form, di.lookup_key "
                "FROM dict_entries de JOIN dict_inflections di ON di.entry_rowid = de.id "
                f"WHERE de.lookup_key IN ({placeholders}) AND di.lookup_key <> ''"
            )
            params = list(lookup_keys)
            if norm_lang:
                sql += " AND de.lang = ?"
                params.append(norm_lang)
            sql += " ORDER BY de.lang, di.id"

            # Give each form a chance before filling remaining slots with more
            # examples of the forms already searched.
            direct = result["examples"]
            examples = direct[:1]
            remaining = direct[1:]
            seen_units = {ex["unit_id"] for ex in examples}
            seen_forms: set[tuple[str, str]] = set()
            for form_lang, form, form_key in conn.execute(sql, tuple(params)).fetchall():
                if normalize_db_text(form_key) == key or (form_lang, form_key) in seen_forms:
                    continue
                seen_forms.add((form_lang, form_key))
                usage = self._word_form_usage(
                    conn, form, form_key, form_lang, effective_limit, snippet_limit,
                    mark_matches=True,
                )
                new_examples = [ex for ex in usage["examples"] if ex["unit_id"] not in seen_units]
                if new_examples:
                    first, *rest = new_examples
                    examples.append(first)
                    seen_units.add(first["unit_id"])
                    remaining.extend(rest)
                    if len(examples) >= effective_limit:
                        break

            for ex in remaining:
                if len(examples) >= effective_limit:
                    break
                if ex["unit_id"] not in seen_units:
                    examples.append(ex)
                    seen_units.add(ex["unit_id"])
            result["examples"] = examples
            return result

    def _word_form_usage(
        self,
        conn: libsql.Connection,
        cleaned: str,
        key: str,
        norm_lang: str | None,
        effective_limit: int,
        snippet_limit: int | None,
        *,
        mark_matches: bool = False,
    ) -> dict[str, Any]:
        wf_sql = (
            "SELECT lang, form, freq, lemma_et, pos, morph, example_unit_id, sources_json "
            "FROM word_frequencies WHERE lookup_key = ?"
        )
        wf_params: list[Any] = [key]
        if norm_lang:
            wf_sql += " AND lang = ?"
            wf_params.append(norm_lang)
        wf_sql += " ORDER BY freq DESC LIMIT 20"

        frequencies: list[dict[str, Any]] = []
        seed_unit_ids: list[str] = []
        for wlang, form, freq, lemma_et, pos, morph, ex_uid, srcs_json in conn.execute(wf_sql, tuple(wf_params)).fetchall():
            item: dict[str, Any] = {"lang": wlang, "form": form, "freq": int(freq)}
            if lemma_et:
                item["lemma_et"] = lemma_et
            if pos:
                item["pos"] = pos
            if morph:
                item["morph"] = morph
            srcs = _parse_json_list(srcs_json)
            if srcs:
                item["sources"] = srcs
            frequencies.append(item)
            if ex_uid and ex_uid not in seed_unit_ids:
                seed_unit_ids.append(ex_uid)

        examples: list[dict[str, Any]] = []
        seen_units: set[str] = set()
        match_text = " ".join(_text_words(unicodedata.normalize("NFC", cleaned).replace("\u032c", "")))

        def add_example(
            uid: str, lang: str, unit_level: str, source_slug: str, text: str,
            lid_lang: str | None, lid_conf: int | None, doc_id: str,
        ) -> None:
            if uid in seen_units:
                return
            snippet = str(text or "").strip()
            if mark_matches:
                corpus_words = " ".join(_text_words(unicodedata.normalize("NFC", snippet).replace("\u032c", "")))
                if not match_text or f" {match_text} " not in f" {corpus_words} ":
                    return
                if norm_lang and lang != norm_lang:
                    return
            if unit_level == "document":
                snippet = _document_excerpt(snippet, cleaned, snippet_limit or MAX_SNIPPET_CHARS)
            elif snippet_limit is not None and len(snippet) > snippet_limit:
                snippet = snippet[:snippet_limit].rstrip() + "…"
            ex: dict[str, Any] = {
                "unit_id": uid,
                "lang": lang,
                "unit_level": unit_level,
                "source_slug": source_slug,
                "text": snippet,
                **self._corpus_attribution(conn, source_slug, doc_id),
            }
            if mark_matches:
                ex["matched_form"] = cleaned
            warn = _lid_warning(lang, lid_lang, lid_conf)
            if warn:
                ex["warnings"] = [warn]
            seen_units.add(uid)
            examples.append(ex)

        if seed_unit_ids:
            ph = ",".join("?" for _ in seed_unit_ids)
            for row in conn.execute(
                f"SELECT unit_id, lang, unit_level, source_slug, text, lid_lang, lid_conf, doc_id "
                f"FROM corpus_units WHERE unit_id IN ({ph})",
                tuple(seed_unit_ids),
            ).fetchall():
                add_example(*row)

        if len(examples) < effective_limit:
            fts_q = _build_fts_query(cleaned)
            if fts_q:
                sql_ex = (
                    "SELECT cu.unit_id, cu.lang, cu.unit_level, cu.source_slug, cu.text, cu.lid_lang, cu.lid_conf, cu.doc_id "
                    "FROM corpus_fts "
                    "JOIN corpus_units cu ON cu.id = corpus_fts.rowid "
                    "WHERE corpus_fts MATCH ?"
                )
                p_ex: list[Any] = [fts_q]
                if norm_lang:
                    sql_ex += " AND cu.lang = ?"
                    p_ex.append(norm_lang)
                sql_ex += " ORDER BY bm25(corpus_fts) LIMIT ?"
                p_ex.append(effective_limit * 2)
                for row in conn.execute(sql_ex, tuple(p_ex)).fetchall():
                    add_example(*row)
                    if len(examples) >= effective_limit:
                        break

        return {
            "word": cleaned,
            "lang_filter": norm_lang,
            "frequencies": frequencies,
            "examples": examples[:effective_limit],
        }

    def _fetch_context_neighbors(
        self,
        conn: libsql.Connection,
        rows: list[tuple[str, int, str]],
    ) -> dict[tuple[str, int, str], dict[str, str]]:
        """Fetch immediate +-1 unit_idx neighbors inside the same (doc_id, unit_level)."""
        out: dict[tuple[str, int, str], dict[str, str]] = {}
        seen: set[tuple[str, int, str]] = set()
        for doc_id, idx, ulevel in rows:
            key = (doc_id, int(idx), ulevel)
            if key in seen or not doc_id:
                continue
            seen.add(key)
            ctx: dict[str, str] = {}
            for nidx, ntext in conn.execute(
                "SELECT unit_idx, text FROM corpus_units "
                "WHERE doc_id = ? AND unit_level = ? AND unit_idx IN (?, ?) ORDER BY unit_idx",
                (doc_id, ulevel, int(idx) - 1, int(idx) + 1),
            ).fetchall():
                if int(nidx) == int(idx) - 1:
                    ctx["before"] = ntext
                elif int(nidx) == int(idx) + 1:
                    ctx["after"] = ntext
            if ctx:
                out[key] = ctx
        return out

    def search_corpus(
        self,
        query: str,
        *,
        query_vec: str | Any | None = None,
        lang: str | None = None,
        mode: str = "hybrid",
        source_slug: str | None = None,
        unit_level: str | None = None,
        include_context: bool = False,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        norm_lang = self._normalize_lang(lang)
        mode_norm = mode.casefold().strip()
        if mode_norm not in ("fts", "vector", "hybrid"):
            raise ValueError(f"Unsupported mode {mode!r}. Expected 'fts', 'vector', or 'hybrid'.")
        vec_json = _coerce_vec_json(query_vec)
        if mode_norm in ("vector", "hybrid") and not vec_json:
            if mode_norm == "vector":
                raise ValueError("Vector search requires query_vec.")
            mode_norm = "fts"
        effective_limit = max(1, min(int(limit), 50))
        src_filter = source_slug.strip() if source_slug and source_slug.strip() else None
        lvl_filter = unit_level.strip() if unit_level and unit_level.strip() else None

        with self._connection() as conn:
            fts_rows: list[tuple[Any, ...]] = []
            vec_rows: list[tuple[Any, ...]] = []

            if mode_norm in ("fts", "hybrid") and query.strip():
                for use_or in (False, True):
                    fts_q = _build_fts_query(query, use_or=use_or)
                    if not fts_q:
                        break
                    sql = (
                        "SELECT cu.id, cu.unit_id, cu.lang, cu.unit_level, cu.doc_id, cu.unit_idx, "
                        "cu.source_slug, cu.text, cu.lid_lang, cu.lid_conf, bm25(corpus_fts) AS rank "
                        "FROM corpus_fts JOIN corpus_units cu ON cu.id = corpus_fts.rowid "
                        "WHERE corpus_fts MATCH ?"
                    )
                    params: list[Any] = [fts_q]
                    if norm_lang:
                        sql += " AND cu.lang = ?"
                        params.append(norm_lang)
                    if src_filter:
                        sql += " AND cu.source_slug = ?"
                        params.append(src_filter)
                    if lvl_filter:
                        sql += " AND cu.unit_level = ?"
                        params.append(lvl_filter)
                    sql += " ORDER BY rank ASC LIMIT ?"
                    params.append(max(effective_limit * 4, 40))
                    fts_rows = conn.execute(sql, tuple(params)).fetchall()
                    if fts_rows or use_or:
                        break

            if mode_norm in ("vector", "hybrid") and vec_json:
                overfetch = max(effective_limit * 25, 250) if (norm_lang or src_filter or lvl_filter) else max(effective_limit * 10, 120)
                filters = ["cu.orig_vec IS NOT NULL"]
                vparams: list[Any] = [vec_json, vec_json, overfetch]
                if norm_lang:
                    filters.append("cu.lang = ?")
                    vparams.append(norm_lang)
                if src_filter:
                    filters.append("cu.source_slug = ?")
                    vparams.append(src_filter)
                if lvl_filter:
                    filters.append("cu.unit_level = ?")
                    vparams.append(lvl_filter)
                vparams.append(max(effective_limit * 4, 40))
                vec_rows = conn.execute(
                    f"""
                    SELECT cu.id, cu.unit_id, cu.lang, cu.unit_level, cu.doc_id, cu.unit_idx,
                           cu.source_slug, cu.text, cu.lid_lang, cu.lid_conf,
                           vector_distance_cos(cu.orig_vec, vector8(?)) AS dist
                    FROM vector_top_k('idx_corpus_orig_vec', vector8(?), ?) AS vt
                    JOIN corpus_units cu ON cu.id = vt.id
                    WHERE {' AND '.join(filters)}
                    ORDER BY dist ASC
                    LIMIT ?
                    """,
                    tuple(vparams),
                ).fetchall()

                # Fallback scan for filtered smaller-volume queries if ANN top-k yielded too few matches
                if len(vec_rows) < effective_limit and ((norm_lang and norm_lang != "vro") or src_filter):
                    fb_filters = ["orig_vec IS NOT NULL"]
                    fb_params: list[Any] = [vec_json]
                    if norm_lang:
                        fb_filters.append("lang = ?")
                        fb_params.append(norm_lang)
                    if src_filter:
                        fb_filters.append("source_slug = ?")
                        fb_params.append(src_filter)
                    if lvl_filter:
                        fb_filters.append("unit_level = ?")
                        fb_params.append(lvl_filter)
                    fb_params.append(max(effective_limit * 3, 30))
                    vec_rows = conn.execute(
                        f"""
                        SELECT id, unit_id, lang, unit_level, doc_id, unit_idx,
                               source_slug, text, lid_lang, lid_conf,
                               vector_distance_cos(orig_vec, vector8(?)) AS dist
                        FROM corpus_units
                        WHERE {' AND '.join(fb_filters)}
                        ORDER BY dist ASC
                        LIMIT ?
                        """,
                        tuple(fb_params),
                    ).fetchall()

            fused: dict[int, dict[str, Any]] = {}
            scores: dict[int, float] = {}
            for rank_i, row in enumerate(fts_rows):
                rid = int(row[0])
                scores[rid] = scores.get(rid, 0.0) + (1.0 / (60.0 + rank_i + 1) if mode_norm == "hybrid" else float(-rank_i))
                if rid not in fused:
                    fused[rid] = {"row": row, "match": "fts"}
            for rank_i, row in enumerate(vec_rows):
                rid = int(row[0])
                cos_sim = max(0.0, 1.0 - float(row[10]))
                if mode_norm == "hybrid":
                    scores[rid] = scores.get(rid, 0.0) + (_vector_rrf_weight(cos_sim) / (60.0 + rank_i + 1))
                else:
                    scores[rid] = cos_sim
                if rid in fused:
                    fused[rid]["match"] = "hybrid"
                    fused[rid]["vector_score"] = round(cos_sim, 4)
                else:
                    fused[rid] = {"row": row, "match": "vector", "vector_score": round(cos_sim, 4)}

            top_rids = sorted(fused.keys(), key=lambda r: scores[r], reverse=True)[:effective_limit]
            ctx_map: dict[tuple[str, int, str], dict[str, str]] = {}
            if include_context and top_rids:
                ctx_keys = [(str(fused[r]["row"][4]), int(fused[r]["row"][5]), str(fused[r]["row"][3])) for r in top_rids]
                ctx_map = self._fetch_context_neighbors(conn, ctx_keys)

            results: list[dict[str, Any]] = []
            for rid in top_rids:
                item_meta = fused[rid]
                _id, uid, ulang, ulevel, doc_id, unit_idx, s_slug, txt, lid_l, lid_c, _metric = item_meta["row"]
                out: dict[str, Any] = {
                    "unit_id": uid,
                    "lang": ulang,
                    "unit_level": ulevel,
                    "source_slug": s_slug,
                    "text": _document_excerpt(txt, query) if ulevel == "document" else txt,
                    "match": item_meta["match"],
                    **self._corpus_attribution(conn, s_slug, doc_id),
                }
                if mode_norm == "hybrid":
                    out["score"] = round(scores[rid], 5)
                    if "vector_score" in item_meta:
                        out["vector_score"] = item_meta["vector_score"]
                elif "vector_score" in item_meta:
                    out["score"] = item_meta["vector_score"]
                    out["vector_score"] = item_meta["vector_score"]
                warnings: list[str] = []
                warn = _lid_warning(ulang, lid_l, lid_c)
                if warn:
                    warnings.append(warn)
                if (
                    item_meta["match"] == "vector"
                    and "vector_score" in item_meta
                    and item_meta["vector_score"] < _LOW_SIMILARITY_WARNING_THRESHOLD
                ):
                    warnings.append(
                        f"low semantic similarity ({item_meta['vector_score']:.2f}); no exact lexical match"
                    )
                if warnings:
                    out["warnings"] = warnings
                if include_context:
                    ctx = ctx_map.get((str(doc_id), int(unit_idx), str(ulevel)))
                    if ctx:
                        if "before" in ctx:
                            out["context_before"] = ctx["before"]
                        if "after" in ctx:
                            out["context_after"] = ctx["after"]
                results.append(out)
            return results

    def search_parallel_examples(
        self,
        query: str,
        *,
        query_vec: str | Any | None = None,
        lang: str | None = None,
        target_lang: str | None = None,
        mode: str = "hybrid",
        origin_filter: str | None = None,
        include_context: bool = False,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        norm_lang = self._normalize_lang(lang)
        tgt_norm = target_lang.casefold().strip() if target_lang and target_lang.strip() else None
        mode_norm = mode.casefold().strip()
        if mode_norm not in ("fts", "vector", "hybrid"):
            raise ValueError(f"Unsupported mode {mode!r}.")
        vec_json = _coerce_vec_json(query_vec)
        if mode_norm in ("vector", "hybrid") and not vec_json:
            if mode_norm == "vector":
                raise ValueError("Vector search requires query_vec.")
            mode_norm = "fts"
        origins: list[str] = []
        if origin_filter and origin_filter.strip():
            origins = [o.casefold().strip() for o in origin_filter.split(",") if o.strip()]
        effective_limit = max(1, min(int(limit), 50))
        search_source = True
        search_trans = True

        select_cols = (
            "ct.id, cu.unit_id, cu.lang, ct.target_lang, cu.unit_level, cu.doc_id, cu.unit_idx, "
            "cu.source_slug, cu.text, ct.translated_text, ct.origin, ct.engine, ct.reliability, "
            "cu.lid_lang, cu.lid_conf, "
            "ct.q_overall, ct.q_meaning, ct.q_omission, ct.q_addition, ct.q_facts, ct.q_naturalness, "
            "ct.q_repetition, ct.q_artifacts, ct.q_intrusion, ct.q_integrity, ct.q_uncertain"
        )

        def _filter_sql(alias_cu: str, alias_ct: str) -> tuple[list[str], list[Any]]:
            clauses: list[str] = []
            prm: list[Any] = []
            if norm_lang:
                clauses.append(f"{alias_cu}.lang = ?")
                prm.append(norm_lang)
            if tgt_norm:
                clauses.append(f"{alias_ct}.target_lang = ?")
                prm.append(tgt_norm)
            if origins:
                ph = ",".join("?" for _ in origins)
                clauses.append(f"{alias_ct}.origin IN ({ph})")
                prm.extend(origins)
            return clauses, prm

        with self._connection() as conn:
            streams: list[tuple[str, list[tuple[Any, ...]]]] = []
            extra_f, extra_p = _filter_sql("cu", "ct")
            overfetch = max(effective_limit * 20, 200) if (norm_lang or tgt_norm or origins) else max(effective_limit * 10, 120)

            # 1. FTS streams
            if mode_norm in ("fts", "hybrid") and query.strip():
                fts_q = _build_fts_query(query) or _build_fts_query(query, use_or=True)
                if fts_q:
                    if search_trans:
                        where_t = ["corpus_translations_fts MATCH ?"] + extra_f
                        rows_ft = conn.execute(
                            f"SELECT {select_cols}, bm25(corpus_translations_fts) AS metric "
                            f"FROM corpus_translations_fts "
                            f"JOIN corpus_translations ct ON ct.id = corpus_translations_fts.rowid "
                            f"JOIN corpus_units cu ON cu.id = ct.unit_rowid "
                            f"WHERE {' AND '.join(where_t)} "
                            f"ORDER BY metric ASC, ct.reliability DESC LIMIT ?",
                            (fts_q, *extra_p, max(effective_limit * 5, 50)),
                        ).fetchall()
                        streams.append(("translation_fts", rows_ft))
                    if search_source:
                        where_s = ["corpus_fts MATCH ?"] + extra_f
                        rows_fs = conn.execute(
                            f"SELECT {select_cols}, bm25(corpus_fts) AS metric "
                            f"FROM corpus_fts "
                            f"JOIN corpus_units cu ON cu.id = corpus_fts.rowid "
                            f"JOIN corpus_translations ct ON ct.unit_rowid = cu.id "
                            f"WHERE {' AND '.join(where_s)} "
                            f"ORDER BY metric ASC, ct.reliability DESC LIMIT ?",
                            (fts_q, *extra_p, max(effective_limit * 5, 50)),
                        ).fetchall()
                        streams.append(("source_fts", rows_fs))

            # 2. Vector streams
            if mode_norm in ("vector", "hybrid") and vec_json:
                if search_trans:
                    where_vt = ["ct.tr_vec IS NOT NULL"] + extra_f
                    rows_vt = conn.execute(
                        f"SELECT {select_cols}, vector_distance_cos(ct.tr_vec, vector8(?)) AS metric "
                        f"FROM vector_top_k('idx_translations_vec', vector8(?), ?) AS vt "
                        f"JOIN corpus_translations ct ON ct.id = vt.id "
                        f"JOIN corpus_units cu ON cu.id = ct.unit_rowid "
                        f"WHERE {' AND '.join(where_vt)} "
                        f"ORDER BY metric ASC LIMIT ?",
                        (vec_json, vec_json, overfetch, *extra_p, max(effective_limit * 5, 50)),
                    ).fetchall()
                    if len(rows_vt) < effective_limit and ((norm_lang and norm_lang != "vro") or tgt_norm or origins):
                        rows_vt = conn.execute(
                            f"SELECT {select_cols}, vector_distance_cos(ct.tr_vec, vector8(?)) AS metric "
                            f"FROM corpus_translations ct "
                            f"JOIN corpus_units cu ON cu.id = ct.unit_rowid "
                            f"WHERE {' AND '.join(where_vt)} "
                            f"ORDER BY metric ASC LIMIT ?",
                            (vec_json, *extra_p, max(effective_limit * 4, 40)),
                        ).fetchall()
                    streams.append(("translation_vec", rows_vt))

                if search_source:
                    where_vs = ["cu.orig_vec IS NOT NULL"] + extra_f
                    rows_vs = conn.execute(
                        f"SELECT {select_cols}, vector_distance_cos(cu.orig_vec, vector8(?)) AS metric "
                        f"FROM vector_top_k('idx_corpus_orig_vec', vector8(?), ?) AS vt "
                        f"JOIN corpus_units cu ON cu.id = vt.id "
                        f"JOIN corpus_translations ct ON ct.unit_rowid = cu.id "
                        f"WHERE {' AND '.join(where_vs)} "
                        f"ORDER BY metric ASC LIMIT ?",
                        (vec_json, vec_json, overfetch, *extra_p, max(effective_limit * 5, 50)),
                    ).fetchall()
                    if len(rows_vs) < effective_limit and ((norm_lang and norm_lang != "vro") or tgt_norm or origins):
                        rows_vs = conn.execute(
                            f"SELECT {select_cols}, vector_distance_cos(cu.orig_vec, vector8(?)) AS metric "
                            f"FROM corpus_units cu "
                            f"JOIN corpus_translations ct ON ct.unit_rowid = cu.id "
                            f"WHERE {' AND '.join(where_vs)} "
                            f"ORDER BY metric ASC LIMIT ?",
                            (vec_json, *extra_p, max(effective_limit * 4, 40)),
                        ).fetchall()
                    streams.append(("source_vec", rows_vs))

            # Confidence-weighted RRF + reliability tie-breaking, keeping best translation per (unit_id, target_lang).
            rec_data: dict[int, dict[str, Any]] = {}
            rec_score: dict[int, float] = {}
            for s_name, s_rows in streams:
                is_vec = s_name.endswith("_vec")
                for rank_i, row in enumerate(s_rows):
                    ct_id = int(row[0])
                    rel = int(row[12])
                    if is_vec:
                        cos_sim = max(0.0, 1.0 - float(row[26]))
                        rrf = _vector_rrf_weight(cos_sim) / (60.0 + rank_i + 1)
                    else:
                        cos_sim = 0.0
                        rrf = 1.0 / (60.0 + rank_i + 1)
                    rel_boost = 0.004 * (rel / 1000.0)
                    rec_score[ct_id] = rec_score.get(ct_id, 0.0) + rrf + (rel_boost if ct_id not in rec_score else 0.0)
                    info = rec_data.get(ct_id)
                    if info is None:
                        info = {"row": row, "channels": [s_name]}
                        rec_data[ct_id] = info
                    elif s_name not in info["channels"]:
                        info["channels"].append(s_name)
                    if is_vec:
                        score_key = (
                            "translation_vector_score"
                            if s_name == "translation_vec"
                            else "source_vector_score"
                        )
                        info[score_key] = round(max(info.get(score_key, 0.0), cos_sim), 4)

            ordered_ct = sorted(rec_data.keys(), key=lambda cid: rec_score[cid], reverse=True)
            chosen: list[int] = []
            seen_unit_tgt: set[tuple[str, str]] = set()
            for cid in ordered_ct:
                row = rec_data[cid]["row"]
                ut_key = (str(row[1]), str(row[3]))
                if ut_key in seen_unit_tgt:
                    continue
                seen_unit_tgt.add(ut_key)
                chosen.append(cid)
                if len(chosen) >= effective_limit:
                    break

            ctx_map: dict[tuple[str, int, str], dict[str, str]] = {}
            if include_context and chosen:
                ctx_keys = [(str(rec_data[c]["row"][5]), int(rec_data[c]["row"][6]), str(rec_data[c]["row"][4])) for c in chosen]
                ctx_map = self._fetch_context_neighbors(conn, ctx_keys)

            results: list[dict[str, Any]] = []
            q_cols = (
                "q_overall",
                "q_meaning",
                "q_omission",
                "q_addition",
                "q_facts",
                "q_naturalness",
                "q_repetition",
                "q_artifacts",
                "q_intrusion",
                "q_integrity",
                "q_uncertain",
            )
            for cid in chosen:
                info = rec_data[cid]
                row = info["row"]
                (
                    _ct_id,
                    uid,
                    ulang,
                    tgt_lang,
                    ulevel,
                    doc_id,
                    unit_idx,
                    s_slug,
                    src_txt,
                    tr_txt,
                    origin,
                    engine,
                    _rel,
                    lid_l,
                    lid_c,
                    *qvals,
                ) = row[:26]
                qdict = {col: (int(val) if val is not None else None) for col, val in zip(q_cols, qvals)}
                warnings = _translation_warnings(qdict)
                lwarn = _lid_warning(ulang, lid_l, lid_c)
                if lwarn:
                    warnings.insert(0, lwarn)

                item: dict[str, Any] = {
                    "unit_id": uid,
                    "lang": ulang,
                    "target_lang": tgt_lang,
                    "unit_level": ulevel,
                    "source_text": _document_excerpt(src_txt, query) if ulevel == "document" else src_txt,
                    "translated_text": _document_excerpt(tr_txt, query) if ulevel == "document" else tr_txt,
                    "origin": origin,
                    "source_slug": s_slug,
                    "channels": info["channels"],
                    **self._corpus_attribution(conn, s_slug, doc_id),
                }
                if engine:
                    item["engine"] = engine
                item["score"] = round(rec_score[cid], 5)
                for score_key in ("source_vector_score", "translation_vector_score"):
                    if score_key in info:
                        item[score_key] = info[score_key]
                vector_scores = [
                    info[key]
                    for key in ("source_vector_score", "translation_vector_score")
                    if key in info
                ]
                if vector_scores and not any("fts" in ch for ch in info["channels"]) and max(vector_scores) < _LOW_SIMILARITY_WARNING_THRESHOLD:
                    warnings.append(f"low semantic similarity ({max(vector_scores):.2f}); no exact lexical match")
                if warnings:
                    item["warnings"] = warnings
                if include_context:
                    ctx = ctx_map.get((str(doc_id), int(unit_idx), str(ulevel)))
                    if ctx:
                        if "before" in ctx:
                            item["context_before"] = ctx["before"]
                        if "after" in ctx:
                            item["context_after"] = ctx["after"]
                results.append(item)
            return results

    def find_correction_entries(self, query: str, limit: int = 40, lang: str = "vro") -> list[dict[str, Any]]:
        """Return dictionary entries matching a query for Giella correction candidate generation."""
        canon_lang = normalize_language_code(lang)
        effective_limit = max(1, min(int(limit), 100))
        norm = normalize_db_text(query)
        with self._connection() as conn:
            rowids: list[int] = []
            seen: set[int] = set()
            if norm:
                for (rid,) in conn.execute(
                    "SELECT id FROM dict_entries WHERE lang = ? AND lookup_key = ? LIMIT ?",
                    (canon_lang, norm, effective_limit),
                ).fetchall():
                    if rid not in seen:
                        seen.add(rid)
                        rowids.append(int(rid))
            if len(rowids) < effective_limit:
                fts_q = _build_fts_query(query)
                if fts_q:
                    for (rid,) in conn.execute(
                        "SELECT entry_rowid FROM dict_fts WHERE dict_fts MATCH ? AND lang = ? ORDER BY bm25(dict_fts) LIMIT ?",
                        (fts_q, canon_lang, effective_limit),
                    ).fetchall():
                        if rid not in seen:
                            seen.add(rid)
                            rowids.append(int(rid))
                        if len(rowids) >= effective_limit:
                            break
            if not rowids:
                return []
            ph = ",".join("?" for _ in rowids)
            hw_map = {
                int(rid): hw
                for rid, hw in conn.execute(
                    f"SELECT id, headword FROM dict_entries WHERE id IN ({ph})",
                    tuple(rowids),
                ).fetchall()
            }
            return [{canon_lang: [hw_map[rid]], "headwords": [hw_map[rid]], "et": ""} for rid in rowids if rid in hw_map]

    def find_usage_examples(
        self,
        query: str,
        *,
        source_type: str | None = None,
        limit: int = 5,
        max_snippet_chars: int = DEFAULT_SNIPPET_CHARS,
    ) -> list[dict[str, Any]]:
        """Find attested Võro corpus usage examples using south_estonian.db."""
        fts_q = _build_fts_query(query)
        if not fts_q:
            return []
        effective_limit = _limit(limit, default=5, maximum=50)
        snippet_limit = _snippet_char_limit(max_snippet_chars)
        with self._connection() as conn:
            sql = (
                "SELECT cu.unit_id, cu.source_slug, cu.doc_id, cu.unit_idx, cu.text "
                "FROM corpus_fts JOIN corpus_units cu ON cu.id = corpus_fts.rowid "
                "WHERE corpus_fts MATCH ? AND cu.lang = 'vro'"
            )
            params: list[Any] = [fts_q]
            if source_type and source_type.strip():
                sql += " AND cu.source_slug = ?"
                params.append(USAGE_SOURCE_SLUGS.get(source_type.strip(), source_type.strip()))
            sql += " ORDER BY bm25(corpus_fts) LIMIT ?"
            params.append(effective_limit)
            rows = [(*row, self._corpus_attribution(conn, row[1], row[2]))
                    for row in conn.execute(sql, tuple(params)).fetchall()]
        results: list[dict[str, Any]] = []
        for uid, s_slug, doc_id, unit_idx, txt, attribution in rows:
            snippet = str(txt or "").strip()
            if len(snippet) > snippet_limit:
                snippet = snippet[:snippet_limit].rstrip() + "…"
            results.append({
                "public_id": uid,
                "source_slug": s_slug,
                "document_id": doc_id,
                "segment_index": unit_idx,
                "snippet": snippet,
                **attribution,
            })
        return results

    def get_language_stats(self, lang: str | None = None) -> dict[str, Any]:
        norm_lang = self._normalize_lang(lang)
        langs = (norm_lang,) if norm_lang else SOUTH_ESTONIAN_LANGS
        with self._connection() as conn:
            per_lang: dict[str, dict[str, Any]] = {}
            for lcode in langs:
                units = conn.execute("SELECT COUNT(*), SUM(CASE WHEN orig_vec IS NOT NULL THEN 1 ELSE 0 END) FROM corpus_units WHERE lang = ?", (lcode,)).fetchone()
                tr_rows = conn.execute(
                    "SELECT target_lang, origin, COUNT(*), SUM(CASE WHEN tr_vec IS NOT NULL THEN 1 ELSE 0 END) "
                    "FROM corpus_translations WHERE lang = ? GROUP BY target_lang, origin",
                    (lcode,),
                ).fetchall()
                d_cnt = conn.execute("SELECT COUNT(*) FROM dict_entries WHERE lang = ?", (lcode,)).fetchone()[0]
                def_rows = conn.execute(
                    "SELECT COUNT(*), SUM(CASE WHEN def_vec IS NOT NULL THEN 1 ELSE 0 END) FROM dict_definitions WHERE lang = ?",
                    (lcode,),
                ).fetchone()
                inf_cnt = conn.execute("SELECT COUNT(*) FROM dict_inflections WHERE lang = ?", (lcode,)).fetchone()[0]
                wf_cnt = conn.execute("SELECT COUNT(*) FROM word_frequencies WHERE lang = ?", (lcode,)).fetchone()[0]
                per_lang[lcode] = {
                    "corpus_units": int(units[0] or 0),
                    "corpus_vectors": int(units[1] or 0),
                    "translations_total": sum(int(r[2]) for r in tr_rows),
                    "translation_vectors": sum(int(r[3] or 0) for r in tr_rows),
                    "translations_by_target_origin": {
                        f"{r[0]}:{r[1]}": int(r[2]) for r in tr_rows
                    },
                    "dict_entries": int(d_cnt or 0),
                    "dict_definitions": int(def_rows[0] or 0),
                    "dict_vectors": int(def_rows[1] or 0),
                    "dict_inflections": int(inf_cnt or 0),
                    "word_frequencies": int(wf_cnt or 0),
                }

            src_sql = "SELECT source_slug, langs, unit_count, translation_count, dict_entry_count, license FROM sources"
            src_rows = conn.execute(f"{src_sql} ORDER BY (unit_count + dict_entry_count) DESC LIMIT 40").fetchall()
            sources = [
                {
                    "source_slug": s[0],
                    "langs": _parse_json_list(s[1]),
                    "unit_count": int(s[2]),
                    "translation_count": int(s[3]),
                    "dict_entry_count": int(s[4]),
                    "license": s[5],
                    **source_attribution(s[0]),
                }
                for s in src_rows
                if (norm_lang is None or norm_lang in _parse_json_list(s[1]))
            ][:20]

            return {
                "db_path": str(self.db_path),
                "size_mb": round(self.db_path.stat().st_size / 1_000_000, 2),
                "languages": per_lang,
                "top_sources": sources,
            }

    def word_exists_in_bag_many(
        self,
        words: list[str],
        *,
        lang: str | None = None,
        include_languages: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """Check word surface forms against `word_frequencies` in south_estonian.db."""
        norm_lang = self._normalize_lang(lang)
        pairs = [(original, normalize_db_text(original)) for original in words]
        norms = list(dict.fromkeys(norm for _, norm in pairs if norm))
        counts_by_key: dict[str, dict[str, int]] = {}
        if norms:
            with self._connection() as conn:
                for index in range(0, len(norms), 500):
                    chunk = norms[index : index + 500]
                    placeholders = ",".join("?" for _ in chunk)
                    sql = (
                        f"SELECT lookup_key, lang, SUM(freq) AS total_freq "
                        f"FROM word_frequencies WHERE lookup_key IN ({placeholders})"
                    )
                    params: list[Any] = list(chunk)
                    if norm_lang:
                        sql += " AND lang = ?"
                        params.append(norm_lang)
                    sql += " GROUP BY lookup_key, lang"
                    for lk, wlang, total_freq in conn.execute(sql, tuple(params)).fetchall():
                        lang_map = counts_by_key.setdefault(str(lk), {})
                        lang_map[str(wlang)] = int(total_freq or 0)

        results: dict[str, dict[str, Any]] = {}
        for original, norm in pairs:
            lang_map = counts_by_key.get(norm, {}) if norm else {}
            total = sum(lang_map.values())
            entry: dict[str, Any] = {
                "word": original,
                "normalized_word": norm,
                "exists": total > 0,
                "total_count": total,
            }
            if include_languages:
                entry["languages"] = [
                    k
                    for k, _ in sorted(lang_map.items(), key=lambda item: (-item[1], item[0]))
                ]
            results[original] = entry
        return results

    def known_words_in_bag(self, words: Any, *, lang: str | None = None) -> set[str]:
        """Return the subset of normalized keys present in `word_frequencies`."""
        norm_lang = self._normalize_lang(lang)
        word_list = list(dict.fromkeys(w for w in words if w))
        if not word_list:
            return set()
        known: set[str] = set()
        with self._connection() as conn:
            for index in range(0, len(word_list), 500):
                chunk = word_list[index : index + 500]
                placeholders = ",".join("?" for _ in chunk)
                sql = (
                    f"SELECT DISTINCT lookup_key FROM word_frequencies "
                    f"WHERE lookup_key IN ({placeholders})"
                )
                params: list[Any] = list(chunk)
                if norm_lang:
                    sql += " AND lang = ?"
                    params.append(norm_lang)
                for row in conn.execute(sql, tuple(params)).fetchall():
                    known.add(str(row[0]))
        return known

    def find_unknown_words(
        self,
        text: str,
        *,
        lang: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Tokenize text and return unique word forms absent from `word_frequencies`."""
        norm_lang = self._normalize_lang(lang)
        max_rows = _limit(limit, default=50, maximum=500)
        tokens = _text_words(text)
        if not tokens:
            out: dict[str, Any] = {"unknown": [], "checked": 0}
            if norm_lang:
                out["lang"] = norm_lang
            return out

        counts: dict[str, int] = {}
        first_seen: dict[str, str] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
            first_seen.setdefault(token, token)

        known = self.known_words_in_bag(counts.keys(), lang=norm_lang)
        unknown = [
            first_seen[word]
            for word in sorted(counts, key=lambda item: (-counts[item], item))
            if word not in known
        ]
        out = {
            "unknown": unknown[:max_rows],
            "checked": len(tokens),
        }
        if norm_lang:
            out["lang"] = norm_lang
        return out
