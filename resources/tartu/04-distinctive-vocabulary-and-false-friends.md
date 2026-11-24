# Tartu: Distinctive Vocabulary and False Friends

## Characteristic Tartu Forms & Lexicon
| Tartu Word | Standard Estonian / Meaning | Linguistic Note |
| --- | --- | --- |
| `üits` / `kaits` (`üte`) | *üks* / *kaks* (*ühe*) | Characteristic palatal epenthesis `i` before `ts` |
| `säidse` | *seitse* / seven | Palatal diphthongization |
| `nuu` / `naa` / `näile` | *need* / *nemad* / *neile* | `"mis nuu sääl teevä"`, `"ku‿na kodu tulliva"` |
| `tsuvva` (`tsuvvad`?) | *tsuva* / birch-bark shoes / leather shoes | Seen in `"tsuvva kabla"` ("shoe laces") |
| `kaema` | *vaatama* / look, check | `"aina manu \`kaema"` |
| `manu` | *juurde* / to, beside | Spatial postposition |
| `tsiga` (`tsia-`) | *siga* / pig (`tsiakarjan`) | South Estonian palatal affricate `ts` |
| `valla` | *lahti, vabaks* / loose, open | `"jala \`valla \`võtmine"` |
| `pallu` / `väiga` / `nüid` | *palju* / *väga* / *nüüd* | Diphthongized/South Estonian forms |
| `midägi` | *midagi* / something | Front vowel harmony `ä` |
| `jaanihain` | *jaani-õnnehein / nõmm-liivatee / kassiristik* | Multi-sense dialect plant name (EMS/VMS) |
| `jaamaline` | *jaamamineja; postijaamas elunev isik* | Attested in `eki_ems_dictionary` for `tartu` |

## Practical Orthography vs Spoken Corpus Traps
- Do not confuse Q3 marks (`` `valla ``), prosodic clitic ties (`teevä‿vai`), or phonetic `ʔ` (`Noʔ`) in `murdekorpus_tartu` with corrupted UTF-8 or broken OCR.
- `kõtu` (`"kõtu olliva tühä"`) is nominative **plural** matching plural verb `olliva` and plural adjective `tühä`.
- Check `eki_ems_dictionary` and `eki_vms_dictionary` via `lookup_words(..., lang="tartu")` to confirm regional Tartu plant/agricultural/folk terminology before borrowing Estonian terms.
