import unittest

from scripts.import_smugri4 import paired_units
from vro_mcp.db import _document_excerpt


class Smugri4PairTests(unittest.TestCase):
    def test_matching_line_boundaries_allow_parallel_examples(self):
        row = {"vro": "Üts.\n\nKats.", "est": "Üks.\n\nKaks."}
        self.assertEqual(list(paired_units(row, "vro-est", "vro")), [
            (0, "sentence", "Üts.", {"et": "Üks."}),
            (1, "sentence", "", {"et": ""}),
            (2, "sentence", "Kats.", {"et": "Kaks."}),
        ])

    def test_different_blank_line_positions_keep_the_whole_pair(self):
        row = {"vro": "Üts.\n\nKats.", "est": "Üks.\nKaks.\n "}
        self.assertEqual(list(paired_units(row, "vro-est", "vro")), [
            (0, "document", row["vro"], {"et": row["est"]}),
        ])

    def test_multilingual_appeal_preserves_all_targets(self):
        row = {"vro": "Üts.", "est": "Üks.", "eng": "One.", "deu": "Eins."}
        self.assertEqual(list(paired_units(row, "cifu_poordamine", "vro")), [
            (0, "paragraph", "Üts.", {"et": "Üks.", "en": "One.", "de": "Eins."}),
        ])

    def test_document_excerpt_retains_a_match_past_the_first_page(self):
        text = "esimene " * 1000 + "kraasna" + " viimane" * 1000
        excerpt = _document_excerpt(text, "Kraasna", limit=80)
        self.assertLessEqual(len(excerpt), 80)
        self.assertTrue(excerpt.startswith("…") and excerpt.endswith("…"))
        self.assertIn("kraasna", excerpt)
