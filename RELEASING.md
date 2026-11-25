# Building and publishing the public dataset

Build from a unified South Estonian snapshot using the reviewed
[source manifest](src/vro_mcp/sources-public.json). The source database is opened
read-only. The build creates a fresh database, adds source attribution, and
rebuilds the full-text and vector indexes, word frequencies, and cognate groups.

```sh
PYTHONPATH=src .venv/bin/python scripts/build_public_data.py /path/to/source.db \
  --wiki-dump /path/to/fiu_vrowiki-pages-articles-multistream.xml \
  --documents /path/to/fiction-metadata.jsonl \
  --documents /path/to/setomaa-metadata.jsonl \
  --publisher-parallel /path/to/paralleelkorpus-master \
  --estonian-ids /path/to/ids_et_dictionary.tsv

python3 src/vro_mcp/public_data.py data/south_estonian_public.db
make test
make package-data
```

Repeat `--wiki-dump` for older snapshots needed to identify pages, in
chronological order, and `--documents` for each source metadata file.
For the noncommercial edition, also pass `--smugri-root` pointing to a
checkout of [TartuNLP SMUGRI-4](https://huggingface.co/datasets/tartuNLP/smugri4-data)
at revision `902597137be2310f03f5b33292cb01c7585d639b` and save the official
[CC BY-NC-SA 4.0 legal text](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.txt)
as `data/LICENSE-NC-SA`. Git LFS data can be checked out in place or placed
under `lfs_objects/` beside the checkout, preserving its relative path.
The importer checks the pinned Git blob or LFS object before reading it.

GiellaLT artifacts are released separately with `make package-giella`.
Use a fresh GitHub release tag for each dataset revision, then update
`VRO_DATA_TAG` defaults when publishing a new server version.

```sh
make release-data DATA_TAG=data-v4-nc
```
