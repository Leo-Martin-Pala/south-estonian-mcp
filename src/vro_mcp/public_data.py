"""Validate the dataset selected for a public deployment or release."""
from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

SOURCES_FILE = Path(__file__).with_name("sources-public.json")
APPLICATION_ID = 0x56524F32


def render_notice() -> str:
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    sections = [
        "South Estonian MCP public dataset",
        "Compilation and adaptations are distributed under CC BY-SA 4.0. "
        "The original source licenses listed below continue to apply. "
        "See LICENSE and https://creativecommons.org/licenses/by-sa/4.0/.",
    ]
    for slug, source in sources.items():
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
        if conn.execute("""
            SELECT 1 FROM corpus_translations t LEFT JOIN corpus_units u ON t.unit_rowid = u.id
            WHERE u.id IS NULL OR u.source_slug <> 'paraleelkorpus'
               OR t.origin <> 'human' OR t.engine IS NOT 'paraleelkorpus' OR t.target_lang <> 'et'
            LIMIT 1
        """).fetchone():
            raise ValueError("Unapproved translations in the public dataset")
        if conn.execute("""
            SELECT 1 FROM corpus_units u LEFT JOIN corpus_documents d USING (doc_id)
            WHERE d.doc_id IS NULL OR (u.source_slug = 'fiu_vrowiki'
                  AND d.source_url NOT GLOB 'https://fiu-vro.wikipedia.org/?curid=*')
            LIMIT 1
        """).fetchone():
            raise ValueError("Missing corpus attribution")


if __name__ == "__main__":
    verify_public_data(Path(sys.argv[1]))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(render_notice(), encoding="utf-8")
