from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import load_settings
from .tools import VroTools


settings = load_settings()
tools = VroTools(settings)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_resource(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _mcp_path_from_env() -> str:
    path = os.getenv("MCP_PATH", "/mcp").strip()
    if not path:
        return "/mcp"
    if not path.startswith("/"):
        path = f"/{path}"
    return path if path.endswith("/mcp") else f"{path.rstrip('/')}/mcp"


def create_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "Python package 'mcp' is required. Install this project with `pip install -e .`."
        ) from exc

    # stateless_http lets the server run on serverless platforms where each
    # request may land on a fresh container. MCP_PATH (e.g. "/<random>/mcp")
    # keeps the public URL unguessable when hosted; it defaults to "/mcp" for
    # local use and is ignored entirely by the default stdio transport.
    mcp = FastMCP(
        "vro-mcp-server",
        host="0.0.0.0",
        stateless_http=True,
        streamable_http_path=_mcp_path_from_env(),
    )

    @mcp.resource(
        "vro://grammar/noun-cases",
        name="Võro Noun Cases",
        description=(
            "Markdown reference for Võro noun/adjective/numeral/pronoun "
            "declension, case endings, number formation, and orthography notes."
        ),
        mime_type="text/markdown",
    )
    def noun_cases() -> str:
        return _read_resource("resources/noun-cases.md")

    @mcp.resource(
        "vro://grammar/verb-conjugation",
        name="Võro Verb Conjugation",
        description=(
            "Markdown reference for Võro verb conjugation, moods, tenses, "
            "person/number endings, voice, negation, and non-finite forms."
        ),
        mime_type="text/markdown",
    )
    def verb_conjugation() -> str:
        return _read_resource("resources/verb-conjugation.md")

    @mcp.resource(
        "vro://grammar/orthography-and-standard",
        name="Võro Orthography and Standard Language",
        description=(
            "Markdown reference for the Võro writing system (alphabet, glottal "
            "stop q, palatalization, high õ, length spelling, negation spelling) "
            "and Võro Institute standard-language orientation, with a "
            "distinctive-vocabulary list versus Estonian."
        ),
        mime_type="text/markdown",
    )
    def orthography_and_standard() -> str:
        return _read_resource("resources/orthography-and-standard.md")

    @mcp.resource(
        "vro://guide/translator-prompt",
        name="Võro Translator Prompt",
        description=(
            "Markdown translator/post-editor prompt and workflow for producing "
            "Võro text: constraints, quality goals, the reference resources, and "
            "a step-by-step workflow that uses these MCP tools."
        ),
        mime_type="text/markdown",
    )
    def translator_prompt() -> str:
        return _read_resource("resources/vro-translator-prompt.md")

    @mcp.tool()
    def lookup_word(
        words: str | list[str] | None = None,
        word: str | list[str] | None = None,
        direction: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Look up one or more words. Pass a single string, or a list of up to 15
        words to look up many in one call. Output is keyed by input word;
        each result is a compact concept object with language keys such as en,
        et, and vro. Direction accepts the standard values en-vro, et-vro,
        vro-en, and vro-et; directed results include a direction field and only
        that source/target language pair. Leave direction unset by default for
        broader coverage; use direction only when that pair is specifically
        needed.
        Exact normalized matches are preferred; if none exist, lookup also
        searches inside stored comma-separated terms such as "church, temple".
        Accepts either `words` or `word` (alias).
        """
        value = words if words is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `words` or `word`."}
        return tools.lookup_word(value, direction=direction, limit=limit)

    @mcp.tool()
    def find_usage_examples(
        words: str | list[str] | None = None,
        word: str | list[str] | None = None,
        source_type: str | None = None,
        limit: int = 3,
    ) -> dict[str, Any]:
        """
        Find real usage snippets from the local Võro corpus. Pass a single
        word/phrase, or a list of up to 15 words/phrases to search many terms at once.
        Output is keyed by input word/phrase and contains short text snippets only.
        Optional source_type filters: wiki_article for encyclopedia text,
        parallel_corpus_vro_side for translated/aligned text, and
        tei_literature for fiction/literature.
        Accepts either `words` or `word` (alias).
        """
        value = words if words is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `words` or `word`."}
        return tools.find_usage_examples(value, source_type=source_type, limit=limit)

    @mcp.tool()
    def word_exists_in_bag(
        words: str | list[str] | None = None,
        word: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Check whether word surface forms exist in the Võro word bag. Pass a
        single string, or a list of up to 100 words. Output is keyed by input
        word; the integer value is the stored count, with 0 meaning absent.
        Existence does not prove the form is standard or correct in context.
        Accepts either `words` or `word` (alias).
        """
        value = words if words is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `words` or `word`."}
        return tools.word_exists_in_bag(value)

    @mcp.tool()
    def count_text(text: str) -> dict[str, int]:
        """
        Count output length for drafting constraints. Returns only
        {"characters": int, "words": int, "estimated_sentences": int}.
        Characters include spaces and punctuation. Words include normal prose
        words and numbers, preserving Võro apostrophe and hyphenated forms as
        one word where possible. Sentence count is an estimate from terminal
        punctuation.
        """
        return tools.count_text(text)

    @mcp.tool()
    def find_unknown_words(text: str, limit: int = 50) -> dict[str, Any]:
        """
        Tokenize a larger Võro text/article and return unique word forms absent
        from the surface-form word bag. Use before or after translation to find
        forms that have not appeared in the current corpus/dictionary bag.
        Output is compact: unknown forms plus the number of checked tokens.
        """
        return tools.find_unknown_words(text, limit=limit)

    @mcp.tool()
    def find_unrecognized_words(
        text: str,
        prefilter: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Tokenize larger Võro text and return only unique word forms that the
        GiellaLT analyzer marks as unrecognized (+?). By default every unique
        token is analyzer-checked. Set prefilter=true to first skip forms already
        present in the word bag; this is faster for long text, but words in the
        bag are not analyzer-checked. Output contains only unrecognized forms,
        checked candidate count, and whether prefiltering was used.
        """
        return tools.find_unrecognized_words(text, prefilter=prefilter, limit=limit)

    @mcp.tool()
    def analyze_word(
        words: str | list[str] | None = None,
        word: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze one or more Võro words with GiellaLT. Pass a single string, or a
        list of up to 100 words analyzed in one pass; the response is keyed by
        input form. Each value is a compact list of analysis strings; an empty
        list means no recognized analysis. Treat output as guidance.
        Accepts either `words` or `word` (alias).

        Note: spellcheck_vro, grammar_check_vro, analyze_word, and suggest_correction
        use related but not identical Giella/Divvun checks. A word may be morphologically
        analyzable while still being flagged by the speller or grammar checker. Treat
        spell/grammar results as warnings, not final proof.
        """
        value = words if words is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `words` or `word`."}
        return tools.analyze_word(value)

    @mcp.tool()
    def lint_estonian_leakage(
        words: str | list[str] | None = None,
        word: str | list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        In-depth Standard Estonian leakage linter for discrete Võro words. Pass a
        single word/short phrase, or a list of up to 100 inputs; each input is
        checked as a whole unit with no tokenization (mirrors word_exists_in_bag
        and analyze_word). For a larger passage, scan it with find_estonian_leakage
        first, then pass the flagged words here. It flags Estonian-looking
        inflectional endings such as -nud, -tud/-dud, -b, -vad, -sse, and -sid,
        returning severities, messages, and hints. Findings mean "this ending
        looks Estonian-looking", not proof that the whole word is Estonian.
        Accepts either `words` or `word` (alias).
        """
        value = words if words is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `words` or `word`."}
        return tools.lint_estonian_leakage(value)

    @mcp.tool()
    def find_estonian_leakage(text: str, limit: int = 200) -> dict[str, Any]:
        """
        Tokenize a larger intended-Võro text and return a slim list of surface
        word forms whose ending looks like Standard Estonian (e.g. -nud, -tud/-dud,
        -b, -vad, -sse, -sid). Output is deduplicated and frequency-sorted, with no
        per-rule detail, so it stays small for long text. Pass any flagged word to
        lint_estonian_leakage for severities, messages, and hints.
        Flagged means "ending looks Estonian", not proof the word is wrong.
        """
        return tools.find_estonian_leakage(text, limit=limit)

    @mcp.tool()
    def suggest_correction(form: str) -> dict[str, Any]:
        """
        Suggest compact Võro corrections for one bad or unknown form. Returns
        {"form": ..., "valid": bool, "alternatives": [...]} with up to three
        analyzer-confirmed alternatives ranked best to worst. If valid is true,
        the form already analyzes cleanly and alternatives is empty.

        Note: spellcheck_vro, grammar_check_vro, analyze_word, and suggest_correction
        use related but not identical Giella/Divvun checks. A word may be morphologically
        analyzable while still being flagged by the speller or grammar checker. Treat
        spell/grammar results as warnings, not final proof.
        """
        return tools.suggest_correction(form)

    @mcp.tool()
    def generate_forms(
        lemma: str,
        tags: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate compact form list for one exact Giella analysis, e.g. lemma=uma
        and tags=A+Sg+Ill. Provide the complete tag string including the Part of
        Speech prefix, e.g. tags="N+Sg+Ine"; failed +? generator lines are omitted.
        This is not a full paradigm generator.
        """
        return tools.generate_forms(lemma, tags=tags)

    @mcp.tool()
    def spellcheck_vro(
        text: str | None = None,
        words: str | None = None,
        word: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Token-level Võro spellcheck with GiellaLT/Divvun. Checks each word form
        against the speller lexicon and returns {"unknown": [...], "returned": int,
        "total_unknown": int} with deduplicated unknown words and up to three
        ranked correction suggestions per word. Returns at most 10 unknown words
        by default; raise limit up to 50 when checking longer text. Compare
        returned vs total_unknown to see if more unknown words exist beyond the
        limit. It does not judge sentence grammar; suggestions may be incomplete
        or wrong. Accepts `text`, `words`, or `word` (aliases).

        Note: spellcheck_vro, grammar_check_vro, analyze_word, and suggest_correction
        use related but not identical Giella/Divvun checks. A word may be morphologically
        analyzable while still being flagged by the speller or grammar checker. Treat
        spell/grammar results as warnings, not final proof.
        """
        value = text if text is not None else (words if words is not None else word)
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `text`, `words`, or `word`."}
        return tools.spellcheck_vro(value, limit=limit)

    @mcp.tool()
    def grammar_check_vro(
        text: str | None = None,
        words: str | None = None,
        word: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Sentence-level Võro grammar check with GiellaLT/Divvun. Returns
        {"errors": [...], "returned": int, "total_errors": int} with structured
        error spans when the grammar checker detects issues, including some
        typos. Each error includes the word, span, compact code, and up to three
        suggestions. Returns at most 10 errors by default; raise limit up to 50
        when checking longer text. Compare returned vs total_errors to see if
        more errors exist beyond the limit. Use as a weak warning signal, not a
        final authority. Accepts `text`, `words`, or `word` (aliases).

        Note: spellcheck_vro, grammar_check_vro, analyze_word, and suggest_correction
        use related but not identical Giella/Divvun checks. A word may be morphologically
        analyzable while still being flagged by the speller or grammar checker. Treat
        spell/grammar results as warnings, not final proof.
        """
        value = text if text is not None else (words if words is not None else word)
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `text`, `words`, or `word`."}
        return tools.grammar_check_vro(value, limit=limit)

    @mcp.tool()
    def translate_vro(text: str, source_lang: str | None = None, target_lang: str | None = None) -> dict[str, Any]:
        """
        Translate text to or from Võro with Neurotõlge/TartuNLP. Use 3-letter
        API language codes. From Võro supports target_lang eng, est, fin, rus,
        hun, lav, nor. To Võro supports source_lang eng, est, fin, rus, lav,
        hun, nor. If both source_lang and target_lang are omitted, it defaults
        to translating from vro to est without giving an error. Successful
        output omits raw API payloads and source/target languages.
        """
        return tools.translate_vro(text, source_lang=source_lang, target_lang=target_lang)

    @mcp.tool()
    def check_setup() -> dict[str, Any]:
        """
        Report compact database and Giella availability. Healthy components are
        true; unavailable components include diagnostic details and setup hints.
        """
        return tools.check_setup()

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
