# Seto: Overview and Orthography

## Identity & Subvarieties
- **Language code:** `seto` (Seto; *seto kiil* / *seto keeľ*)
- **Family Relationship:** Closest sister variety to Võro within Eastern South Estonian (historically forming a tight Võro-Seto linguistic unit while maintaining strong Seto community, Orthodox cultural lexicon, and distinctive eastern grammar).
- **MCP Support:** Extensive `unified_dictionary` + `smugri4_seto_dictionary` + `eki_seto_dictionary` coverage, large corpus (`setomaa_pdf`, `setomaa_newspaper_corpus_cc`, `murdekorpus_seto`, `kogukond_setomaa`), parallel examples (`et`/`en`), Seto-tailored leakage linter, context-aware offline language classifier (`seto` vs `vro`), and **one-way** offline MT (`seto -> et`/`en` via `vro` source transfer; `et`/`en -> seto` is disabled to prevent Võro leakage into generated Seto).

## Orthography & Text Normalization Traps
1. **Apostrophe `'` / `’` (and `q`) Ambiguity:**
   - Word-finally (`pühä’`, `suurõ’`, `valli'`, `omma'`), the apostrophe (or `’`, occasionally `q` in mixed spellings) marks the **glottal stop** (noun plural, imperative, *da*-infinitive, negative connegative).
   - After/beside consonants (`k´auti`, `s´oo`, `as´atundja’`, `k´äve`, `ol´`), the apostrophe / acute accent marks **palatalization**!
   - **Critical rule:** NEVER treat apostrophes or acute palatalization marks as OCR noise or strip them before syntactic analysis.
2. **Pre-word Quantity Dot (`·`):** Traditional Seto editions sometimes print a middle/raised dot before a word to mark overlong (Q3) quantity. Do not split the token or flag it as corruption.
3. **High `õ` and Front/Back Vowel Harmony:** Front vowels (`ä`, `ö`, `ü`, `e`, `i`) vs back vowels (`a`, `o`, `u`, `õ`) strictly govern suffixes, including `õ` in non-initial syllables (`suurõ’`, `sõira-`, `olõ-õi`).
4. **Hagu & Pajusalu (2021) Standard:** Operational MCP norms follow *Seto keele teejuht* (Paul Hagu & Karl Pajusalu, Seto Instituut, 2021).
