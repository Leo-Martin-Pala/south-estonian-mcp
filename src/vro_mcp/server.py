from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from .config import load_settings
from .tools import VroTools


settings = load_settings()
tools = VroTools(settings)
REPO_ROOT = Path(__file__).resolve().parents[2]

SouthEstonianLang = Literal["vro", "seto", "mulgi", "tartu", "leivu", "lutsi", "kraasna"]
GiellaLang = Literal["vro", "mulgi", "seto"]
TargetLang = Literal["et", "en", "lv"]
SearchMode = Literal["fts", "vector", "hybrid"]
LintCheck = Literal["purity", "unknown", "spell", "grammar", "analyzer"]
GrammarTopic = Literal[
    "overview",
    "nouns",
    "verbs",
    "vocabulary",
    "sources",
    "guide",
    "pronouns",
    "comparison",
    "numerals",
    "inflection-tables",
    "paradigms",
]
MTBackend = Literal["auto", "api", "local"]
ClassifierMode = Literal["auto", "standalone", "context"]


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
        from mcp.types import ToolAnnotations

        readonly_local: Any = ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
        readonly_network: Any = ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    except ImportError:
        readonly_local = None
        readonly_network = None

    try:
        from mcp.server.fastmcp import FastMCP

        # stateless_http lets the server run on serverless platforms where each
        # request may land on a fresh container. MCP_PATH (e.g. "/<random>/mcp")
        # keeps the public URL unguessable when hosted; it defaults to "/mcp" for
        # local use and is ignored entirely by the default stdio transport.
        mcp: Any = FastMCP(
            "south-estonian-mcp",
            host="0.0.0.0",
            stateless_http=True,
            streamable_http_path=_mcp_path_from_env(),
        )
    except ImportError:
        try:
            from mcp.server.mcpserver import MCPServer
        except ImportError as exc:
            raise RuntimeError(
                "Python package 'mcp' is required. Install this project with `pip install -e .`."
            ) from exc

        class _CompatMCPServer(MCPServer):
            def streamable_http_app(self, **kwargs: Any) -> Any:
                kwargs.setdefault("host", "0.0.0.0")
                kwargs.setdefault("stateless_http", True)
                kwargs.setdefault("streamable_http_path", _mcp_path_from_env())
                return super().streamable_http_app(**kwargs)

        mcp = _CompatMCPServer("south-estonian-mcp")

    def _tool(*, network: bool = False) -> Any:
        ann = readonly_network if network else readonly_local
        return mcp.tool(annotations=ann) if ann is not None else mcp.tool()

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

    @mcp.resource(
        "southestonian://language/{lang}/{topic}",
        name="South Estonian Language Guides",
        description=(
            "Standardized Markdown grammar, inflection, and translator guides for "
            "South Estonian languages (vro, seto, mulgi, tartu, leivu, lutsi, kraasna). "
            "Topics: overview, nouns, verbs, vocabulary, sources, guide, pronouns, "
            "comparison, numerals, inflection-tables, paradigms."
        ),
        mime_type="text/markdown",
    )
    def south_estonian_resource(lang: str, topic: str) -> str:
        res = tools.get_grammar_resource(lang=lang, topic=topic)
        if "content" not in res:
            raise ValueError(res.get("detail") or res.get("error") or "Resource not found.")
        return res["content"]

    @_tool()
    def lookup_words(
        words: str | list[str],
        lang: SouthEstonianLang | None = None,
        target_lang: TargetLang | None = None,
        include_inflections: bool = True,
        include_examples: bool = True,
        include_raw: bool = False,
        include_paradigm: bool = False,
        limit: int | None = None,
        source_slug: str | None = None,
    ) -> dict[str, Any]:
        """
        Look up one or up to 15 words/forms/glosses across the unified South
        Estonian dictionary (vro, seto, mulgi, tartu, leivu, lutsi, kraasna).
        `limit` applies per searched word: defaults to 10 for a single word
        (max 50) and 3 per word when batching (max 10 per word). Set
        `include_inflections=False` and/or `include_examples=False` for lower
        context usage when batching. Matches exact headwords, inflected forms
        (including Lutsi UPA & practical paradigms), reverse `et`/`en`/`lv`
        definitions, and FTS5 fallback. Use `lang` to filter entries and
        `target_lang` to filter definitions.
        Võro Wikipedia entries (`fiu_vrowiki_dictionary`) include the article
        revision in `source_url`, linked Estonian and/or English glosses, and
        the first Võro sentence in `notes` when available. Set `source_slug` to search
        within a specific dictionary source.
        Set `include_paradigm=True` to include model forms for an entry's
        recorded inflection type when a matching reference exists. Model forms
        are omitted by default. Set `include_raw=True`
        to inspect original unparsed dictionary strings (`raw_entry` and
        `raw_inflections`) when parsed fields look suspicious.
        """
        return tools.lookup_words(
            words,
            lang=lang,
            target_lang=target_lang,
            include_inflections=include_inflections,
            include_examples=include_examples,
            include_raw=include_raw,
            include_paradigm=include_paradigm,
            limit=limit,
            source_slug=source_slug,
        )

    @_tool()
    def search_dictionary_semantic(
        query: str,
        lang: SouthEstonianLang | None = None,
        target_lang: TargetLang | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Hybrid semantic (offline Voyage-4-Nano + libSQL DiskANN) and FTS5
        search across South Estonian dictionary definitions. Best for concept
        or meaning queries in Estonian, English, or South Estonian.
        """
        return tools.search_dictionary_semantic(
            query,
            lang=lang,
            target_lang=target_lang,
            limit=limit,
        )

    @_tool()
    def find_cognates(
        word: str | None = None,
        lang: SouthEstonianLang | None = None,
        concept: str | None = None,
        limit: int = 15,
    ) -> dict[str, Any]:
        """
        Find cross-dialect equivalents across Võro, Seto, Mulgi, Tartu, Leivu,
        Lutsi, and Kraasna sharing an Estonian or English concept gloss. Splits
        results into `cognates` (shared-stem cognates accounting for common
        South Estonian sound correspondences) and `semantic_equivalents`, with
        `entry_id` and `source_slug` on each item. Pass a dialect `word` (with
        optional `lang`) and/or a direct `concept`.
        """
        return tools.find_cognates(word=word, lang=lang, concept=concept, limit=limit)

    @_tool()
    def get_word_usage_examples(
        words: str | list[str],
        lang: SouthEstonianLang | None = None,
        limit: int = 5,
        max_snippet_chars: int | None = None,
        expand_inflections: bool = False,
    ) -> dict[str, Any]:
        """
        Look up attested corpus word frequencies and usage examples for one or
        up to 15 words across any South Estonian language (omit `lang` for all 7).
        Set `expand_inflections=True` to also search recorded dictionary
        inflections of a headword. Examples identify the `matched_form`;
        frequencies describe the input form.
        Set `max_snippet_chars` (80..1000) to keep snippets compact when batching.
        Attaches LID warnings only when classifier disagreement is >= 70%.
        """
        return tools.get_word_usage_examples(
            words,
            lang=lang,
            limit=limit,
            max_snippet_chars=max_snippet_chars,
            expand_inflections=expand_inflections,
        )

    @_tool()
    def search_corpus(
        query: str,
        lang: SouthEstonianLang | None = None,
        mode: SearchMode = "hybrid",
        source_slug: str | None = None,
        unit_level: str | None = None,
        include_context: bool = False,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Search monolingual South Estonian corpus units across all 7 languages.
        `mode`: 'fts' (BM25), 'vector' (offline Voyage-4-Nano + DiskANN), or
        'hybrid' (RRF fusion, default). Set `include_context=True` to fetch
        adjacent +-1 units from the same document; LID warnings appear only on
        strong disagreement (>= 70%).
        """
        return tools.search_corpus(
            query,
            lang=lang,
            mode=mode,
            source_slug=source_slug,
            unit_level=unit_level,
            include_context=include_context,
            limit=limit,
        )

    @_tool()
    def search_parallel_examples(
        query: str,
        lang: SouthEstonianLang | None = None,
        target_lang: Literal["et", "en", "de", "lv"] | None = None,
        mode: SearchMode = "hybrid",
        origin_filter: str | None = None,
        include_context: bool = False,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Search aligned examples and contextual dictionary pairs across source and
        target text. Common target languages include Estonian, English, German
        and Latvian. `origin_filter`
        accepts 'human', 'llm', 'mt' (or comma-separated). Omits raw quality
        scores when clean and surfaces warnings only when thresholds are crossed.
        """
        return tools.search_parallel_examples(
            query,
            lang=lang,
            target_lang=target_lang,
            mode=mode,
            origin_filter=origin_filter,
            include_context=include_context,
            limit=limit,
        )

    @_tool()
    def word_exists_in_bag(
        words: str | list[str] | None = None,
        lang: SouthEstonianLang | None = None,
        include_languages: bool = False,
        word: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Fast, low-context check of whether up to 100 word surface forms exist
        in `word_frequencies`. Returns `{word: count}` by default (0 = absent),
        or `{word: {"total_count": int, "languages": [...]}}` when
        `include_languages=True`. Existence does not prove standardness.
        """
        value = words if words is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `words` or `word`."}
        return tools.word_exists_in_bag(value, lang=lang, include_languages=include_languages)

    @_tool()
    def count_text(text: str) -> dict[str, int]:
        """
        Count output length for drafting constraints. Returns
        `{"characters": int, "words": int, "estimated_sentences": int}`.
        """
        return tools.count_text(text)

    @_tool()
    def lint_text(
        text: str,
        lang: SouthEstonianLang = "vro",
        checks: list[LintCheck] | None = None,
        detail: bool = False,
        limit: int = 25,
    ) -> dict[str, Any]:
        """
        Unified draft-checking tool designed for low-context text review. Runs
        multiple checks in one call: `purity` (Estonian leakage rules),
        `unknown` (absent from word bag), and GiellaLT checks where available
        (`spell`, `grammar`, `analyzer` for `vro`, `mulgi`, and `seto`).
        Defaults to `["purity", "unknown", "spell", "grammar"]` for those three
        varieties and `["purity", "unknown"]` for other varieties. Unsupported
        checks are skipped with an explanation. With `detail=False` (default), returns compact deduplicated
        word lists for large texts; set `detail=True` to include rule hints and
        full spell/grammar suggestions. Use surgical tools (`analyze_word`,
        `suggest_correction`, `lookup_words`) to inspect flagged items.
        """
        return tools.lint_text(
            text,
            lang=lang,
            checks=list(checks) if checks is not None else None,
            detail=detail,
            limit=limit,
        )

    @_tool()
    def find_unknown_words(
        text: str,
        lang: SouthEstonianLang | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Low-context scan of a South Estonian text returning unique word forms
        absent from `word_frequencies` (optionally restricted to `lang`), plus
        checked token count.
        """
        return tools.find_unknown_words(text, lang=lang, limit=limit)

    @_tool()
    def find_unrecognized_words(
        text: str,
        lang: GiellaLang = "vro",
        prefilter: bool = False,
        limit: int = 50,
        prefilter_lang: SouthEstonianLang | None = None,
    ) -> dict[str, Any]:
        """
        Low-context scan of Võro, Mulgi, or Seto text returning unique word
        forms that the GiellaLT analyzer for `lang` marks as unrecognized (+?).
        Set `prefilter=True` to first skip forms present in `word_frequencies`
        (defaults to `lang`, or override via `prefilter_lang`).
        """
        return tools.find_unrecognized_words(
            text,
            lang=lang,
            prefilter=prefilter,
            limit=limit,
            prefilter_lang=prefilter_lang,
        )

    @_tool()
    def analyze_word(
        words: str | list[str] | None = None,
        lang: GiellaLang = "vro",
        word: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Surgical morphological analysis via GiellaLT (`vro`, `mulgi`, or `seto`)
        for one or up to 100 words in one pass. Returns `{word: [analysis_strings]}`
        (empty list = unrecognized). Treat output as guidance.
        """
        value = words if words is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `words` or `word`."}
        return tools.analyze_word(value, lang=lang)

    @_tool()
    def suggest_correction(
        form: str | None = None, lang: GiellaLang = "vro", word: str | None = None,
    ) -> dict[str, Any]:
        """
        Surgical correction helper for one bad/unknown form (`vro`, `mulgi`, or
        `seto`). Combines the GiellaLT speller (when available for `lang`),
        dictionary entries, and analyzer verification to return
        `{"form": ..., "lang": ..., "valid": bool, "alternatives": [...]}` (up
        to 3 ranked alternatives), plus `seen_in_word_bag` for invalid forms.
        """
        value = form if form is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `form` or `word`."}
        return tools.suggest_correction(value, lang=lang)

    @_tool()
    def generate_forms(
        lemma: str,
        tags: str | None = None,
        lang: GiellaLang = "vro",
    ) -> dict[str, Any]:
        """
        Generate inflected form(s) for one exact GiellaLT analysis (`vro`,
        `mulgi`, or `seto`), e.g. `lemma="uma"`, `tags="A+Sg+Ill"` or
        `tags="N+Sg+Ine"` (include POS prefix). Use `generate_paradigm` for a
        full declension/conjugation table without specifying GiellaLT tags.
        """
        return tools.generate_forms(lemma, tags=tags, lang=lang)

    @_tool()
    def generate_paradigm(
        lemma: str,
        pos: Literal["N", "A", "V"] | None = None,
        lang: GiellaLang = "vro",
    ) -> dict[str, Any]:
        """
        Generate a full declension or conjugation table for a word in Võro
        (`vro`), Mulgi (`mulgi`), or Seto (`seto`) in a single GiellaLT pass
        without needing to know GiellaLT tag syntax. If `pos` (`N`, `A`, or `V`)
        is omitted, it is auto-detected via the analyzer. Returns singular/plural
        cases for nouns/adjectives or present/past/conditional/imperative/non-finite
        forms for verbs.
        """
        return tools.generate_paradigm(lemma, pos=pos, lang=lang)

    @_tool()
    def spellcheck(
        text: str,
        lang: GiellaLang = "vro",
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Token-level spellcheck via GiellaLT/Divvun (`vro`, `mulgi`, or `seto`).
        Returns deduplicated unknown words with up to 3 ranked suggestions each
        (default limit 10, max 50). Treat results as warnings, not final proof.
        """
        return tools.spellcheck(text, lang=lang, limit=limit)

    @_tool()
    def grammar_check(
        text: str,
        lang: GiellaLang = "vro",
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Sentence-level grammar warnings for `vro`, `mulgi`, and `seto`.
        Võro uses Divvun. Seto and Mulgi use an experimental present-tense
        copula agreement rule backed by their own GiellaLT analysers.
        Returns `word`, `span`, `code`, and up to 3 suggestions per finding
        (default limit 10, max 50).
        """
        return tools.grammar_check(text, lang=lang, limit=limit)

    @_tool()
    def classify_language(
        text: str,
        context_before: str | None = None,
        context_after: str | None = None,
        source_lang_prior: str | None = None,
        mode: ClassifierMode = "auto",
        document_mode: bool = False,
        top_k: int = 4,
    ) -> dict[str, Any]:
        """
        Offline South Estonian & Estonian language identifier (`vro`, `seto`,
        `mulgi`, `tartu`, `leivu`, `lutsi`, `kraasna`, `et`). Uses standalone
        ensemble by default, or contextual XLM-R + prior ensemble when
        `context_before`/`context_after`/`source_lang_prior` is provided
        (set `document_mode=True` for multi-sentence passages).
        """
        return tools.classify_language(
            text,
            context_before=context_before,
            context_after=context_after,
            source_lang_prior=source_lang_prior,
            mode=mode,
            document_mode=document_mode,
            top_k=top_k,
        )

    @_tool()
    def check_purity_with_rules(
        words: str | list[str] | None = None,
        text: str | None = None,
        lang: SouthEstonianLang = "vro",
        mode: Literal["auto", "text", "words"] = "auto",
        detail: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Rule-based Standard Estonian leakage and purity check tailored per
        South Estonian variety. Pass `text` for a low-context scan (`detail=False`
        returns only flagged words; `detail=True` adds rule hints), or discrete
        `words` (up to 100) for surgical per-word explanations.
        """
        return tools.check_purity_with_rules(
            words=words,
            text=text,
            lang=lang,
            mode=mode,
            detail=detail,
            limit=limit,
        )

    @_tool(network=True)
    def translate_mt(
        text: str,
        source_lang: str = "vro",
        target_lang: str = "et",
        backend: MTBackend = "auto",
    ) -> dict[str, Any]:
        """
        Machine translation for Võro and Seto. Supports bidirectional
        `vro` <-> `et`/`en`/`fi`/`ru`/`hu`/`lv`/`no` and `seto` -> those
        targets (via `vro` transfer; translating INTO `seto` is disallowed).
        `backend="auto"` uses TartuNLP/Neurotõlge API for `vro` with automatic
        fallback to offline Smugri NMT (`mt_smugri_fp16`), or offline directly
        for `seto` source.
        """
        return tools.translate_mt(
            text,
            source_lang=source_lang,
            target_lang=target_lang,
            backend=backend,
        )

    @_tool()
    def get_grammar_resource(
        lang: SouthEstonianLang = "vro",
        topic: GrammarTopic = "overview",
    ) -> dict[str, Any]:
        """
        Retrieve standardized Markdown grammar, inflection, and translator
        reference guides for any South Estonian language. Use `topic="guide"`
        for the translator/post-editor guide.
        """
        return tools.get_grammar_resource(lang=lang, topic=topic)

    @_tool()
    def get_language_stats(lang: SouthEstonianLang | None = None) -> dict[str, Any]:
        """
        Report corpus unit, translation, dictionary entry, inflection, word
        frequency, and vector counts in `south_estonian.db` (overall or per
        language).
        """
        return tools.get_language_stats(lang=lang)

    @_tool()
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
        return tools.lookup_legacy_word(value, direction=direction, limit=limit)

    @_tool()
    def find_usage_examples(
        words: str | list[str] | None = None,
        word: str | list[str] | None = None,
        source_type: str | None = None,
        limit: int = 3,
        max_snippet_chars: int | None = None,
    ) -> dict[str, Any]:
        """
        Find real usage snippets from the local Võro corpus. Pass a single
        word/phrase, or a list of up to 15 words/phrases to search many terms at once.
        Output is keyed by input word/phrase and contains short text snippets with source attribution.
        Optional source_type filters: wiki_article for encyclopedia text,
        parallel_corpus_vro_side for translated/aligned text, and
        tei_literature for fiction/literature.
        Set max_snippet_chars to choose the maximum returned snippet length
        (bounded to 80..1000 characters).
        Accepts either `words` or `word` (alias).
        """
        value = words if words is not None else word
        if value is None:
            return {"error": "missing_parameter", "detail": "Provide `words` or `word`."}
        return tools.find_usage_examples(
            value,
            source_type=source_type,
            limit=limit,
            max_snippet_chars=max_snippet_chars,
        )

    @_tool()
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

    @_tool()
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

    @_tool()
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
        return tools.spellcheck(value, limit=limit)

    @_tool()
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
        return tools.grammar_check(value, limit=limit)

    @_tool(network=True)
    def translate_vro(text: str, source_lang: str | None = None, target_lang: str | None = None) -> dict[str, Any]:
        """
        Translate text to or from Võro with Neurotõlge/TartuNLP. Canonical
        language codes are the 3-letter API codes: from Võro supports target_lang
        eng, est, fin, rus, hun, lav, nor; to Võro supports source_lang eng, est,
        fin, rus, lav, hun, nor. Common 2-letter aliases are also accepted:
        en->eng, et->est, fi->fin, ru->rus, hu->hun, lv->lav, no/nb->nor.
        If both source_lang and target_lang are omitted, it defaults to
        translating from vro to est without giving an error. Successful output
        omits raw API payloads and source/target languages.
        """
        return tools.neurotolge.translate(text, source_lang=source_lang, target_lang=target_lang)


    @_tool()
    def check_setup() -> dict[str, Any]:
        """
        Report compact database, Giella, offline ML model, resource, and rules
        availability. Healthy components return `true`; unavailable components
        include diagnostic details and setup hints.
        """
        return tools.check_setup()

    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
