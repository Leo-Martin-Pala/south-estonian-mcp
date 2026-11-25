# Public data coverage and licenses

## Initial noncommercial edition (data-v3-nc)

This release adds four components from the exact pinned TartuNLP distribution
at revision `902597137be2310f03f5b33292cb01c7585d639b`. The dataset's
CC BY-NC-SA 4.0 grant applies to these imports. Direct scrapes from the
same publishers have separate rights. The earlier `data-v2` is available
with its original permissive source selection.
[Pinned dataset card](https://huggingface.co/datasets/tartuNLP/smugri4-data/blob/902597137be2310f03f5b33292cb01c7585d639b/README.md)
[Pinned component credits](https://huggingface.co/datasets/tartuNLP/smugri4-data/blob/902597137be2310f03f5b33292cb01c7585d639b/corpus_source.md)

| Added component | Corpus units | Estonian pairs | Dictionary entries |
| --- | ---: | ---: | ---: |
| Uma Leht | 69,892 | — | — |
| Setomaa, 2020 onward | 9,969 | — | — |
| Võro `laused_n` provider usage examples | 30,201 | 30,201 | — |
| Võro `vasted_n` provider phrase equivalents | — | — | 78,755 |
| **Total added** | **110,062** | **30,201** | **78,755** |
| **Whole v3 dataset** | **203,988** | **37,453** | **95,180** |

News is deduplicated by language and normalized paragraph text. For
`laused_n`, the importer deduplicates exact normalized pairs and excludes
identical sides and ambiguous provider separators. The `vasted_n` rows
represent lexical and phrase groups. Their counts do not measure unique
headwords. Every new result can be traced to the exact upstream file.
The new rows are searchable by full text.

## Expanded noncommercial edition (data-v4-nc)

The official SMUGRI-4 package terms apply to the additional South Estonian
components from the same pinned revision. The importer verifies provenance,
retains attribution and deduplicates rows. The earlier permissively licensed
versions of the fiction, newspaper and parallel corpora remain available.

| Provider component added since v3 | Corpus units | Stored bilingual pairs |
| --- | ---: | ---: |
| `ilo` fiction | 9,132 | 0 |
| `setomaa` older newspaper archive | 6,609 | 0 |
| `vro-est` parallel corpus | 1,203 | 1,187 |
| `cifu_poordamine` appeal | 6 | 18 |
| `mes1` Mulgi dictionary examples | 4,919 | 4,919 |
| `sto1` Seto dictionary examples | 44,341 | 44,337 |
| **Total added** | **66,210** | **50,461** |
| **Whole v4 dataset** | **270,198** | **87,914** |

The EKI entries are searchable usage examples with contextual Estonian
equivalents. Four previously flagged Seto target glosses were omitted.
The appeal includes Estonian, English and German sides. The parallel corpus
keeps paired lines where source and target boundaries match and uses
document-level pairs otherwise. The server returns excerpts for long documents.
Public dictionary phrase entries total
95,180, unchanged from v3. Independent acquisitions of newspaper,
dictionary, and Facebook text retain their separate rights status.

## v2 baseline and private comparison

The public build uses licenses and public-domain notices that support
redistribution and adaptation, including commercial use. The builder admits
sources by exact identity. The private unified snapshot is the denominator.
The public totals include the publisher line-aligned parallel recovery, so they
measure available coverage after the upgrade. The counts are rows and may
include several senses or examples for the same term.

| Variety | Corpus units public / private | Dictionary entries public / private | Stored translations public / private |
| --- | ---: | ---: | ---: |
| Võro | 83,755 / 407,339 | 9,182 / 151,755 | 7,252 / 209,325 |
| Seto | 10,144 / 139,502 | 1,732 / 64,888 | 0 / 212,947 |
| Mulgi | 27 / 141,255 | 1,999 / 38,938 | 0 / 20,395 |
| Tartu | 0 / 8,617 | 2,302 / 14,845 | 0 / 8,387 |
| Leivu | 0 / 253 | 449 / 1,877 | 0 / 46 |
| Lutsi | 0 / 2,561 | 718 / 3,010 | 0 / 1,477 |
| Kraasna | 0 / 147 | 43 / 173 | 0 / 106 |
| **Total** | **93,926 / 699,674** | **16,425 / 275,486** | **7,252 / 452,683** |

The public build has 86.58% fewer corpus units, 94.04% fewer dictionary entry
rows, and 98.40% fewer stored translations than the private snapshot.
Stored translations in the public build are human Võro–Estonian examples.
They include 7,238 pairs from the publisher's line-aligned archive and 14
previously verified pairs. Three archive files with unequal line counts were
skipped for automatic line alignment. The private denominator also includes
machine and LLM translations whose target-side provenance is incomplete.

The earlier public release had 43,503 corpus segments. The new total is 2.16
times as large by row count, with different segmentation. The earlier
dictionary had 6,637 language-term rows in a concept schema. Its row count is
in a different unit from the unified entry count. The new release adds
1,306 Estonian IDS glosses joined by concept and has dictionary coverage in all
seven varieties.

The release builder prints the counts from the input and rebuilt database.
It reconstructs word frequencies and search indexes from approved content.
It includes 23,557 vectors for corpus units, 13,819 vectors for dictionary
definitions, and 14 vectors for translations. The remaining rows are available
through full-text search.

## License evidence

- **Väike murdesõnastik.** EKI distributes the exact electronic text and
  locality files on its reuse downloads page. The local import points to the
  same `vms.t` source. The public build includes 12,509 entries with EKI credit
  under the site's standard CC BY 4.0 terms.
  [EKI reuse terms](https://arhiiv.eki.ee/litsents/)
  [Edition download](https://arhiiv.eki.ee/litsents/vaba/dl.cgi?D=vms)
- **Mulk muigas.** DIGAR marks the exact 2021 edition Public Domain. This
  contributes 27 Mulgi corpus units.
  [National Library catalog](https://www.digar.ee/arhiiv/et/raamatud/184835)
- **Setomaa.** The permitted corpus is the licensed 2006–2013 distribution.
  The extraction memo records that the download agreement identified CC BY-SA
  3.0. The separate collected PDF source has 77,065 private units and needs
  its own grant or exact matches against the licensed archive.
  [META-SHARE distribution](https://metashare.ut.ee/repository/browse/setomaa-newspaper-corpus/3303e60ca0d411eebb4773db10791bcf2d01e0b55ce2419db34ef402460a1c99/)
- **Synaq.** The official catalog lists the portal under a proprietary license.
  The Synaq scrape contributes 65,309 private dictionary entries. Seek a
  license for a specific dictionary export from the Võro Institute.
  [META-SHARE record](https://metashare.ut.ee/repository/browse/sunaqorg-web-dictionary-of-voro-and-seto-languages/4b3cdd6ca0d411eebb4773db10791bcf741086378b9d4181b1395028dc86e5c2/)
- **EKI dictionaries.** The EMS catalog says CC BY for an `a–pari` edition
  whose availability is under negotiation. The 2011 Old Võru record says
  CC BY with a Share Alike restriction and is also under negotiation. The
  Mulgi record describes the 2013 edition, alongside academic/noncommercial
  restrictions. The 2025 Mulgi import and the SESS query interface need an
  explicit grant for their respective editions.
  [EMS](https://metashare.ut.ee/repository/browse/dictionary-of-estonian-dialects/366a688ca0d411eebb4773db10791bcf139297a68a5244c7ad493eb7528123f6/)
  [Old Võru](https://metashare.ut.ee/repository/browse/the-dictionary-of-old-voru-dialect/1d52ecf8a0d411eebb4773db10791bcf646c54ddd9dd4004a4377915f5dc4b8f/)
  [Mulgi 2013](https://metashare.ut.ee/repository/browse/the-dictionary-of-the-mulgi-dialect/04eb195ca0d411eebb4773db10791bcf49f63692e3f54a6a8b9ddbe8050d182d/)
  [SESS](https://arhiiv.eki.ee/dict/setoeri/)
- **Estonian Dialect Corpus.** The catalog specifies restricted use under
  CLARIN ACA. The four local varieties account for 46,628 units.
  [META-SHARE record](https://metashare.ut.ee/repository/browse/estonian-dialect-corpus/fa3c4b2aa0d311eebb4773db10791bcfd02e3a0c0eca4e46bf2eeccb5187625d/)
- **SMUGRI-4.** The 216,980 Võro and Seto corpus rows carry a coarse local
  CC BY-NC-SA label. The provider reports mixed licenses on the underlying
  works. Verify the license and attribution per original component, and
  verify the target side before sharing pairs.
  [Provider data card](https://huggingface.co/datasets/tartuNLP/smugri4-data)
- **Uma Leht.** The 116,361 imported units have no verified redistribution
  grant. The catalog lists the corpus search service as proprietary.
  [META-SHARE catalog](https://metashare.ut.ee/repository/search/?q=eesti+korpus&selected_facets=availabilityFilter_exact%3ANot+Available+Through+Meta+Share&selected_facets=licenceFilter_exact%3AProprietary&selected_facets=resourceTypeFilter_exact%3AtoolService&sort=resourcetype_asc)
- **Lutsi historical material.** Kallas's 1900 source is a promising candidate
  for a fresh extraction. The existing 927 units came from a modern annotated
  web edition. Match the original printing before importing them.
  [Archive editions](https://www.folklore.ee/muinasjutt/)

The two Facebook sources account for 1,780 corpus units and 1,675 translations.
They are excluded along with sources lacking a verified grant. The temporary
WordNet tools and data are outside this release.

## SMUGRI-4 components

TartuNLP reports 3,266,531 Võro tokens, 283,598 Setu tokens, and 26,895 Mulgi
tokens. The downloadable collection carries CC BY-NC-SA 4.0. This permits
public noncommercial sharing with credit and share-alike. Original-source
terms vary. [Dataset card](https://huggingface.co/datasets/tartuNLP/smugri4-data)
[License deed](https://creativecommons.org/licenses/by-nc-sa/4.0/)

| Provider component | Evidence and public coverage |
| --- | --- |
| `ilo` | The licensed original fiction corpus is already used by the public MCP. |
| `setomaa` | The original licensed 2006–2013 Setomaa archive is already used by the public MCP. |
| `vro-est` | The original licensed parallel corpus provides the public MCP's human pairs. |
| `setomaa_2020jne`, `umaleht` | Separate newspaper material. Unrestricted redistribution grant unverified. |
| `laused_n`, `vasted_n` | Examples and equivalent phrases. A separate unrestricted grant is unverified. |
| `cifu_poordamine` | Appeal text. Unrestricted redistribution grant unverified. |
| `eki_dictionary` | Seto and Mulgi dictionary examples. The package carries the noncommercial label. Exact edition rights need confirmation. |

The [provider source list](https://huggingface.co/datasets/tartuNLP/smugri4-data/blob/main/corpus_source.md)
identifies each component. The public release uses the original licensed
distributions of the three matched components. The private MCP's five
SMUGRI-labelled sources account for 216,980 corpus units, 234,971 stored
translations and 102,131 dictionary rows. Matching exact source works and
deduplicating against the public corpus comes before estimating new coverage.

## Highest-impact improvements

1. Recover permissively licensed SMUGRI components by matching provider
   files to the original publications. This is the largest available pool of
   corpus rows. Keep explicit evidence for both sides of each translation.
2. Ask EKI for exact reusable exports of EMS, Mulgi and Seto. A grant covering
   the imported EMS alone would yield up to 48,291 dictionary rows across the
   varieties, including the ones with the least public data. Ask the Võro
   Institute for the Synaq dictionary export in parallel.
3. Complete embedding coverage and promote attributable GiellaLT Seto and
   Mulgi builds. Pair these with published human examples for the varieties
   with little prose, starting with the original Kallas Lutsi material and
   a verified Mulgi archive.
