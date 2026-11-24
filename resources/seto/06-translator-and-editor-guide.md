# Seto: Translator and Editor Guide

## Role & Directionality Constraints
1. **Seto -> Estonian / English (Reading, Translation, Post-Editing):**
   - Fully supported locally via `translate_mt(text, source_lang="seto", target_lang="et"|"en")`, which transfers through the closely related Smugri `vro` model, paired with Seto-specific dictionaries (`lookup_words(..., lang="seto")`) and human/LLM Seto parallel examples (`search_parallel_examples(..., lang="seto")`).
   - **Rule:** *Interpret Seto source forms cleanly — NEVER rewrite the Seto source into Standard Estonian or Võro!*
2. **Estonian / English -> Seto (Generation):**
   - **Offline `translate_mt` intentionally REJECTS `et`/`en -> seto`** so the Võro neural generator cannot silently overwrite Seto identity (`-h` inessive, `-st` translative, `’` apostrophes, Seto vocabulary) with Võro forms!
   - When drafting/adapting into Seto as an LLM, anchor every construction using `lookup_words(..., lang="seto")`, `search_corpus(..., lang="seto")`, `02-noun-morphology`, and `03-verb-conjugation`, then validate with `check_purity_with_rules(..., lang="seto")` and `classify_language(..., source_lang_prior="seto")`.

## Checklist for Seto Comprehension & Post-Editing
- Preserve apostrophes (`’` / `'`) marking glottal stops and palatalization, plus quantity dots (`·`).
- Distinguish `-s` present (`eläs`, `küdsäs`, `ilotõlõs`) from past (`ol'`, `käve`, `anni'`, `tõi'`).
- Catch preverbal (`ei`/`õi` vs `es`/`õs`) AND postposed negation (`olõ-õi` vs `olõ-õs`).
- Distinguish Seto `-h` inessive (`kerkoh`, `tulõmah`), `-st` elative/translative, and `-lda'` abessive (`tulõmalda'`).
- Preserve reportative `-v`/`-vat` (`olevat`) rather than converting reported claims into witnessed facts.

## Recommended MCP Workflow for Seto
1. Load `get_grammar_resource("seto", "verbs")` and `get_translation_guide("seto")`.
2. Search verified precedents: `search_parallel_examples(query, lang="seto", mode="hybrid")` and `search_corpus(query, lang="seto", mode="hybrid")`.
3. Resolve rare Seto lexicon: `lookup_words(words, lang="seto")` + `find_cognates(word, lang="seto")`.
4. Draft MT baseline (when translating *from* Seto): `translate_mt(text, source_lang="seto", target_lang="et")`, then verify all negation, tense, `-h`/`-st` case roles, and reportative markers against Seto grammar!
5. When authoring Seto output: run `check_purity_with_rules(text=draft, lang="seto")` and `classify_language(draft, source_lang_prior="seto")`.
