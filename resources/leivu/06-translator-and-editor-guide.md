# Leivu: Translator and Editor Guide

## Purpose & Evidentiary Stance
Leivu is a precious, severely endangered South Estonian language island documented mainly through historical fieldwork, scholarly articles (*JEFUL 2021*, *Balodis*), and EMS/VMS dictionary citations. **Preserve all primary transcriptions verbatim** — including segmentation hyphens (`vanu-n aju-n`, `nuorõ-b`, `magusa-mb`), broken-tone marks (`` ` ``), palatalization (`t́`, `d́`, `ń`), Latvian-contact particles (`un`), and apocopated endings.

## Critical Reading Rules
1. **Decode Morpheme-Segmented Forms & Vocalism:**
   - `-n` on `vanu-n aju-n` = inessive ("in old times"); `-st` on `piehmest` = translative ("soft"); `-mb` / `-b` on `magusa-mb` / `nuorõ-b` = comparative ("sweeter" / "younger").
   - Long broken/diphthongized vowels (`nuorõ`, `piehmest`, `laib`) reflect genuine Leivu historical phonology.
2. **Watch Latvian Contact Function Words & Sound Changes:** Recognize `un` ("and"), `d́-` for initial `j-` (`d́alan`), and `padi` ("thick/dense", not Estonian "pillow").
3. **Reject Modern Estonian Inflections in Leivu Authoring:** Flag `-nud`, `-tud/-dud`, `pole/polnud`, `-vad`, `-takse/-dakse`, `-ksin`, `-sse`, `-desse/-tesse`, and `-ks` translative.

## Recommended MCP Workflow for Leivu
1. Consult `get_grammar_resource("leivu", "nouns")` and `get_grammar_resource("leivu", "vocabulary")`.
2. Lookup lexical entries & Latvian/Estonian glosses: `lookup_words(words, lang="leivu")` (includes `eki_ems_dictionary`, `eki_vms_dictionary`, `leivu_eestijuured_vocabulary`, `dictionary_pairs`).
3. Use `find_cognates(word, lang="leivu")` and `search_dictionary_semantic(query, lang="leivu")` to bridge Leivu forms with Võro/Lutsi/Kraasna cognates.
4. Search all attested examples & translations: `search_parallel_examples(query, lang="leivu", mode="hybrid")` and `search_corpus(query, lang="leivu", mode="hybrid")`.
5. Validate purity with `check_purity_with_rules(text=draft, lang="leivu")` and `classify_language(draft, source_lang_prior="leivu")`.
