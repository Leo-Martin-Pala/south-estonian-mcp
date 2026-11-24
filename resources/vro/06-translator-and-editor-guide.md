# Võro: Translator and Editor Guide

## Core Goal
Produce idiomatic, grammatically consistent Võro text (practical Võro Institute spelling unless older/dialectal register is explicitly requested) without Standard Estonian inflectional or lexical leakage.

## Mandatory Constraints
1. **Do NOT import Standard Estonian inflections:**
   - Reject `-nud` -> use `-nu(q)/-nü(q)`.
   - Reject `-tud/-dud` -> use `-t/-d` or `-tu(q)/-du(q)`.
   - Reject `ei + -nud/-tud` or `pole/polnud` -> use `es + verb` or postposed `-õs/-õi` (`olõ-õs`, `olõ-õi`).
   - Reject 3sg `-b` and 3pl `-vad` -> use endingless or `-s` 3sg, `-vaq/-sõq` 3pl.
   - Reject `-takse/-dakse`, `-ksin/-ksime`, `-sse/-desse/-tesse`, `-sid`, `-mas`, `-mata`, `-des/-tes`, translative `-ks` (use `-s`), nominative plural `-d` (use `-q`).
2. **Respect Vowel Harmony & Stem Morphology:** Keep `õ`/`ä`/`ö`/`ü` harmony (`midägi`, `eläseq`, `kõnõlõs`, `talolõ`) and valid `-o` stems (`talo`, `kodo`, `elo`).
3. **Never confuse present `-s` with Estonian past:** Translate `eläs`, `kirotas`, `ütles`, `mõtlõs` as **present tense** unless past context clearly dictates otherwise.
4. **Preserve postposed negation:** Never drop `-aiq`, `-õi`, `-õs`, `-as` on negated verbs (`võta-aiq`, `olõ-õs`).

## Recommended MCP Tool Workflow for Võro
1. **Orient & Plan:** Call `get_translation_guide("vro")`, `get_grammar_resource("vro", "verbs")`, and `get_grammar_resource("vro", "vocabulary")`.
2. **Drafting / MT Aid:**
   - Offline MT: `translate_mt(text, source_lang="et"|"en"|"vro", target_lang="vro"|"et"|"en")`.
   - Parallel & Corpus Precedents: `search_parallel_examples(query, lang="vro", mode="hybrid", origin_filter="human")` and `search_corpus(query, lang="vro", mode="hybrid")`.
3. **Lexical & Morphological Verification:**
   - `lookup_words(words, lang="vro")` / `search_dictionary_semantic(query, lang="vro")`.
   - Morphology: `analyze_word(words)` and `generate_forms(lemma, tags)` (GiellaLT FST for Võro!).
   - Usage attestation: `get_word_usage_examples(words, lang="vro")` or `word_exists_in_bag(words)`.
4. **Quality & Purity Gate (Mandatory before Final Output):**
   - Scan full draft: `check_purity_with_rules(text=draft, lang="vro")` (add `detail=True` or pass `words=[...]` for rule hints).
   - Optional GiellaLT checks: `spellcheck(draft, lang="vro")`, `grammar_check(draft, lang="vro")`, `find_unrecognized_words(draft, lang="vro")`.
   - Dialect sanity check: `classify_language(draft, source_lang_prior="vro")` to ensure text registers cleanly as `vro`, not `et`.
   - Word/char budget: `count_text(draft)`.
