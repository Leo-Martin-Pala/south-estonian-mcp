# Lutsi: Translator and Editor Guide

## Role & Orthographic Fidelity
Lutsi is a historical heritage language island (`lutsi`) documented across both **practical revival/primer orthography** (*lutsi.org*, *Lutsi kielelementär*) and **academic UPA** (*Kallas 1894/1900*, *Mägiste*, *JEFUL 2021*). Keep primary evidence intact — never overwrite `y` (= *õ*), macrons, `țș`/`ļ`/`ņ`, `q`/`ˀ`, or Latgalian loanwords with Standard Estonian or Võro.

## Key Reading & Analysis Principles
1. **Practical vs UPA Equivalences:**
   - Practical `y` (`kyvaq`, `vyeras`, `vytnuq`) = UPA `e̮` (`he̮be͔hane͔`, `ve̮eras̀`) = Estonian/Võro `õ`.
   - Practical `-q` (`māq`, `ummaq`, `ole-eiq`, `vytnuq`) = UPA `-ˀ` (`māˀ`, `um̆maˀ`, `oлe͔i·ˀ`).
   - Palatal consonants written `ļ`, `ņ`, `ț`, `ș` in practical Lutsi correspond to UPA `l’`, `n’`, `t̅’s` (`лat̅’s`, `üt̅’s`, `ol̆’li`).
2. **Do Not Lose Postposed Negation (`ole-eiq` pres vs `ole-es` past) or 3sg `um` / 3pl `ummaq`.**
3. **Preserve Historical Estonian/English/Latvian Aligned Examples:** Many `source_parallel_pairs` in Lutsi carry English or Latvian reference glosses alongside Estonian.

## Recommended MCP Workflow for Lutsi
1. Always query `lookup_words(words, lang="lutsi")` — it searches `dict_entries` AND `dict_inflections` (`notation='practical'` AND `notation='upa'`) so inflected/UPA surface forms resolve straight to paradigm tables (`lutsi_org_paradigms`) and glosses.
2. Load `get_grammar_resource("lutsi", "verbs")` and `get_grammar_resource("lutsi", "nouns")` for exact `olema`, `minemä`, and `mā` paradigms.
3. Cross-reference related South Estonian forms via `find_cognates(word, lang="lutsi")` across Seto, Võro, Leivu, and Kraasna.
4. Search folklore/corpus parallels: `search_parallel_examples(query, lang="lutsi", mode="hybrid")` and `search_corpus(query, lang="lutsi", mode="hybrid")`.
5. Validate draft purity: `check_purity_with_rules(text=draft, lang="lutsi")` (which preserves both UPA/practical spellings and glottal markers while catching modern Estonian `-nud`, `-tud`, `-vad`, `pole`, `-sse`, `-ks`).
6. No offline MT exists for Lutsi (`translate_mt` supports only `vro`/`seto`); always synthesize translations with LLM reasoning anchored on attested `lutsi_org_paradigms` and `folklore_kallas_80` evidence.
