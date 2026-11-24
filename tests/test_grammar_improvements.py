import json
import unittest
from unittest.mock import patch

from vro_mcp.config import load_settings
from vro_mcp.tools import VroTools


class TestGrammarImprovements(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = load_settings()
        cls.tools = VroTools(cls.settings)

    def test_paradigm_json_files_valid(self) -> None:
        vro_path = self.settings.resources_dir / "vro" / "paradigms.json"
        mulgi_path = self.settings.resources_dir / "mulgi" / "paradigms.json"
        self.assertTrue(vro_path.exists())
        self.assertTrue(mulgi_path.exists())

        vro_data = json.loads(vro_path.read_text(encoding="utf-8"))
        self.assertEqual(len(vro_data["types"]), 90)
        self.assertEqual(vro_data["types"]["54"]["pos_group"], "verbal")
        self.assertEqual(vro_data["types"]["54"]["forms"]["inf_ma"], "süü:mä")
        self.assertEqual(vro_data["types"]["54"]["forms"]["inf_da"], "süvväq")

        mulgi_data = json.loads(mulgi_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(mulgi_data["types"]), 24)
        self.assertIn("ammas", mulgi_data["types"])

    def test_lookup_word_include_paradigm_opt_in(self) -> None:
        def example_lookup(*args, **kwargs):
            return {"testword": [{"lang": "vro", "inflection_type": "54"}, {"lang": "vro"}]}

        with patch.object(self.tools._get_south_estonian(), "lookup_words", side_effect=example_lookup):
            default = self.tools.lookup_words("testword", lang="vro")["testword"]
            expanded = self.tools.lookup_words("testword", lang="vro", include_paradigm=True)["testword"]
        self.assertNotIn("paradigm", default[0])
        self.assertNotIn("paradigm", expanded[1])
        self.assertEqual(expanded[0]["paradigm"]["type"], "54")
        self.assertEqual(expanded[0]["paradigm"]["forms"]["inf_da"], "süvväq")

    def test_get_grammar_resource_returns_available_topics_on_missing(self) -> None:
        res = self.tools.get_grammar_resource(lang="tartu", topic="paradigms")
        self.assertFalse(res.get("available"))
        self.assertEqual(res.get("error"), "resource_not_found")
        self.assertIn("available_topics", res)
        self.assertIn("inflection-tables", res["available_topics"])
        self.assertIn("pronouns", res["available_topics"])
        self.assertNotIn("paradigms", res["available_topics"])

    def test_get_grammar_resource_returns_available_topics_on_invalid_topic(self) -> None:
        res = self.tools.get_grammar_resource(lang="lutsi", topic="nonexistent")
        self.assertEqual(res.get("error"), "invalid_topic")
        self.assertIn("available_topics", res)
        self.assertIn("pronouns", res["available_topics"])
        self.assertIn("inflection-tables", res["available_topics"])


if __name__ == "__main__":
    unittest.main()
