# Lutsi: Overview and Orthography

## Identity & Heritage Enclave
- **Language code:** `lutsi` (Lutsi; historic South Estonian language island around Ludza in Latgale, eastern Latvia).
- **Subgrouping:** Eastern-aligned South Estonian enclave with close historical ties to Võro/Seto while showing intensive Latvian (Latgalian) phonological and lexical contact alongside archaic morphological retentions.
- **MCP Support:** `eki_ems_dictionary` (~1.5k), `eki_vms_dictionary` (~1.2k), `lutsi_kielelementar` (~551 dictionary entries + ~407 texts), `lutsi_org_paradigms` (**both practical & UPA tables for 20 core noun/verb paradigms / 402 forms**), `folklore_kallas_80_lutsi_examples`, `jeful_2021_lutsi_examples`, Estonian/English/Latvian parallel pairs, offline language classifier (`lutsi`), and Lutsi leakage linter.

## Dual Notation Systems (Practical vs UPA!)
When querying `lookup_words` or `search_corpus` for `lang="lutsi"`, both **practical** orthography (`lutsi.org` / *Lutsi kielelementär*) and **academic UPA** (Uralic Phonetic Alphabet) forms appear:
1. **Practical Notation (`lutsi.org`):**
   - **`y`** represents high unrounded **`õ`** (`vyeras` = võõras, `kyvaq` = kõvad, `hybehane` = hõbehane, `vytnuq` = võtnud)! **Crucial:** do NOT mistake `y` for IPA/Finnish `[y]` (= `ü`); Lutsi uses `ü` separately (`üțș`).
   - **Macrons (`ā`, `ē`, `ō`, `ū`, `ǟ`)** mark long vowels (`mā`, `nān̄e`, `nār`, `lǟm`).
   - **Cedilla / palatalized diacritics (`ț`, `ș`, `ņ`, `ļ`, `ŗ`)**: borrowed cleanly from Latvian orthography conventions to mark palatalization/affricates (`üțș` = üks, `lațș` = laps, `oțșma` = otsima, `nāņe` = naine, `taļvine` = talvine, `oļ` = oli)!
   - **Glottal stop:** Written **`q`** practically (`māq`, `kyvaq`, `hobezaq`, `ole-eiq`, `vytnuq`, `mahaq`), matching **`ˀ`** in UPA (`māˀ`, `um̆maˀ`, `ol̆’liˀ`).
2. **Academic UPA (`notation='upa'` in `dict_inflections`):** Uses Cyrillic/UPA lateral `л` (`лumì`, `mâлe͔`), inverted breve/caret/macron length marks, half-long/reduced vowel subscripts (`e͔`), and `ˀ` (`mâ`, `māˀ`, `oлe͔`, `um̆maˀ`). Lookup automatically indexes **both** `practical` and `upa` inflections!
