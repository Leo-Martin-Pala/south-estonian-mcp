# Mulgi: Translator and Editor Guide

## Core Goal
Interpret Mulgi faithfully across all five parishes (**Karksi, Halliste, Helme, Tarvastu, Paistu**) or generate pure Mulgi prose free of Standard Estonian intrusions (`-nud`, `-tud/-dud`, `-vad`, `-takse/-dakse`, `-ksin`, `-sse/-desse/-tesse`, `pole/polnud`) while **never** importing incompatible Võro rules (`-q` glottal stops or forced `-s` 3sg).

## Key Disambiguation Checks
1. **Resolve `-me` Infinitive vs 1pl Syntactically:** If a verb governing an infinitive precedes parallel `-me` verbs, interpret them as *ma*-infinitives (`-ma`), not 1pl *we*.
2. **Resolve Endingless Plurals (`latse`, `muna`, `sia`, `juhi`, `obese`):** Check verb context (`om`), demonstratives (`nii` = *need*), and predicates before assuming singular.
3. **Preserve `sii` = *see*, `nii` = *need*, `h`-drop (`obese`, `ain`), and `-te/-de` Abessive:** Never turn `-te/-de` absence forms into positive infinitives.
4. **Preserve `es` Past Negation:** Translate `es + verb` as past negative (Estonian *ei ...-nud*).
5. **Preserve Idioms (`mehele minema`):** Translate idiomatic relations naturally.

## Recommended MCP Workflow for Mulgi
1. Reference: call `get_translation_guide("mulgi")`, `get_grammar_resource("mulgi", "verbs")`, `get_grammar_resource("mulgi", "vocabulary")`.
2. Dictionary & Examples:
   - `lookup_words(words, lang="mulgi")` (covers `eki_mulgi_dictionary`, EMS, Smugri Mulgi dict, VMS).
   - `search_dictionary_semantic(query, lang="mulgi")` and `find_cognates(word, lang="mulgi")`.
   - `search_parallel_examples(query, lang="mulgi", mode="hybrid")` and `search_corpus(query, lang="mulgi", mode="hybrid")`.
3. Purity & Language ID Check:
   - Run `check_purity_with_rules(text=draft, lang="mulgi")` — note the Mulgi ruleset intentionally allows `-b/-p`, `-me`, `-n`, `-ge`, `-ss`, and `-te/-de` while flagging Estonian `-nud`, `-tud`, `-vad`, `-takse`, `-ksin`, `-sse`, `pole`.
   - Confirm variety classification: `classify_language(draft, source_lang_prior="mulgi")`.
4. **No Offline MT for Mulgi:** Bundled `SmugriMTRunner` only covers `vro`/`seto`; use corpus/dictionary lookups + LLM synthesis anchored on `eki_mulgi_dictionary` & `uitsainus_mulgimaa` examples!
