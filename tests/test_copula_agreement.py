from __future__ import annotations

import unittest
from unittest.mock import patch

from vro_mcp.config import load_settings
from vro_mcp.tools import VroTools


class CopulaAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tools = VroTools(load_settings())

    def test_profile_findings_with_existing_analysers(self) -> None:
        for lang, subject, correction, matching, ambiguous in (
            ("mulgi", "Mia", "ole", "Mia ole kodun.", "Sia om kodun."),
            ("seto", "Mina", "olõ", "Mina olõ kotoh.", "Ma om kotoh."),
        ):
            with self.subTest(lang=lang):
                if not self.tools.giella.availability(lang=lang)["grammar"]["available"]:
                    self.skipTest(f"{lang} GiellaLT analyser unavailable")
                text = f"😀. {subject} om. {subject} OM."
                start = len(f"😀. {subject} ".encode("utf-16-le")) // 2
                result = self.tools.grammar_check(text, lang=lang, limit=1)
                self.assertEqual(
                    result,
                    {
                        "errors": [{
                            "word": "om",
                            "span": [start, start + 2],
                            "code": "copula-agreement",
                            "suggestions": [correction],
                        }],
                        "returned": 1,
                        "total_errors": 2,
                    },
                )
                second_person = self.tools.grammar_check("Sina OM.", lang=lang)
                self.assertEqual(second_person["errors"][0]["suggestions"], [f"{correction}t".upper()])
                for control in (matching, ambiguous, f"{subject} xyzzy.", f"{subject}, om."):
                    self.assertEqual(self.tools.grammar_check(control, lang=lang)["errors"], [])

    def test_analyser_failure_is_reported(self) -> None:
        with patch.object(self.tools.giella, "analyze_words", return_value={
            "available": True,
            "exit_code": 1,
            "stderr": "analyser failed",
        }):
            result = self.tools.grammar_check("Mia om.", lang="mulgi")
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "grammar_analyzer_failed")
