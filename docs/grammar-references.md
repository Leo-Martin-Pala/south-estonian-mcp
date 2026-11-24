# Authoritative Grammar References for South Estonian Varieties

This document catalogs the authoritative linguistic sources, online archives, and local corpus files used to compile the MCP grammar resources under `resources/<lang>/`. Bibliographic metadata is kept here (and in PostgreSQL `unified_dictionary.grammar_resources.source_url`) rather than inside the MCP tool output so LLM contexts stay focused on pure grammar.

## 1. Võro (`resources/vro/`)
- **Võro–Estonian–Võro Dictionary (`synaq.org`) Inflection & Paradigm Tables** (Võro Institute):
  - Paradigm tables 1–90 (53 nominal, 37 verbal): `https://synaq.org/index.php?vaade=tyybiq`
  - Case & verb inflection tables (`NIMISÕNA MOODUQ`, `TEGOSÕNA MOODUQ`, pronouns, comparison, numerals): `https://synaq.org/index.php?vaade=kaan&p=kaan-nim`
  - Used for: `07-pronouns.md`, `08-comparison.md`, `09-numerals.md`, `10-inflection-tables.md`, `11-paradigms.md`.
- **Sulev Iva (2007):** *Võru kirjakeele sõnamuutmissüsteem* (PhD dissertation, University of Tartu).
  - Open-access PDF: `https://dspace.ut.ee/handle/10062/4860`
  - Local archive: `vro-corpora/data/raw/language_guides/extra/vro_iva_2007.pdf`
- **Helen Plado (2026):** *Võru keele grammatika* (Võro Institute, June 2026) — full modern descriptive grammar of Võro.
- **GiellaLT `lang-vro`:** Finite-state morphological analyzer and spellchecker (`https://github.com/giellalt/lang-vro`).

## 2. Seto (`resources/seto/`)
- **Paul Hagu & Karl Pajusalu (2021):** *Seto keele teejuht* (Seto Instituut / Tartu Ülikool).
  - Local archive: `vro-corpora/data/raw/language_guides/seto/seto_keele_teejuht.pdf` (pp. 18–34, Tables 2–10).
  - Used for: `07-pronouns.md`, `08-comparison.md`, `09-numerals.md`, `10-inflection-tables.md`.
- **Seto Erisõnade Sõnaraamat (SESS 2020)** & **EKI Seto Dictionary** (`sonaveeb.ee` / `eki.ee`).

## 3. Mulgi (`resources/mulgi/`)
- **Triin Todesk (2022):** *Mulgi noomenimuutmise põhijooni* (*Emakeele Seltsi aastaraamat* 67, pp. 217–232).
  - Local archive: `vro-corpora/data/raw/language_guides/extra/mulgi_todesk_2022.pdf`
  - Used for: `11-paradigms.md` (24 principal declension classes, gradation & stem-alternation tables).
- **Triin Todesk, Kristi Ilves, Alli Laande, Karl Pajusalu & Marili Tomingas (2026):** *Mulgi sõnaraamatust ja unustatud sõnavarast*.
  - Local archive: `vro-corpora/data/raw/language_guides/extra/mulgi_todesk_2026.pdf`
- **Mulgi Kultuuri Instituut (`mulgimaa.ee`) Grammar Worksheets** (Alli Laande 2015; Kristi Ilves):
  - Local archive: `vro-corpora/data/raw/language_guides/mulgi/` (`Asesõna tüüleht.pdf`, `Käändetabel.pdf`, `Omadussõnade käänamine.pdf`, `MA - TEGEVUSNIMI  2 SILBILISED.pdf`, `Mulgi erinevuse tüüleht.pdf`, `Mulgi murde pääjoone.pdf`, `olevik, minevik.pdf`, `Kuul-kooli-kuuli.pdf`, `Kokkukõla ek vokaalharmoonia.pdf`, `Palatalisatsioon  mulgi keelen.pdf`).
  - Used for: `07-pronouns.md`, `08-comparison.md`, `10-inflection-tables.md`.
- **Mulgi sõnaraamat (2025)** (`eki.ee/dict/mulgi` / `sonaveeb.ee`) & **Karl Pajusalu (1996)** (*Multiple linguistic contacts in South Estonian: Variation of verb inflection in Karksi*).

## 4. Lutsi (`resources/lutsi/`)
- **Uldis Balodis (2020):** *Lutsi kiele lementar / Ludzas igauņu valodas ābece* (LU Lībiešu institūts & Ludzas pilsētas galvenā bibliotēka).
  - Local archive: `vro-corpora/data/raw/lutsi/Lutsikielelementar.pdf` (pp. 76–90, *Kīļ | Valoda*, based on August Sang 1936a/b & *Eesti murded IX*).
  - Used for: `07-pronouns.md`, `08-comparison.md`, `10-inflection-tables.md`.
- **Lutsi.org Paradigm Tables** (ingested as `lutsi_org_paradigms` in `south_estonian.db`).
  - Used for: `10-inflection-tables.md` (complete 13-case nominal paradigms & 18 indicative verb paradigms).
- **Miina Norvik, Uldis Balodis, Valts Ernštreits et al. (2021):** *The South Estonian language islands in the Central Baltic area* (*ESUKA–JEFUL* 12(2): 33–72).
  - Local archive: `vro-corpora/data/raw/all/pdf_collections/jeful_2021_12_2_islands/jeful_2021_12_2_02.pdf`
  - Used for: `08-comparison.md`, `10-inflection-tables.md`.

## 5. Kraasna (`resources/kraasna/`)
- **Tobias Weber (2021):** *A linguistic analysis of Kraasna recordings* (*ESUKA–JEFUL* 12(2): 343–390).
  - Local archive: `vro-corpora/data/raw/all/pdf_collections/jeful_2021_12_2_islands/jeful_2021_12_2_13.pdf` (Section 6 Morphology, Table 1 Pronominal forms, numerals 1–17).
  - Used for: `07-pronouns.md`, `09-numerals.md`, `10-inflection-tables.md`.
- **Miina Norvik et al. (2021):** *ESUKA–JEFUL* 12(2): 33–72 (comparatives, person-indexing, negation).
- **Tobias Weber Kraasna Archive** (`vro-corpora/data/raw/kraasna/pdf_collections/kraasna_wordpress/`), **Oskar Kallas (1903)** (*Kraasna Maarahvas*), & **Mets et al. (2014)** (*Eesti murded IX*).

## 6. Leivu (`resources/leivu/`)
- **Petri Kallio (2021):** *The position of Leivu* (*ESUKA–JEFUL* 12(2): 123–143).
  - Local archive: `vro-corpora/data/raw/all/pdf_collections/jeful_2021_12_2_islands/jeful_2021_12_2_05.pdf`
- **Miina Norvik et al. (2021):** *ESUKA–JEFUL* 12(2): 33–72 (comparatives, person-indexing, negation, phonology).
- **Janek Vaab (2026):** *Pääle sõa tettüq leivu helüülesvõttõq*.
  - Local archive: `vro-corpora/data/raw/language_guides/extra/leivu_vaab_2026.pdf`
- **Mets et al. (2014)** (*Eesti murded IX*), **Pire Teras (2010)** (*Quantity in Leivu*), & **Valter Niilus (1935, 1936)**.
  - Used for: `10-inflection-tables.md`.

## 7. Tartu (`resources/tartu/`)
- **Karl Pajusalu, Tiit Hennoste, Ellen Niit, Peeter Päll & Jüri Viikberg (2018):** *Eesti murded ja kohanimed* (3rd ed., Ch. 18 *Tartu murre*, pp. 182–187, based on Hella Keem 1970 *Tartu murde tekstid*).
  - Local archive: `vro-corpora/data/raw/all/pdf_collections/text/eesti_murded_ja_kohanimed_2018.txt`
- **Tartu & Mulgi Plurals Monograph** (`vro-corpora/data/raw/language_guides/extra/tartu_mulgi_plurals_1737.pdf`).
- **Jüri Viikberg (2020):** *Eesti murrete grammatika* (*Eesti keele varamu* VIII).
- **Historical Old Literary South Estonian Grammars:** Johann Gutslaff (1648), August Wilhelm Hupel (1780), Ferdinand Johann Wiedemann (1864).
  - Used for: `10-inflection-tables.md`.
