"""Build and install aggregate word frequencies for the public dataset."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from itertools import groupby, islice
from pathlib import Path

import libsql

from vro_mcp.db import normalize_db_text
from vro_mcp.public_data import verify_public_data
from vro_mcp.tokenization import tokenize

if __package__:
    from .public_website_scrapes import WEBSITE_INPUTS, import_website_scrapes, website_page_credits
else:
    from public_website_scrapes import WEBSITE_INPUTS, import_website_scrapes, website_page_credits

UNIT_PRIORITY = {"sentence": 0, "utterance": 0, "paragraph": 1, "document": 2}
HANDLE = re.compile(r"(?<!\w)@[\w.]+", re.UNICODE)


def fetch_rows(cursor):
    while batch := cursor.fetchmany(5000):
        yield from batch


def document_texts(db, website_pages):
    rows = db.execute("""
        SELECT lang, doc_id, source_slug, unit_level, text
        FROM corpus_units
        WHERE doc_id IS NOT NULL AND trim(doc_id) <> ''
          AND unit_level IN ('sentence', 'utterance', 'paragraph', 'document')
        ORDER BY lang, doc_id, source_slug
    """)
    for (lang, doc_id, slug), units in groupby(fetch_rows(rows), key=lambda row: row[:3]):
        if slug in WEBSITE_INPUTS and (slug, doc_id) not in website_pages:
            continue
        by_level = defaultdict(list)
        for _, _, _, level, text in units:
            by_level[UNIT_PRIORITY[level]].append(text)
        yield lang, doc_id, by_level[min(by_level)]


def rebuild_word_frequencies(output, source, website_pages=()):
    """Pool counts across documents, with private/public overlap counted once."""
    counts = defaultdict(Counter)
    document_support = defaultdict(dict)
    source_units = set()
    for db, is_source in ((source, True), (output, False)):
        for lang, doc_id, texts in document_texts(db, website_pages):
            document = Counter()
            for text in texts:
                normalized = " ".join(unicodedata.normalize("NFC", text).split())
                digest = hashlib.blake2b(normalized.encode(), digest_size=16).digest()
                key = (lang, digest)
                if is_source:
                    source_units.add(key)
                elif key in source_units:
                    continue
                document.update(
                    word.lower() for word in tokenize(HANDLE.sub(" ", normalized))
                )
            counts[lang].update(document)
            support = document_support[lang]
            for word in document:
                if word not in support:
                    support[word] = doc_id
                elif support[word] != doc_id:
                    support[word] = None

    output.execute("DELETE FROM word_frequencies")
    rows = (
        (lang, key, word, count)
        for lang, forms in counts.items()
        for word, count in sorted(forms.items())
        if document_support[lang][word] is None and (key := normalize_db_text(word))
    )
    while batch := list(islice(rows, 5000)):
        output.executemany(
            "INSERT INTO word_frequencies (lang, lookup_key, form, freq) VALUES (?, ?, ?, ?)",
            batch,
        )
    output.execute("""
        CREATE TABLE IF NOT EXISTS word_frequency_metadata (
            minimum_documents INTEGER NOT NULL,
            input_rights_status TEXT NOT NULL
        )
    """)
    output.execute("DELETE FROM word_frequency_metadata")
    output.execute("INSERT INTO word_frequency_metadata VALUES (2, 'mixed-including-unknown')")


def refresh(source_path: Path, target: Path, website_corpus_root=None, base=None) -> None:
    target = target.resolve(strict=True)
    if source_path.resolve(strict=True) == target:
        raise ValueError("The source and public dataset must differ.")
    baseline = target.stat()
    with tempfile.TemporaryDirectory(dir=target.parent) as directory:
        staged = Path(directory) / target.name
        shutil.copy2(base or target, staged)
        with closing(sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            source.execute("BEGIN")
            with closing(libsql.connect(str(staged))) as output:
                output.execute("BEGIN")
                website_pages = website_page_credits(website_corpus_root, source) if website_corpus_root else {}
                if website_corpus_root:
                    websites = import_website_scrapes(source, output, website_pages)
                    print(f"Website scrapes: {sum(websites.values()):,} units from {len(websites)} sources", flush=True)
                    output.execute("INSERT INTO corpus_fts(corpus_fts) VALUES ('rebuild')")
                rebuild_word_frequencies(output, source, website_pages)
                print(output.execute(
                    "SELECT lang, count(*), sum(freq) FROM word_frequencies GROUP BY lang"
                ).fetchall(), flush=True)
                output.commit()
                if output.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise ValueError("Public database integrity check failed.")
        verify_public_data(staged)
        current = target.stat()
        if (baseline.st_ino, baseline.st_mtime_ns) != (current.st_ino, current.st_mtime_ns):
            raise RuntimeError("The public database changed while rebuilding its word bag.")
        os.replace(staged, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Unified corpus database to read")
    parser.add_argument("public", type=Path, help="Existing public database to refresh")
    parser.add_argument("--website-corpus-root", type=Path,
                        help="Corpus workspace with source selections and saved HTML manifests")
    parser.add_argument("--base", type=Path, help="Clean public snapshot to use as the starting point")
    args = parser.parse_args()
    refresh(args.source, args.public, args.website_corpus_root, args.base)
