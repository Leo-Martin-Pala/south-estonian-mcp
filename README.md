# South Estonian MCP

MCP tools for Võro, Seto, Mulgi, Tartu, Leivu, Lutsi, and Kraasna. Look up
dictionary entries and related forms, find attested usage, check a draft, or
consult grammar and inflection references from an MCP client.

## Install and connect

Use Python 3.11 or later. From this checkout:

```sh
make install
make data
.venv/bin/south-estonian-mcp-check
codex mcp add south-estonian -- "$PWD/.venv/bin/south-estonian-mcp"
```

Use `claude mcp add south-estonian -- "$PWD/.venv/bin/south-estonian-mcp"` for
Claude Code. For a client that takes a JSON command, run `make local-url`.
Update existing MCP client configurations to use the new `south-estonian-mcp` command.

On Debian or Ubuntu, `make setup` also installs the GiellaLT binaries and
downloads the existing Võro runtime bundle. See [DEPLOY.md](DEPLOY.md) for the
hosted service and [RELEASING.md](RELEASING.md) for dataset builds.

## Tools

| Task | Tools |
| --- | --- |
| Find a form or meaning | `lookup_words`, `search_dictionary_semantic`, `find_cognates` |
| Find real usage or human translations | `search_corpus`, `get_word_usage_examples`, `search_parallel_examples`, `word_exists_in_bag` |
| Review a draft | `lint_text`, `check_purity_with_rules`, `find_unknown_words`, `find_unrecognized_words`, `count_text` |
| Analyze and generate forms | `analyze_word`, `generate_forms`, `generate_paradigm`, `suggest_correction` |
| Check spelling and grammar | `spellcheck`, `grammar_check` |
| Translate and classify | `translate_mt`, `classify_language` |
| Read references or inspect setup | `get_grammar_resource`, `get_language_stats`, `check_setup` |

Võro morphology and proofing use GiellaLT. The same tools support Seto and
Mulgi when their corresponding artifacts are installed. The standard
`giella-v1` download provides Võro. Grammar guides and rule-based checks cover
all seven varieties. `translate_mt` uses Neurotõlge for supported Võro API
directions, with optional local models for offline translation and Seto transfer.

The public data release has dictionary entries across all seven varieties.
Corpus search covers Võro and Seto, with a small Mulgi sample. Parallel search
returns human Võro–Estonian pairs, including provider-supplied usage examples.
The default `data-v3-nc` adds SMUGRI-4 material under CC BY-NC-SA 4.0.
Use `VRO_DATA_TAG=data-v2 make data` for the earlier dataset without the
noncommercial material. Use `get_language_stats` to inspect coverage
by language and source. See the [coverage and license audit](docs/public-data-audit.md)
and [source manifest](src/vro_mcp/sources-public.json).

## Optional models

Full-text search works with the base install. For hybrid and vector search,
install the semantic extra and fetch the Apache-2.0 Voyage checkpoint used by
the release's vector index.

```sh
.venv/bin/pip install -e '.[semantic]'
.venv/bin/hf download voyageai/voyage-4-nano \
  --revision 433ece5e27a1611e9360dd7134ecaaf79fb3681d \
  --local-dir models/voyage_4_nano
```

Model files belong in `VRO_MODELS_DIR` (default `models/`). The
`classifier` and `local-mt` Python extras enable locally supplied compatible
models in `language_id/` and `mt_smugri_fp16/`. Run `check_setup` to see
which optional components are installed.

Use `VRO_SOUTH_ESTONIAN_DB` to choose a public-format database and
`VRO_GIELLA_SHARE_DIR` to choose a GiellaLT artifact directory.
`VRO_NEUROTOLGE_BASE_URL` selects a compatible translation API.

Project code is MIT licensed. Dataset and GiellaLT notices are separate.
[Licenses and attribution](NOTICE.md)
