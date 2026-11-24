# Tartu: Translator and Editor Guide

## Core Goal
Interpret authentic spoken and dictionary Tartu dialect (`murdekorpus_tartu`, `eki_kiiker_tartu`, EMS/VMS) or draft faithful Tartu text without forcing Võro `-q` endings on Tartu or letting Standard Estonian inflections (`-nud`, `-tud/-dud`, `-vad`, `-takse/-dakse`, `-ksin`, `-sse`, `pole/polnud`) leak in.

## Critical Editing Rules
1. **Normalize Transcription Noise Carefully When Reading:** When translating spoken `murdekorpus_tartu` passages into Estonian/English, mentally strip quantity backticks (`` ` ``), prosodic ties (`‿`), and phonetic `ʔ` only to understand the underlying words — never corrupt archived primary citations.
2. **Respect Tartu Inflectional Patterns:**
   - Plural verbs take `-va`/`-vä` (`teevä`), `-iva` (`olliva`, `tulliva`), `-nüvä` (`lännüvä`) — without `-vad` or Võro `-q`.
   - Inessive is `-n` (`lehmäkarjan`); translative `-st`/`-ss`/`-s`; *da*-infinitives omit `-q` (`süvvä`, `lüvvä`).
   - Past negation uses `es`.
3. **Preserve Signature Phonology & Pronouns:** `üits`, `kaits`, `nuu`, `näile`, `säidse`, `manu`, `kaema`.

## Recommended MCP Workflow for Tartu
1. Read `get_translation_guide("tartu")`, `get_grammar_resource("tartu", "nouns")`, and `get_grammar_resource("tartu", "verbs")`.
2. Lookup lexical items & regional senses: `lookup_words(words, lang="tartu")` (searches 11k+ EMS/VMS Tartu entries) and `find_cognates(word, lang="tartu")` to compare across Mulgi/Võro/Seto.
3. Retrieve authentic dialect spoken usage & parallel examples: `search_parallel_examples(query, lang="tartu", mode="hybrid")` and `search_corpus(query, lang="tartu", mode="hybrid")`.
4. Purity & Classification Gate: `check_purity_with_rules(text=draft, lang="tartu")` and `classify_language(draft, source_lang_prior="tartu")`. (Offline `translate_mt` does not target `tartu`; rely on retrieved examples + LLM drafting.)
