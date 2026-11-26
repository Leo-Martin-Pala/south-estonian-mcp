"""Import the explicitly listed website scrapes with source attribution."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from vro_mcp.db import PUBLIC_SOURCES

WEBSITE_SOURCES = {slug: policy for slug, policy in PUBLIC_SOURCES.items() if policy.get("website_scrape")}
WEBSITE_INPUTS = WEBSITE_SOURCES.keys() | {"mulgimaa_website"}
HTML_TYPES = {"text/html", "application/xhtml+xml"}
DOWNLOAD_SUFFIXES = {
    ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".ppt", ".pptx",
    ".xls", ".xlsx", ".zip", ".gz", ".7z", ".epub",
}


def page_url(url):
    return (url or "").split("#", 1)[0].rstrip("/").lower()


def captured_html_urls(directory: Path):
    directory = directory.resolve()
    with (directory / "manifest.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            content_type = (row.get("content_type") or "").split(";", 1)[0].strip().lower()
            if row.get("kind") != "page" or content_type not in HTML_TYPES or not row.get("html_file"):
                continue
            path = (directory / row["html_file"]).resolve()
            if not path.is_relative_to(directory) or not path.is_file():
                continue
            for url in (row.get("url"), row.get("final_url")):
                if not url:
                    continue
                parsed = urlsplit(url)
                if parsed.scheme in {"http", "https"} and Path(parsed.path).suffix.lower() not in DOWNLOAD_SUFFIXES:
                    yield page_url(url)


def website_page_credits(corpus_root: Path, source):
    """Match source documents to saved HTTP HTML responses, by source and URL."""
    config = json.loads((corpus_root / "configs/sources.yaml").read_text())
    captures = {
        entry["slug"]: set(captured_html_urls(corpus_root / entry["raw_path"]))
        for entry in config if entry["slug"] in WEBSITE_SOURCES
    }
    releases = json.loads((corpus_root / "configs/corpus_releases.json").read_text())
    placeholders = ",".join("?" for _ in WEBSITE_SOURCES)
    wanted = {}
    for lang, slug, doc_id in source.execute(f"""
        SELECT DISTINCT lang, source_slug, doc_id FROM corpus_units
        WHERE source_slug IN ({placeholders})
    """, tuple(WEBSITE_SOURCES)):
        wanted.setdefault(lang, set()).add((slug, doc_id))
    credits = {}
    for lang, doc_ids in wanted.items():
        selection = corpus_root / releases["source_selections"][lang]["path"]
        for doc in json.loads(selection.read_text())["documents"]:
            slug = doc["source_slug"]
            key = slug, doc["doc_id"]
            url = doc.get("url")
            if key not in doc_ids or page_url(url) not in captures.get(slug, ()):
                continue
            meta = doc.get("meta_json") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            raw_file = meta.get("raw_file") or meta.get("pages_file")
            if doc.get("source_kind") == "website_file" or (
                raw_file and Path(raw_file).suffix.lower() not in {".html", ".htm", ".xhtml"}
            ):
                continue
            credits[key] = (doc.get("title"), doc.get("author"), url)
    return credits


def import_website_scrapes(source, output, documents):
    totals = {}
    for slug, policy in WEBSITE_SOURCES.items():
        columns = "unit_id, lang, unit_level, doc_id, unit_idx, source_slug, text, lid_lang, lid_conf, orig_vec"
        rows = source.execute(
            f"SELECT {columns} FROM corpus_units WHERE source_slug = ? ORDER BY id", (slug,)
        )
        expected = 0
        while batch := rows.fetchmany(500):
            batch = [row for row in batch if (slug, row[3]) in documents]
            if not batch:
                continue
            expected += len(batch)
            output.executemany(f"""
                INSERT INTO corpus_units ({columns}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(unit_id) DO NOTHING
            """, batch)

        langs = output.execute("SELECT lang, count(*) FROM corpus_units WHERE source_slug = ? GROUP BY lang", (slug,)).fetchall()
        total = sum(count for _, count in langs)
        if total != expected:
            raise ValueError(f"{slug}: expected {expected} website units, found {total}")
        if not total:
            continue
        doc_ids = output.execute("SELECT DISTINCT doc_id FROM corpus_units WHERE source_slug = ?", (slug,)).fetchall()
        output.executemany("""
            INSERT INTO corpus_documents (doc_id, title, author, source_url) VALUES (?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET title=excluded.title, author=excluded.author, source_url=excluded.source_url
        """, [(doc_id, *documents[(slug, doc_id)]) for doc_id, in doc_ids])
        output.execute("""
            INSERT INTO sources
                (source_slug, langs, unit_count, translation_count, dict_entry_count, sample_title, sample_url, license)
            VALUES (?, ?, ?, 0, 0, ?, ?, ?)
            ON CONFLICT(source_slug) DO UPDATE SET unit_count=excluded.unit_count, langs=excluded.langs, license=excluded.license
        """, (slug, json.dumps([lang for lang, _ in langs]), total, policy["title"], policy["url"], policy["license"]))
        totals[slug] = total
    return totals
