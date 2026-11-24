from __future__ import annotations

import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from vro_mcp.config import load_settings
from vro_mcp.db import SouthEstonianStore, normalize_db_text


class DictionaryDiacriticsTests(unittest.TestCase):
    def test_raised_vowel_marks_are_optional_but_vowel_letters_remain_distinct(self):
        self.assertEqual(normalize_db_text('tsu̬u̬ń'), 'tsuun')
        self.assertEqual(normalize_db_text('vü̬ü̬'), 'vüü')
        self.assertNotEqual(normalize_db_text('vü̬ü̬'), normalize_db_text('vuu'))
        self.assertEqual(normalize_db_text('õäöü'), 'õäöü')

    def test_legacy_headword_and_inflection_keys_are_found_and_cached(self):
        store = SouthEstonianStore(load_settings().south_estonian_db)
        with sqlite3.connect(':memory:') as conn:
            conn.execute('CREATE TABLE dict_entries (lookup_key TEXT)')
            conn.execute('CREATE TABLE dict_inflections (lookup_key TEXT)')
            conn.execute('INSERT INTO dict_entries VALUES (?)', ('tsu̬u̬n',))
            conn.execute('INSERT INTO dict_inflections VALUES (?)', ('tsu̬u̬ni',))
            self.assertEqual(store._dictionary_lookup_keys(conn, 'tsuun'), ['tsuun', 'tsu̬u̬n'])
            self.assertEqual(store._dictionary_lookup_keys(conn, 'tsuuni'), ['tsuuni', 'tsu̬u̬ni'])
            # New datasets with normalized keys use the ordinary indexed lookup.
            self.assertEqual(store._dictionary_lookup_keys(conn, 'muu'), ['muu'])
            conn.execute('DROP TABLE dict_entries')
            conn.execute('DROP TABLE dict_inflections')
            self.assertEqual(store._dictionary_lookup_keys(conn, 'tsuun'), ['tsuun', 'tsu̬u̬n'])

    def test_public_lookup_preserves_marked_headword_for_both_spellings(self):
        schema = Path(__file__).resolve().parents[1] / "scripts/public_data_schema.sql"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dictionary.db"
            with closing(sqlite3.connect(path)) as conn:
                conn.executescript(schema.read_text())
                conn.executemany(
                    "INSERT INTO dict_entries (entry_id, lang, headword, lookup_key, source_slug) "
                    "VALUES (?, 'vro', ?, ?, 'fixture')",
                    [(str(i), headword, normalize_db_text(headword))
                     for i, headword in enumerate(("tsu̬u̬ń", "vü̬ü̬"))],
                )
                conn.commit()
            store = SouthEstonianStore(path)
            try:
                for query in ("tsuun", "tsuuń", "tsu̬u̬ń", "vüü", "vü̬ü̬"):
                    expected = "tsu̬u̬ń" if query.startswith("ts") else "vü̬ü̬"
                    with self.subTest(query=query):
                        rows = store.lookup_word(query, lang="vro")
                        self.assertEqual(rows[0]["headword"], expected)
                        self.assertEqual(rows[0]["matched_via"], "headword")
            finally:
                store.close()
