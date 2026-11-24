# Tartu: Overview and Orthography

## Identity & Dialect Position
- **Language code:** `tartu` (Tartu; *tarto kiil* / historic Old Literary South Estonian)
- **Geographic & Historical Role:** Northernmost branch of South Estonian (`tartumaa`), transitional between core Võro-Seto and Mulgi/Estonian, and historically the liturgical/literary base of *maakeel* (1686 *Wastne Testament*).
- **MCP Support:** `eki_ems_dictionary` + `eki_vms_dictionary` lexical entries (~11.5k), spoken corpus (`murdekorpus_tartu`, `eki_kiiker_tartu`), LLM parallel translations (~8.1k pairs), Tartu-specific leakage linter, offline language classifier (`tartu`), and cross-dialect cognate links.

## Writing & Dialect Transcription Conventions
1. **No Mandatory Written `q` in Practical Spelling:** Practical Tartu texts usually omit written `q` (using vocalic/endingless forms or `-va`/`-nu` instead of Võro `-vaq`/`-nuq`). Never enforce Võro `-q` rules onto Tartu.
2. **`murdekorpus_tartu` Academic Transcription Markers (Do Not Misread!):**
   - Backtick `` ` `` before a syllable (`\`valla`, `\`süvvä`, `\`suvve`, `\`anti`) marks **Q3 (overlong) quantity**, NOT a syntax delimiter.
   - `ʔ` (`Noʔ`) marks a phonetic **glottal stop**.
   - Underscore tie `‿` (`teevä‿vai`, `lännüvä‿ja`, `Nii‿et`) marks prosodic cliticization between adjacent words.
3. **Epenthetic Palatal Diphthongs:** Characteristic **`üits`** ("one", Võro `üts`) and **`kaits`** ("two", Võro `kats`), plus `täüs` / `väiga` / `nüid`.
4. **High `õ` and Vowel Harmony:** Present in stems and suffixes (`mõts`, `kõneles`, `tulõ`, `eläs`, `ütle`), though northern Tartu subdialects show partial weakening compared to core Võro/Seto.
