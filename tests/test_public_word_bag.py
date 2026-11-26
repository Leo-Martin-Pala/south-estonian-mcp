import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import libsql

from scripts.public_word_bag import rebuild_word_frequencies
from scripts.public_website_scrapes import import_website_scrapes, website_page_credits


class PublicWordBagTests(unittest.TestCase):
    def test_requires_distinct_documents_and_does_not_copy_overlapping_units(self):
        unit_schema = """CREATE TABLE corpus_units (
            lang TEXT, doc_id TEXT, unit_level TEXT, text TEXT, source_slug TEXT DEFAULT 'licensed'
        )"""
        with closing(sqlite3.connect(":memory:")) as source, closing(libsql.connect(":memory:")) as output:
            source.execute(unit_schema)
            output.execute(unit_schema)
            output.execute("CREATE TABLE word_frequencies (lang TEXT, lookup_key TEXT, form TEXT, freq INTEGER)")
            source.executemany("INSERT INTO corpus_units (lang, doc_id, unit_level, text) VALUES (?, ?, ?, ?)", [
                ("vro", "a", "sentence", "Kivi kivi ainu @kasutaja"),
                ("vro", "a", "paragraph", "kivi kivi"),
                ("vro", "b", "utterance", "kivi @kasutaja"),
                ("vro", "c", "document", "avalik üts"),
                ("seto", "d", "sentence", "kivi"),
            ])
            source.execute("INSERT INTO corpus_units VALUES ('vro', 'file', 'document', 'avalik', 'mulgimaa_website')")
            output.executemany("INSERT INTO corpus_units (lang, doc_id, unit_level, text) VALUES (?, ?, ?, ?)", [
                ("vro", "copy", "sentence", "Kivi  kivi ainu @kasutaja"),
                ("vro", "e", "paragraph", "avalik"),
                ("seto", "d", "sentence", "kivi teist"),
            ])

            rebuild_word_frequencies(output, source)

            self.assertEqual(output.execute(
                "SELECT lang, form, freq FROM word_frequencies ORDER BY lang, form"
            ).fetchall(), [("vro", "avalik", 2), ("vro", "kivi", 3)])
            self.assertEqual(output.execute(
                "SELECT minimum_documents, input_rights_status FROM word_frequency_metadata"
            ).fetchall(), [(2, "mixed-including-unknown")])

    def test_website_import_retains_unknown_and_document_credit(self):
        schema = (Path(__file__).resolve().parents[1] / "scripts/public_data_schema.sql").read_text()
        with closing(sqlite3.connect(":memory:")) as source, closing(libsql.connect(":memory:")) as output:
            source.executescript(schema)
            output.executescript(schema)
            source.executemany("""
                INSERT INTO corpus_units
                    (unit_id, lang, unit_level, doc_id, unit_idx, source_slug, text, lid_lang, lid_conf, orig_vec)
                VALUES (?, 'vro', 'sentence', ?, 0, ?, 'Example', 'vro', 100, NULL)
            """, [
                ("web-unit", "web-doc", "wi_ee"),
                ("attachment-unit", "attachment-doc", "wi_ee"),
                ("file-unit", "file-doc", "wi_ee"),
                ("private-unit", "private-doc", "vro_facebook"),
            ])
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "configs").mkdir()
                (root / "raw").mkdir()
                (root / "configs/sources.yaml").write_text(json.dumps([{"slug": "wi_ee", "raw_path": "raw"}]))
                (root / "configs/corpus_releases.json").write_text(json.dumps({
                    "source_selections": {"vro": {"path": "selection.json"}},
                }))
                url = "https://wi.ee/example/"
                pdf = "https://wi.ee/download.pdf"
                (root / "selection.json").write_text(json.dumps({"documents": [
                    {"doc_id": "web-doc", "source_slug": "wi_ee", "title": "Example", "author": "Author", "url": url},
                    {"doc_id": "attachment-doc", "source_slug": "wi_ee", "url": pdf},
                    {"doc_id": "file-doc", "source_slug": "wi_ee", "url": url,
                     "meta_json": {"raw_file": "download.pdf"}},
                ]}))
                (root / "raw/example.html").write_text("<p>Example</p>")
                (root / "raw/manifest.jsonl").write_text("\n".join([
                    json.dumps({"kind": "page", "content_type": "text/html; charset=UTF-8", "url": url,
                                "html_file": "example.html"}),
                    json.dumps({"kind": "file", "content_type": "application/pdf", "url": pdf}),
                ]))
                credits = website_page_credits(root, source)
                self.assertEqual(import_website_scrapes(source, output, credits), {"wi_ee": 1})
                self.assertEqual(import_website_scrapes(source, output, credits), {"wi_ee": 1})
            self.assertEqual(output.execute("SELECT source_slug, license FROM sources").fetchall(),
                             [("wi_ee", "unknown")])
            self.assertEqual(output.execute("SELECT doc_id, author, source_url FROM corpus_documents").fetchall(),
                             [("web-doc", "Author", "https://wi.ee/example/")])
            self.assertEqual(output.execute("SELECT unit_id FROM corpus_units").fetchall(), [("web-unit",)])
