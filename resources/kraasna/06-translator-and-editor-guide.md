# Kraasna: Translator and Editor Guide

## Purpose & Evidentiary Stance
Kraasna is a documented eastern South Estonian language island (historically around Krasnogorodskoye south of Pskov) with limited attested texts preserved in historical fieldwork (Oskar Kallas 1903), *JEFUL 2021*, and EMS/VMS dialect archives. **Do not invent or modernize unattested forms silently.** Quote primary transcriptions faithfully, clearly distinguishing attested Kraasna material from reconstructed eastern South Estonian (Seto/Võro) parallels.

## Critical Editing & Reading Checklist
1. **Preserve Historical Notation:** Keep palatalization (`l´`, `t´`, `ź`, `ń`, `ḱ`), glottal `-q`, and vowel spellings (`Riiiga viiia`, `tuuua`, `üźäh`, `tˊśalgovikka`) intact when citing attested sources.
2. **Respect Eastern South Estonian Case & Verb Morphology:**
   - Inessive **`-h`** (`üźäh`), translative **`-s`** (`vitsavõttijas`), `es` past negation, `om`/`ol´`, `-nu/-nü` active participle, and `-si/-ssi` conditional.
   - Flag modern Standard Estonian imports (`-nud`, `-tud/-dud`, `pole/polnud`, `-vad`, `-takse/-dakse`, `-ksin`, `-sse`, `-desse/-tesse`, `-sid`, `-mas`, and unmarked `-b` where Kraasna uses endingless/`-s`).
3. **Verify Every Gloss via Cognates & Dictionary:**
   - Because Kraasna dictionary entries in VMS/EMS often carry Estonian archival glosses and phonetic transcriptions, cross-check forms with `seto` and `vro` cognates.

## Recommended MCP Workflow for Kraasna
1. Read `get_grammar_resource("kraasna", "overview")` and `get_grammar_resource("kraasna", "sources")`.
2. Lookup attested dictionary entries: `lookup_words(words, lang="kraasna")`.
3. Bridge sparse coverage via eastern South Estonian relatives: `find_cognates(word, lang="kraasna")` and `search_dictionary_semantic(query, lang="kraasna")`.
4. Search all attested parallel and corpus examples: `search_parallel_examples(query, lang="kraasna", mode="hybrid")` and `search_corpus(query, lang="kraasna", mode="hybrid")`.
5. Validate proposed Kraasna forms with `check_purity_with_rules(text=draft, lang="kraasna")` and `classify_language(draft, source_lang_prior="kraasna")`.
