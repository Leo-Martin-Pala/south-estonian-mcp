"""Validate the dataset selected for a public deployment or release."""
from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

SOURCES_FILE = Path(__file__).with_name("sources-public.json")
APPLICATION_ID = 0x56524F32


def render_notice(path: Path) -> str:
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        included = {row[0] for row in conn.execute("SELECT source_slug FROM sources")}
    noncommercial = any(sources[slug]["license"] == "CC-BY-NC-SA-4.0" for slug in included)
    sections = [
        "South Estonian MCP public dataset",
        (
            "This database collects works under different licenses. "
            "CC BY-NC-SA 4.0 applies to the SMUGRI-4 material and its adaptations. "
            "Use of the complete database must respect the noncommercial terms. "
            "Other sources retain their own terms. See LICENSE and LICENSE-NC-SA."
            if noncommercial else
            "Compilation and adaptations are distributed under CC BY-SA 4.0. "
            "The original source licenses listed below continue to apply. "
            "See LICENSE and https://creativecommons.org/licenses/by-sa/4.0/."
        ),
    ]
    for slug, source in sources.items():
        if slug not in included:
            continue
        sections.append(
            f"{source['title']} ({slug})\n{source['credit']}\n"
            f"{source['url']}\n{source['license']} — {source['license_url']}\n"
            f"Changes: {source['changes']}"
        )
    return "\n\n".join(sections) + "\n"


def verify_public_data(path: Path) -> None:
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
            raise ValueError("Expected a database built by scripts/build_public_data.py")
        for table, kind in (("corpus_units", "corpus"), ("dict_entries", "dictionary"),
                            ("dict_inflection_types", "dictionary")):
            slugs = {row[0] for row in conn.execute(f"SELECT DISTINCT source_slug FROM {table}")}
            allowed = {slug for slug, policy in sources.items() if policy["kind"] == kind}
            if slugs - allowed:
                raise ValueError(f"Unapproved sources in {table}: {sorted(slugs - allowed)}")
        for slug, license_name in conn.execute("SELECT source_slug, license FROM sources"):
            if slug not in sources or sources[slug]["license"] != license_name:
                raise ValueError(f"Unapproved source metadata for {slug}")
        for table in ("dict_definitions", "dict_examples", "dict_inflections", "dict_cognates", "dict_fts"):
            if conn.execute(f"""
                SELECT 1 FROM {table} d LEFT JOIN dict_entries e ON d.entry_rowid = e.id
                WHERE e.id IS NULL LIMIT 1
            """).fetchone():
                raise ValueError(f"Orphan dictionary rows in {table}")
        approved_pairs = {
            (slug, policy["translation_engine"], target)
            for slug, policy in sources.items() if "translation_engine" in policy
            for target in policy.get("translation_targets", ["et"])
        }
        pairs = conn.execute("""
            SELECT DISTINCT u.source_slug, t.engine, t.origin, t.target_lang, t.lang, u.lang
            FROM corpus_translations t LEFT JOIN corpus_units u ON t.unit_rowid = u.id
        """)
        if any((slug, engine, target) not in approved_pairs or origin != "human"
               or lang != source_lang for slug, engine, origin, target, lang, source_lang in pairs):
            raise ValueError("Unapproved translations in the public dataset")
        if conn.execute("""
            SELECT 1 FROM corpus_units u LEFT JOIN corpus_documents d USING (doc_id)
            WHERE d.doc_id IS NULL OR (u.source_slug = 'fiu_vrowiki'
                  AND d.source_url NOT GLOB 'https://fiu-vro.wikipedia.org/?curid=*')
            LIMIT 1
        """).fetchone():
            raise ValueError("Missing corpus attribution")
        for slug, policy in sources.items():
            if not policy.get("provider_import"):
                continue
            roots = [url.replace("/tree/", "/blob/") + "/*"
                     for url in policy.get("provider_urls", [policy["url"]])]
            outside_roots = " AND ".join("coalesce(src.url, '') NOT GLOB ?" for _ in roots)
            if policy["kind"] == "corpus":
                urls = ("SELECT u.source_slug, d.source_url AS url FROM corpus_units u "
                        "JOIN corpus_documents d USING (doc_id)")
            else:
                urls = "SELECT source_slug, source_url AS url FROM dict_entries"
            if conn.execute(
                f"SELECT 1 FROM ({urls}) src WHERE src.source_slug = ? AND {outside_roots} LIMIT 1",
                (slug, *roots),
            ).fetchone():
                raise ValueError(f"Unpinned source credit for {slug}")


if __name__ == "__main__":
    path = Path(sys.argv[1])
    verify_public_data(path)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(render_notice(path), encoding="utf-8")
