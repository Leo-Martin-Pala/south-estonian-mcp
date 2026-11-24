#!/usr/bin/env python3
"""Export a new public database and attribution from reviewed source records."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

import libsql

from import_smugri4 import import_smugri4

from vro_mcp.db import PUBLIC_SOURCES, _norm_gloss, normalize_db_text
from vro_mcp.public_data import APPLICATION_ID, verify_public_data
from vro_mcp.tokenization import tokenize

ROOT = Path(__file__).resolve().parents[1]
SOURCES = PUBLIC_SOURCES
VECTOR_COLUMNS = {
    "corpus_units": ("orig_vec", "idx_corpus_orig_vec"),
    "corpus_translations": ("tr_vec", "idx_translations_vec"),
    "dict_definitions": ("def_vec", "idx_dict_def_vec"),
}
UNIT_COUNTS = {
    "corpus_units": "lang",
    "corpus_translations": "lang",
    "dict_entries": "lang",
}


def copy_rows(source, output, table, where, args=()):
    columns = [row[1] for row in output.execute(f"PRAGMA table_info({table})").fetchall()]
    fields = ",".join(columns)
    slots = ",".join("?" for _ in columns)
    rows = source.execute(f"SELECT {fields} FROM {table} WHERE {where}", args)
    insert = f"INSERT INTO {table} ({fields}) VALUES ({slots})"
    while batch := rows.fetchmany(2000):
        output.executemany(insert, batch)


def wiki_documents(paths):
    for path in paths:
        with path.open("rb") as stream:
            events = ET.iterparse(stream, events=("start", "end"))
            _, root = next(events)
            namespace = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
            for event, page in events:
                if event != "end" or page.tag != namespace + "page":
                    continue
                page_id = page.findtext(namespace + "id")
                title = page.findtext(namespace + "title")
                if page_id and title:
                    key = "fiu_vrowiki:" + hashlib.sha1(f"fiu_vrowiki:{page_id}".encode()).hexdigest()[:16]
                    yield key, (title, "Võro Wikipedia contributors",
                                f"https://fiu-vro.wikipedia.org/?curid={page_id}")
                root.clear()


def import_publisher_parallel(output, directory):
    """Use the publisher's documented line alignment, preserving blank/comment slots."""
    existing = set(output.execute(
        "SELECT doc_id, text FROM corpus_units WHERE source_slug = 'paraleelkorpus'"
    ).fetchall())
    units = []
    translations = []
    next_id = output.execute("SELECT coalesce(max(id), 0) FROM corpus_units").fetchone()[0]
    for source_file in sorted(directory.glob("*.vro.txt")):
        name = source_file.name.removesuffix(".vro.txt")
        target_file = directory / f"{name}.et.txt"
        if not name.isdecimal() or name == "225" or not target_file.is_file():
            continue
        source_lines = source_file.read_text(encoding="utf-8-sig").splitlines()
        target_lines = target_file.read_text(encoding="utf-8-sig").splitlines()
        if len(source_lines) != len(target_lines):
            print(f"Skipped publisher alignment with unequal line counts: {name}")
            continue
        # Use distinct IDs since the unified snapshot has different segmentation.
        doc_id = f"paraleelkorpus:publisher:{name}"
        for index, (source_line, target_line) in enumerate(zip(source_lines, target_lines)):
            text, translation = source_line.strip(), target_line.strip()
            if not text or text.startswith("#") or (f"paraleelkorpus:{name}", text) in existing:
                continue
            next_id += 1
            units.append((next_id, f"{doc_id}:{index + 1}", doc_id, index, text))
            if translation and not translation.startswith("#"):
                translations.append((next_id, translation))
    output.executemany(
        "INSERT INTO corpus_units (id, unit_id, lang, unit_level, doc_id, unit_idx, source_slug, "
        "text, lid_lang, lid_conf) VALUES (?, ?, 'vro', 'sentence', ?, ?, 'paraleelkorpus', ?, 'vro', 0)",
        units,
    )
    output.executemany(
        "INSERT INTO corpus_translations (unit_rowid, lang, target_lang, translated_text, origin, engine, reliability) "
        "VALUES (?, 'vro', 'et', ?, 'human', 'paraleelkorpus', 950)",
        translations,
    )
    print(f"Added {len(units)} publisher text units and {len(translations)} human parallel pairs")


def import_estonian_ids(output, path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        terms = defaultdict(set)
        for row in csv.DictReader(stream, delimiter="\t"):
            term = row["Estonian_StandOrth"].strip()
            if term:
                terms[(row["chapter_id"], row["entry_id"])].add(term)

    rows = []
    for entry_rowid, entry_id in output.execute(
        "SELECT id, entry_id FROM dict_entries WHERE source_slug = 'ids_vro'"
    ).fetchall():
        fields = entry_id.split(":")
        if len(fields) == 4:
            for term in sorted(terms.get(tuple(fields[2:]), ())):
                evidence = json.dumps([{"url": "https://ids.clld.org/contributions/127",
                                        "license": "CC-BY-4.0"}])
                rows.append((entry_rowid, term, _norm_gloss(term), evidence))
    output.executemany(
        "INSERT INTO dict_definitions (entry_rowid, lang, target_lang, definition_text, norm_def, source_evidence)"
        " VALUES (?, 'vro', 'et', ?, ?, ?)", rows,
    )
    print(f"Added {len(rows)} standard Estonian IDS glosses by concept ID")


def document_credits(output, wiki_paths, metadata_paths):
    docs = dict(output.execute("SELECT DISTINCT doc_id,source_slug FROM corpus_units").fetchall())
    credits = {key: credit for key, credit in wiki_documents(wiki_paths) if key in docs}
    for path in metadata_paths:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                key = row.get("doc_id") or f"{row.get('source_slug')}:{row.get('stable_id')}"
                if key in docs and docs[key] != "fiu_vrowiki":
                    credits[key] = (row.get("title"), row.get("author"), SOURCES[docs[key]]["url"])
    missing = sum(slug == "fiu_vrowiki" and key not in credits for key, slug in docs.items())
    if missing:
        raise ValueError(f"{missing} Wikipedia documents have no page attribution. Supply the source dump(s).")
    output.executemany(
        "INSERT INTO corpus_documents VALUES (?, ?, ?, ?)",
        [(key, *credits.get(key, (None, None, SOURCES[slug]["url"]))) for key, slug in docs.items()],
    )


def rebuild_word_frequencies(output):
    counts = defaultdict(Counter)
    for lang, text in output.execute("""
        SELECT lang, text FROM corpus_units AS unit
        WHERE unit_level = 'sentence' OR NOT EXISTS (
            SELECT 1 FROM corpus_units
            WHERE doc_id = unit.doc_id AND unit_level = 'sentence'
        ) AND unit_level = 'paragraph'
    """).fetchall():
        counts[lang].update(word.lower() for word in tokenize(text))
    output.executemany(
        "INSERT INTO word_frequencies (lang, lookup_key, form, freq) VALUES (?, ?, ?, ?)",
        [(lang, key, word, count) for lang, forms in counts.items()
         for word, count in sorted(forms.items()) if (key := normalize_db_text(word))],
    )


def rebuild_cognates(output):
    output.execute("""
        INSERT INTO dict_cognates (concept_key, concept_lang, lang, entry_rowid, headword, pos, definition_text)
        WITH candidates AS (
            SELECT d.norm_def, d.target_lang, e.lang, e.id, e.headword, e.pos, d.definition_text,
                   row_number() OVER (
                     PARTITION BY d.norm_def, d.target_lang, e.lang, e.headword ORDER BY e.id
                   ) AS duplicate
            FROM dict_definitions d JOIN dict_entries e ON e.id = d.entry_rowid
            WHERE e.source_slug <> 'fiu_vrowiki_dictionary' AND d.target_lang IN ('et', 'en')
              AND length(d.norm_def) BETWEEN 2 AND 45 AND length(e.headword) BETWEEN 1 AND 35
        ), shared AS (
            SELECT norm_def, target_lang FROM candidates GROUP BY norm_def, target_lang
            HAVING count(DISTINCT lang) > 1
        ), ranked AS (
            SELECT c.*, row_number() OVER (
                PARTITION BY norm_def, target_lang, lang ORDER BY length(headword), headword, id
            ) AS rank
            FROM candidates c JOIN shared USING (norm_def, target_lang)
            WHERE duplicate = 1
        )
        SELECT norm_def, target_lang, lang, id, headword, pos, definition_text FROM ranked WHERE rank <= 3
    """)


def build(source_path, output_path, wiki_paths, metadata_paths, publisher_parallel, estonian_ids, smugri_root=None):
    with closing(sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        # All reads and coverage counts see the same source snapshot.
        source.execute("BEGIN")
        with closing(libsql.connect(str(output_path))) as output:
            output.executescript((ROOT / "scripts/public_data_schema.sql").read_text())
            for slug, policy in SOURCES.items():
                if policy.get("provider_import"):
                    continue
                if policy["kind"] == "corpus":
                    copy_rows(source, output, "corpus_units", "source_slug = ?", (slug,))
                    if engine := policy.get("translation_engine"):
                        copy_rows(source, output, "corpus_translations",
                                  "origin = 'human' AND target_lang = 'et' AND engine = ? "
                                  "AND unit_rowid IN (SELECT id FROM corpus_units WHERE source_slug = ?)",
                                  (engine, slug))
                        if publisher_parallel:
                            import_publisher_parallel(output, publisher_parallel)
                else:
                    copy_rows(source, output, "dict_entries", "source_slug = ?", (slug,))
                    copy_rows(source, output, "dict_inflection_types", "source_slug = ?", (slug,))
                    for table in ("dict_definitions", "dict_inflections", "dict_examples"):
                        copy_rows(source, output, table,
                                  "entry_rowid IN (SELECT id FROM dict_entries WHERE source_slug = ?)", (slug,))
                    output.execute("UPDATE dict_entries SET source_url = ? "
                                   "WHERE source_slug = ? AND coalesce(source_url, '') = ''", (policy["url"], slug))

            if estonian_ids:
                import_estonian_ids(output, estonian_ids)
            document_credits(output, wiki_paths, metadata_paths)
            if smugri_root:
                print("smugri4", json.dumps(import_smugri4(output, smugri_root)))

            for slug, policy in SOURCES.items():
                langs = set()
                counts = []
                for table, from_sql in (
                    ("corpus_units", "corpus_units WHERE source_slug = ?"),
                    ("corpus_translations", "corpus_translations t JOIN corpus_units u ON t.unit_rowid = u.id WHERE u.source_slug = ?"),
                    ("dict_entries", "dict_entries WHERE source_slug = ?"),
                ):
                    lang_column = "t.lang" if table == "corpus_translations" else "lang"
                    rows = output.execute(f"SELECT {lang_column},count(*) FROM {from_sql} GROUP BY {lang_column}", (slug,)).fetchall()
                    counts.append(sum(count for _, count in rows))
                    langs.update(lang for lang, _ in rows)
                if langs:
                    output.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                   (slug, json.dumps(sorted(langs)), *counts, policy["title"], policy["url"], policy["license"]))

            rebuild_word_frequencies(output)
            rebuild_cognates(output)
            output.execute("INSERT INTO dict_fts (headword, definition_text, lang, entry_rowid) "
                           "SELECT e.headword, coalesce(d.definition_text, ''), e.lang, e.id "
                           "FROM dict_entries e LEFT JOIN dict_definitions d ON d.entry_rowid = e.id")
            for fts in ("corpus_fts", "corpus_translations_fts"):
                output.execute(f"INSERT INTO {fts}({fts}) VALUES ('rebuild')")
            for table, (column, index) in VECTOR_COLUMNS.items():
                output.execute(f"CREATE INDEX {index} ON {table}(libsql_vector_idx("
                               f"{column}, 'metric=cosine', 'compress_neighbors=float1bit', 'max_neighbors=20'))")
            output.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            output.commit()
            if output.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("Public database integrity check failed")
            for table, lang_column in UNIT_COUNTS.items():
                sql = f"SELECT {lang_column}, count(*) FROM {table} GROUP BY {lang_column}"
                print(table, json.dumps({"private": dict(source.execute(sql)),
                                         "public": dict(output.execute(sql).fetchall())}))
            print("sources", output.execute("SELECT source_slug,unit_count,translation_count,dict_entry_count FROM sources").fetchall())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Private unified database, opened read-only")
    parser.add_argument("--wiki-dump", type=Path, action="append", required=True)
    parser.add_argument("--documents", type=Path, action="append", default=[], help="Source document metadata JSONL")
    parser.add_argument("--publisher-parallel", type=Path, help="Licensed publisher archive of paired .vro.txt and .et.txt files")
    parser.add_argument("--estonian-ids", type=Path, help="CC BY 4.0 Estonian IDS wordlist TSV")
    parser.add_argument("--smugri-root", type=Path, help="Optional pinned TartuNLP Git snapshot for the noncommercial edition")
    parser.add_argument("--output", type=Path, default=ROOT / "data/south_estonian_public.db")
    args = parser.parse_args()

    target = args.output.resolve()
    if target == args.source.resolve():
        parser.error("Source and output paths must differ.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as work:
        staged = Path(work) / target.name
        build(args.source, staged, args.wiki_dump, args.documents, args.publisher_parallel, args.estonian_ids, args.smugri_root)
        verify_public_data(staged)
        os.replace(staged, target)


if __name__ == "__main__":
    main()
