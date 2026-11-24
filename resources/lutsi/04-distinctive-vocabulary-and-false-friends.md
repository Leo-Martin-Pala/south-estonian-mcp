# Lutsi: Distinctive Vocabulary and False Friends

## Attested Lexicon & Parallel Phrases (`lutsi_v1.4.sqlite` / EMS / VMS)
| Lutsi Form (`practical` / `UPA`) | Meaning | Recognition Trap |
| --- | --- | --- |
| `y` words: `vyeras`, `kyvaq`, `vytnuq`, `vytiq`, `hybehane` | *võõras*, *kõvad*, *võtnud*, *võtsid*, *hõbehane* | In practical Lutsi, **`y` = `õ`**, NOT `ü`! |
| `um` / `ummaq` | *on* / is, are | Variant of South Estonian `om`/`ommaq` |
| `ole-eiq` / `ole-es` | *ei ole* / *ei olnud* | Postposed negation clitic — always check after hyphen! |
| `üțș` / `üt̅’s` | *üks* / one | Latvian-style `țș` palatal affricate |
| `lațș` / `лat̅’s` | *laps* / child | Compare Võro `lats` |
| `piniq` (`pini`) / `repän` (`rebäze`) | *koerad* / *rebane* (`rebase`) | Core South Estonian fauna vocabulary |
| `kallu` (`kalaq`) | *kalu* (*kalad*) | Partitive plural `kallu` vs nom pl `kalaq` |
| `neoq` | *need* / those | `"Kost sa neoq kalaq vytiq?"` ("Where did you get those fish?") |
| `kost` | *kust* / from where | Interrogative adverb |
| `nār` | *naerab* / laughs | `Repän nār.` (endingless 3sg + macron long `ā`) |
| `voiska` | army, troops | Slavic/Latgalian loan attested in `"Kuningas lähäț voiska poiga oțșma"` |
| `oțșma` | *otsima* / look for | Syncopated supine (`otsma`) with `țș` |
| `hameq` (`hamè͔ˀ`) | *särk* / shirt | South Estonian core word (`hame`) |

## Cross-Dialect Guardrail
- Never strip Lutsi macrons (`mā`, `nār`, `lǟ`), practical `y` (= *õ*), `țș`/`ļ`/`ņ`/`ŗ`, or UPA characters when looking up words: use `lookup_words(word, lang="lutsi")`, which matches **both** practical and UPA inflections directly in `dict_inflections`.
