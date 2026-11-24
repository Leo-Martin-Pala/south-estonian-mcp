# Seto: Distinctive Vocabulary and False Friends

## Core Seto Lexical & Idiomatic Items (vs Estonian & Neighboring Dialects)
| Seto Word / Form | Meaning (ET / EN) | Contrast / Guardrail |
| --- | --- | --- |
| `s´oo` / `sjoo` / `s´ooaastaganõ` | *see* / *tänavune* | Characteristic palatalized `s´`; contrast Mulgi `sii`, Võro `seo` |
| `om` / `omma'` / `ommava'` | *on* / is, are | 3pl `ommava'` especially common in Seto |
| `olõ-õi` / `olõ-i` | *ei ole* / is not (pres.) | Postposed negation clitic — never read as affirmative! |
| `olõ-õs` / `olõ-s` | *ei olnud* / was not (past) | Past postposed negation clitic |
| `sõir` (gen. `sõira`) | Traditional Seto curd cheese | Cultural signature term (`sõirameistri'`) |
| `hanśa` / `hans´a` | Traditional Seto rye distillate | Cultural lexicon (`hans´ameistri'`) |
| `taar` (gen. `taari`) | Traditional fermented drink | Not Estonian *taar* in narrow modern sense only |
| `kerko` (`kerkoh`) | *kirik* (*kirikus*) | Preserves `-o` stem and `-h` inessive |
| `moro` (`moropääle`) | *õu, muru* / yard, lawn | "On the yard" (`moropääle`) |
| `munaloomka` | Easter egg-rolling slope | Traditional Seto Easter game (*Setomaa* corpus) |
| `ülekaehus` | *ülevaade* / overview, survey | Formed from `kaema` ("look") |
| `õkvalt` | *kohe, otse, just* / right, directly | High-frequency Seto adverb |
| `mille` | *miks* / why | Compare Est. `miks`, Mulgi `misperäst` |
| `pini` | *koer* / dog | Shared South Estonian core noun |
| `kõnõlõma` / `pajatama` | *rääkima, kõnelema* | Traditional speech verbs |
| `küdsämä` / `küdsäs` | *küpsetama* vs *küpseb* | Transitive vs intransitive pair in `-s` |

## Cross-Dialect Boundary Rules
- **Do NOT import Mulgi `-me` infinitives into Seto** (`tulõmah` / `tulõma` != Mulgi *tuleme*).
- **Do NOT erase Seto `-h` inessive or `-st` translative to make Seto look like Võro.** Both Võro (`vro`) and Seto (`seto`) coexist in this MCP server, and context-aware classification uses `source_lang_prior="seto"` when processing Seto publications.
- **Check Cognates & Seto Dictionaries:** Always check `lookup_words(word, lang="seto")` (which queries 49k+ `smugri4_seto_dictionary` / `eki_seto_dictionary` / EMS / VMS entries) before borrowing Estonian or Võro lexical substitutes.
