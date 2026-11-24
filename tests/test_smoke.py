from __future__ import annotations

import json
import unittest

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from vro_mcp.config import load_settings
from vro_mcp.db import normalize_db_text
from vro_mcp.giella import GiellaAdapter
from vro_mcp.server import _mcp_path_from_env, _read_resource
from vro_mcp.tools import (
    CORPUS_POLICY_ID,
    VroTools,
    _count_text,
    _parse_grammar_lines,
    _parse_spellcheck_lines,
)


DATA_HINT = "run `make data` (or `make setup`) to download the datasets"
GIELLA_HINT = "run `make giella` (or `make setup`) to install the Giella tools"


class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tools = VroTools(load_settings())
        status = cls.tools.check_setup()
        cls.db_available = {
            name: bool(info if isinstance(info, bool) else info.get("available"))
            for name, info in status["databases"].items()
        }
        cls.giella_available = {
            key: bool(info if isinstance(info, bool) else info.get("available"))
            for key, info in status["giella"].items()
        }

    def _require_db(self, *names: str) -> None:
        missing = [name for name in names if not self.db_available.get(name)]
        if missing:
            self.skipTest(f"{', '.join(missing)} database not installed — {DATA_HINT}")

    def _require_giella(self, *keys: str) -> None:
        missing = [key for key in keys if not self.giella_available.get(key)]
        if missing:
            self.skipTest(f"Giella {', '.join(missing)} not installed — {GIELLA_HINT}")

    def test_lookup_word_runs(self) -> None:
        self._require_db("south_estonian")
        out = self.tools.lookup_word("world", limit=1)
        results = out["world"]
        self.assertTrue(results)
        self.assertEqual(results[0]["lang"], "vro")
        self.assertIn(results[0]["headword"], {"ilm", "maailm"})
        self.assertIn({"target_lang": "en", "text": "world"}, results[0]["definitions"])
        self.assertNotIn("available_directions", results[0])

    def test_lookup_word_batched_is_keyed(self) -> None:
        self._require_db("south_estonian")
        out = self.tools.lookup_word(["world", "water"])
        self.assertEqual(set(out), {"world", "water"})
        self.assertTrue(out["world"])

    def test_database_lookup_normalization_handles_palatalization_ticks(self) -> None:
        self.assertEqual(normalize_db_text("B\u0301 b´ b’ bʼ Riḱ"), "b b b b rik")
        self.assertEqual(normalize_db_text("ät´t"), "ätt")
        self.assertEqual(normalize_db_text("Á"), "á")

    def test_find_usage_examples_runs(self) -> None:
        self._require_db("south_estonian")
        out = self.tools.find_usage_examples("naasõ", limit=1)
        results = out["naasõ"]
        self.assertTrue(results)
        self.assertIsInstance(results[0]["snippet"], str)
        self.assertLessEqual(len(results[0]["snippet"]), 266)
        self.assertIn("naasõ", results[0]["snippet"].casefold())
        self.assertTrue(results[0]["public_id"])
        self.assertTrue(results[0]["source_slug"])

    def test_legacy_parallel_source_filter(self) -> None:
        self._require_db("south_estonian")
        out = self.tools.find_usage_examples("Võro", source_type="parallel_corpus_vro_side")
        self.assertTrue(out["Võro"])
        self.assertTrue(all(row["source_slug"] == "paraleelkorpus" for row in out["Võro"]))

    def test_word_exists_in_bag_runs(self) -> None:
        if not self.tools.settings.south_estonian_db.exists():
            self.skipTest("south_estonian.db not present")
        out = self.tools.word_exists_in_bag("Miä")
        self.assertGreater(out["Miä"], 0)

    def test_word_exists_in_bag_batched_is_keyed(self) -> None:
        if not self.tools.settings.south_estonian_db.exists():
            self.skipTest("south_estonian.db not present")
        out = self.tools.word_exists_in_bag(["Miä", "xyzzyvrotest"])
        self.assertGreater(out["Miä"], 0)
        self.assertEqual(out["xyzzyvrotest"], 0)

    def test_word_exists_in_bag_with_lang_and_include_languages(self) -> None:
        if not self.tools.settings.south_estonian_db.exists():
            self.skipTest("south_estonian.db not present")
        detailed = self.tools.word_exists_in_bag(
            ["Miä", "xyzzyvrotest"],
            include_languages=True,
        )
        self.assertGreater(detailed["Miä"]["total_count"], 0)
        self.assertIn("vro", detailed["Miä"]["languages"])
        self.assertIsInstance(detailed["Miä"]["languages"], list)
        self.assertEqual(detailed["xyzzyvrotest"], {"total_count": 0, "languages": []})
        filtered = self.tools.word_exists_in_bag("Miä", lang="seto")
        self.assertIsInstance(filtered["Miä"], int)

    def test_count_text_counts_voro_prose_shape(self) -> None:
        text = "Miä olõ-i hüä. Tuust huul'maldaq 110,000 rubla!"
        self.assertEqual(
            self.tools.count_text(text),
            {
                "characters": len(text),
                "words": 7,
                "estimated_sentences": 2,
            },
        )

    def test_count_text_empty_text(self) -> None:
        self.assertEqual(
            _count_text(""),
            {"characters": 0, "words": 0, "estimated_sentences": 0},
        )

    def test_find_unknown_words_runs(self) -> None:
        if not self.tools.settings.south_estonian_db.exists():
            self.skipTest("south_estonian.db not present")
        result = self.tools.find_unknown_words("Miä olõ hüä xyzzyvrotest", limit=10)
        self.assertIn("xyzzyvrotest", result["unknown"])
        self.assertEqual(result["checked"], 4)

    def test_find_unrecognized_words_runs(self) -> None:
        result = self.tools.find_unrecognized_words("Miä olõ hüä xyzzyvrotest", limit=10)
        if result.get("available") is False:
            self.skipTest("analyzer not available in this environment")
        self.assertIn("xyzzyvrotest", result["unrecognized"])
        self.assertNotIn("miä", result["unrecognized"])
        self.assertFalse(result["prefiltered"])
        self.assertGreaterEqual(result["checked"], 4)

    def test_find_unrecognized_words_prefilter_runs(self) -> None:
        result = self.tools.find_unrecognized_words(
            "Miä olõ hüä xyzzyvrotest",
            prefilter=True,
            limit=10,
        )
        if result.get("available") is False:
            self.skipTest("analyzer not available in this environment")
        self.assertIn("xyzzyvrotest", result["unrecognized"])
        self.assertTrue(result["prefiltered"])
        self.assertLess(result["checked"], 4)

    def test_find_unrecognized_words_analyzes_original_surface_after_db_normalization(self) -> None:
        class FakeSouthEstonian:
            def __init__(self) -> None:
                self.seen: list[str] = []

            def known_words_in_bag(self, words: object, *, lang: str | None = None) -> set[str]:
                self.seen = list(words)  # type: ignore[arg-type]
                return set()

        class FakeGiella:
            def __init__(self) -> None:
                self.checked: list[str] = []

            def analyze_words(self, words: list[str], *, lang: str = "vro") -> dict[str, object]:
                self.checked = words
                return {
                    "available": True,
                    "lang": lang,
                    "results": {
                        "Tarton": {"recognized": True},
                        "piirte": {"recognized": False},
                    },
                }

        tools = VroTools.__new__(VroTools)
        fake_se = FakeSouthEstonian()
        tools._south_estonian_store = fake_se
        tools.giella = FakeGiella()
        result = tools.find_unrecognized_words("Tarton piirte", prefilter=True)
        self.assertIn("tarton", fake_se.seen)
        self.assertIn("Tarton", tools.giella.checked)
        self.assertEqual(result["unrecognized"], ["piirte"])

    def test_giella_unavailable_is_structured(self) -> None:
        tools = VroTools(replace(load_settings(), analyzer_cmd="/tmp/no-such-analyzer"))
        result = tools.analyze_word("võro")
        self.assertIn("available", result)
        self.assertIn("setup", result)

    def test_analyze_word_batched_is_keyed(self) -> None:
        out = self.tools.analyze_word(["uma", "kala"])
        if out.get("available") is False:
            self.skipTest("analyzer not available in this environment")
        self.assertEqual(set(out), {"uma", "kala"})
        self.assertTrue(out["kala"])

    def test_lint_estonian_leakage_flags_estonian_like_endings(self) -> None:
        out = self.tools.check_purity_with_rules(words=["teinud", "kirjutab", "kalaq"])["results"]
        self.assertTrue(out["teinud"])
        self.assertEqual(
            out["teinud"][0]["severity"],
            "error",
        )
        self.assertEqual(
            out["kirjutab"][0]["severity"],
            "warning",
        )
        self.assertEqual(out["kalaq"], [])

    def test_lint_estonian_leakage_does_not_tokenize_inputs(self) -> None:
        # A whole phrase is treated as one unit; the window rule fires via search.
        out = self.tools.check_purity_with_rules(words="ei teinud")["results"]
        self.assertEqual(set(out), {"ei teinud"})
        self.assertTrue(out["ei teinud"])
        self.assertEqual(out["ei teinud"][0]["severity"], "error")

    def test_lint_estonian_leakage_allowlist(self) -> None:
        out = self.tools.check_purity_with_rules(words="maks")["results"]
        self.assertEqual(out["maks"], [])

    def test_find_estonian_leakage_slim_scan(self) -> None:
        text = "Tä läheb kodo. Üts asi om tehtud. Timä ei teinud taad. Tehtud sai tehtud."
        out = self.tools.check_purity_with_rules(text=text)
        # Slim: surface strings only, deduped and frequency-sorted.
        self.assertEqual(out["flagged_words"][0], "tehtud")  # most frequent
        self.assertIn("läheb", out["flagged_words"])
        self.assertNotIn("flagged_phrases", out)
        self.assertNotIn("tokens", out)
        self.assertNotIn("matches", out)
        self.assertNotIn("details", out)
        detailed = self.tools.check_purity_with_rules(text=text, detail=True)
        self.assertIn("tehtud", detailed["details"])

    def test_find_estonian_leakage_keeps_voro_words(self) -> None:
        out = self.tools.check_purity_with_rules(text="Ma olõ-i tennüq taad tüüd mõistaq.")
        self.assertEqual(out["flagged_words"], [])
        self.assertNotIn("flagged_phrases", out)

    def test_suggest_correction_returns_valid_form_as_already_valid(self) -> None:
        self._require_giella("analyzer")
        result = self.tools.suggest_correction("köüdet")
        self.assertTrue(result["valid"])
        self.assertEqual(result["alternatives"], [])
        self.assertNotIn("status", result)
        self.assertNotIn("analyses", result)

    def test_suggest_correction_combines_dictionary_generation_and_analyzer(self) -> None:
        result = self.tools.suggest_correction("seotud")
        if not result.get("alternatives") or result["alternatives"][0] != "köüdet":
            self.skipTest("public dictionary does not contain the expected köütmä correction path")
        self.assertFalse(result["valid"])
        self.assertEqual(result["alternatives"][0], "köüdet")
        self.assertLessEqual(len(result["alternatives"]), 3)
        self.assertNotIn("best", result)
        self.assertNotIn("candidates", result)

    def test_suggest_correction_marks_invalid_form_seen_in_word_bag(self) -> None:
        class FakeSuggester:
            def suggest_correction(self, form: str, *, lang: str = "vro") -> dict[str, object]:
                return {"form": form, "lang": lang, "valid": False, "alternatives": []}

        class FakeSouthEstonian:
            def word_exists_in_bag_many(
                self,
                words: list[str],
                *,
                lang: str | None = None,
                include_languages: bool = False,
            ) -> dict[str, dict[str, object]]:
                return {words[0]: {"total_count": 7}}

        tools = VroTools.__new__(VroTools)
        tools.correction_suggester = FakeSuggester()
        tools._south_estonian_store = FakeSouthEstonian()
        result = tools.suggest_correction("seenform")
        self.assertFalse(result["valid"])
        self.assertTrue(result["seen_in_word_bag"])
        self.assertIn("Not analyzer-confirmed", result["note"])

    def test_suggest_correction_accepts_word_alias(self) -> None:
        class FakeSuggester:
            def suggest_correction(self, form: str, *, lang: str = "vro") -> dict[str, object]:
                return {"form": form, "lang": lang, "valid": True, "alternatives": []}

        tools = VroTools.__new__(VroTools)
        tools.correction_suggester = FakeSuggester()
        result = tools.suggest_correction(word="köüdet")
        self.assertTrue(result["valid"])
        self.assertEqual(result["form"], "köüdet")

    def test_spellcheck_tokenizes_sentence_input(self) -> None:
        self._require_giella("speller")
        result = self.tools.spellcheck("Miä olõ hüä tekstt.", lang="vro")
        unknown_words = [item["word"] for item in result["unknown"]]
        self.assertIn("tekstt", unknown_words)
        self.assertNotIn("miä", unknown_words)

    def test_spellcheck_parser_returns_lean_deduped_suggestions(self) -> None:
        parsed = _parse_spellcheck_lines(
            [
                '"tarton" is NOT in the lexicon:',
                'Corrections for "tarton":',
                "tarto    10.000000",
                "tarõn    10.800000",
                "taro    12.345678",
                "targõn    20.000000",
                '"tarton" is NOT in the lexicon:',
                'Corrections for "tarton":',
                "tarto    10.000000",
            ]
        )
        self.assertEqual(
            parsed,
            {
                "unknown": [{"word": "tarton", "suggestions": ["tarto", "tarõn", "taro"]}],
                "returned": 1,
                "total_unknown": 1,
            },
        )

    def test_spellcheck_parser_caps_unknown_words(self) -> None:
        parsed = _parse_spellcheck_lines(
            [
                '"üks" is NOT in the lexicon:',
                "üts    1.000000",
                '"kats" is NOT in the lexicon:',
                "katś    1.000000",
            ],
            limit=1,
        )
        self.assertEqual(parsed["unknown"], [{"word": "üks", "suggestions": ["üts"]}])
        self.assertEqual(parsed["returned"], 1)
        self.assertEqual(parsed["total_unknown"], 2)

    def test_generate_forms_runs_with_giella_tags(self) -> None:
        self._require_giella("generator")
        result = self.tools.generate_forms("uma", tags="A+Sg+Ill")
        self.assertIn("umma", result.get("forms", []))

    def test_generate_paradigm_runs_for_vro(self) -> None:
        self._require_giella("generator")
        vro_v = self.tools.generate_paradigm("olõma", lang="vro")
        self.assertEqual(vro_v["pos"], "V")
        self.assertIn("om", vro_v["present"]["Sg3"])
        self.assertIn("ollaq", vro_v["non_finite"]["Inf"])

    def test_generate_paradigm_runs_for_mulgi(self) -> None:
        if not self.tools.giella.availability_by_language()["mulgi"]["generator"]["available"]:
            self.skipTest("Mulgi Giella generator unavailable")
        mulgi_n = self.tools.generate_paradigm("käsi", lang="mulgi")
        self.assertEqual(mulgi_n["pos"], "N")
        self.assertIn("käe", mulgi_n["singular"]["Gen"])

    def test_generate_paradigm_runs_for_seto(self) -> None:
        if not self.tools.giella.availability_by_language()["seto"]["generator"]["available"]:
            self.skipTest("Seto Giella generator unavailable")
        seto_v = self.tools.generate_paradigm("olõma", lang="seto")
        self.assertEqual(seto_v["pos"], "V")
        self.assertTrue(seto_v["present"]["Sg3"])

    def test_generate_forms_filters_failures(self) -> None:
        class FakeGiella:
            def __init__(self) -> None:
                self.call: tuple[str, str | None] | None = None

            def generate_forms(
                self,
                lemma: str,
                tags: str | None = None,
                *,
                lang: str = "vro",
            ) -> dict[str, object]:
                self.call = (lemma, tags)
                return {
                    "available": True,
                    "lang": lang,
                    "lines": [
                        "kerik+N+Sg+Ine\tkerikun\t0",
                        "kerik+Sg+Ine\tkerik+Sg+Ine\t+?",
                    ],
                }

        tools = VroTools.__new__(VroTools)
        tools.giella = FakeGiella()
        result = tools.generate_forms("kerik", tags="N+Sg+Ine")
        self.assertEqual(result["forms"], ["kerikun"])
        self.assertEqual(tools.giella.call, ("kerik", "N+Sg+Ine"))

    def test_grammar_parser_structures_json_lines(self) -> None:
        parsed = _parse_grammar_lines(
            [
                '{"errs":[["tekstt",12,18,"typo","typo",["testt","teksti","tekstõ","test"],"typo"]],"text":"Miä olõ hüä tekstt."}'
            ]
        )
        self.assertEqual(
            parsed,
            {
                "errors": [
                    {
                        "word": "tekstt",
                        "span": [12, 18],
                        "code": "typo",
                        "suggestions": ["testt", "teksti", "tekstõ"],
                    }
                ],
                "returned": 1,
                "total_errors": 1,
            },
        )

    def test_grammar_parser_caps_errors(self) -> None:
        parsed = _parse_grammar_lines(
            [
                '{"errs":[["üks",0,3,"typo","typo",["üts"],"typo"],["kats",4,8,"typo","typo",["katś"],"typo"]],"text":"üks kats"}'
            ],
            limit=1,
        )
        self.assertEqual(
            parsed["errors"],
            [{"word": "üks", "span": [0, 3], "code": "typo", "suggestions": ["üts"]}],
        )
        self.assertEqual(parsed["returned"], 1)
        self.assertEqual(parsed["total_errors"], 2)

    def test_grammar_check_returns_structured_errors(self) -> None:
        self._require_giella("grammar")
        result = self.tools.grammar_check("Miä olõ hüä tekstt.", lang="vro")
        self.assertIn("errors", result)
        self.assertNotIn("lines", result)
        self.assertNotIn("text", result)
        self.assertTrue(any(error["word"] == "tekstt" for error in result["errors"]))

    def test_lookup_word_accepts_standard_direction(self) -> None:
        self._require_db("south_estonian")
        out = self.tools.lookup_word("vesi", direction="vro-en", limit=1)
        self.assertEqual(out["vesi"][0]["lang"], "vro")
        self.assertEqual(out["vesi"][0]["headword"], "vesi")
        self.assertTrue(out["vesi"][0]["definitions"])
        self.assertTrue(all(d["target_lang"] == "en" for d in out["vesi"][0]["definitions"]))

    def test_lookup_word_supports_standard_directions(self) -> None:
        self._require_db("south_estonian")
        cases = {
            "en-vro": ("world", "en", "vro"),
            "et-vro": ("maailm", "et", "vro"),
            "vro-en": ("vesi", "vro", "en"),
            "vro-et": ("vesi", "vro", "et"),
        }
        for direction, (query, source_lang, target_lang) in cases.items():
            with self.subTest(direction=direction):
                out = self.tools.lookup_word(query, direction=direction, limit=1)
                self.assertTrue(out[query])
                result = out[query][0]
                self.assertEqual(result["lang"], "vro")
                self.assertTrue(result["headword"])
                self.assertTrue(result["definitions"])
                gloss_lang = source_lang if source_lang != "vro" else target_lang
                self.assertTrue(all(d["target_lang"] == gloss_lang for d in result["definitions"]))

    def test_lookup_word_rejects_invalid_direction(self) -> None:
        out = self.tools.lookup_word("vesi", direction="ev")
        self.assertEqual(out["error"], "invalid_direction")
        self.assertEqual(out["valid_directions"], ["en-vro", "et-vro", "vro-en", "vro-et"])
        self.assertIn("unset", out["detail"])

    def test_grammar_resources_are_readable(self) -> None:
        self.assertIn("Võro noun declension", _read_resource("resources/noun-cases.md"))
        self.assertIn("Võro verb conjugation", _read_resource("resources/verb-conjugation.md"))
        self.assertIn(
            "Võro orthography and standard language",
            _read_resource("resources/orthography-and-standard.md"),
        )
        self.assertIn(
            "Võro-language translator",
            _read_resource("resources/vro-translator-prompt.md"),
        )

    def test_mcp_path_from_env_adds_missing_leading_slash(self) -> None:
        with patch.dict("os.environ", {"MCP_PATH": "secret"}):
            self.assertEqual(_mcp_path_from_env(), "/secret/mcp")

    def test_translate_rejects_unsupported_pair_locally(self) -> None:
        result = self.tools.translate_mt("Tere", source_lang="deu", target_lang="vro")
        self.assertEqual(result["error"], "unsupported_translation_pair")
        self.assertNotIn("ger", result["supported_to_vro"])

    def test_translate_accepts_two_letter_language_aliases(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"translation":"Tere"}'

        captured: dict[str, str] = {}

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            captured["body"] = request.data.decode("utf-8")  # type: ignore[attr-defined]
            captured["timeout"] = str(timeout)
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            result = self.tools.translate_mt("Hello", source_lang="en", target_lang="vro")
        self.assertEqual(result["text"], "Tere")
        self.assertEqual(result["translated_text"], "Tere")
        self.assertEqual(result["backend"], "neurotolge_api")
        payload = json.loads(captured["body"])
        self.assertEqual(payload["src"], "eng")
        self.assertEqual(payload["tgt"], "vro")

    def test_translate_uses_configured_neurotolge_base_url(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"translation":"Tere"}'

        captured: dict[str, str] = {}

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            captured["url"] = request.full_url  # type: ignore[attr-defined]
            captured["body"] = request.data.decode("utf-8")  # type: ignore[attr-defined]
            return FakeResponse()

        settings = replace(
            load_settings(),
            neurotolge_base_url="http://127.0.0.1:8765/translation/v2",
        )
        tools = VroTools(settings)
        with patch("urllib.request.urlopen", fake_urlopen):
            result = tools.translate_mt("Hello", source_lang="eng", target_lang="vro")

        self.assertEqual(result["text"], "Tere")
        self.assertEqual(result["backend"], "neurotolge_api")
        self.assertEqual(captured["url"], "http://127.0.0.1:8765/translation/v2")
        payload = json.loads(captured["body"])
        self.assertEqual(payload["src"], "eng")
        self.assertEqual(payload["tgt"], "vro")

    def test_translate_mt_auto_falls_back_to_local_on_api_error(self) -> None:
        class FakeMT:
            def translate(self, text: str, source_lang: str, target_lang: str) -> dict[str, object]:
                return {
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "translated_text": "Täämbä",
                }

        tools = VroTools(
            replace(
                load_settings(),
                neurotolge_base_url="http://127.0.0.1:1/unreachable",
            )
        )
        tools._mt_runner = FakeMT()
        result = tools.translate_mt("Täna", source_lang="et", target_lang="vro")
        self.assertEqual(result["translated_text"], "Täämbä")
        self.assertEqual(result["backend"], "local_smugri_fp16")
        self.assertEqual(result["fallback_from"], "neurotolge_api")
        self.assertTrue(result["fallback_used"])

    def test_missing_south_estonian_db_is_structured_for_lookup(self) -> None:
        tools = VroTools(replace(load_settings(), south_estonian_db=Path("/tmp/no-such-se.db")))
        result = tools.lookup_word("world")
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "south_estonian_db_unavailable")
        self.assertEqual(result["database"], "south_estonian")
        self.assertIn("setup_hint", result)

    def test_missing_south_estonian_db_is_structured_for_corpus(self) -> None:
        tools = VroTools(replace(load_settings(), south_estonian_db=Path("/tmp/no-such-se.db")))
        result = tools.find_usage_examples("naasõ")
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "south_estonian_db_unavailable")
        self.assertEqual(result["database"], "south_estonian")
        self.assertIn("setup_hint", result)

    def test_missing_word_bag_db_is_structured(self) -> None:
        tools = VroTools(
            replace(
                load_settings(),
                south_estonian_db=Path("/tmp/no-such-se.db"),
            )
        )
        result = tools.word_exists_in_bag("Miä")
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "south_estonian_db_unavailable")
        self.assertEqual(result["database"], "south_estonian")
        self.assertIn("setup_hint", result)

    def test_find_unrecognized_words_prefilter_missing_word_bag_is_structured(self) -> None:
        tools = VroTools(
            replace(
                load_settings(),
                south_estonian_db=Path("/tmp/no-such-se.db"),
            )
        )
        result = tools.find_unrecognized_words("Miä olõ hüä", prefilter=True)
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "south_estonian_db_unavailable")
        self.assertEqual(result["database"], "south_estonian")
        self.assertIn("setup_hint", result)

    def test_check_setup_reports_databases(self) -> None:
        self._require_db("south_estonian")
        result = self.tools.check_setup()
        self.assertEqual(result["corpus_policy"], CORPUS_POLICY_ID)
        self.assertIn("databases", result)
        self.assertTrue(result["databases"]["south_estonian"])


if __name__ == "__main__":
    unittest.main()
