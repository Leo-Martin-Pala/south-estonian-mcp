# Deploy South Estonian MCP on Modal

The public deployment uses the Modal app `south-estonian-mcp`, the
`south-estonian-mcp-data` volume, and the `south-estonian-mcp-secret` secret.
The deploy script reads settings from `.env.public` and saves the generated
route there. Treat the route as a credential.

After authenticating the Modal CLI, use `make deploy-release` to hydrate the
volume from GitHub and deploy. Set `VRO_DATA_TAG` or `VRO_GIELLA_TAG` to
select a specific release. For a locally built dataset, use `make deploy-local`.
Use `make deploy-none` for a code-only update after the volume is ready.

To update an existing deployment while retaining the stored Modal secret:

```sh
modal run modal_app.py::hydrate_release
modal deploy modal_app.py
```

The public database uses `/data/south_estonian_public.db`. It can be installed
alongside the earlier dataset. Existing GiellaLT artifacts live in
`/data/giella-share`. The data packaging and upload paths validate the public database before publication.
The default is the noncommercial `data-v3-nc` edition. The deploy command
downloads the selected dataset when its release tag changes. Set
`VRO_DATA_TAG=data-v2` for the earlier edition.

The default hosted image supports full-text search and the existing translation
API. To enable semantic search in your deployment, install the semantic Python
dependencies in the Modal image and provision the pinned Voyage model under
`/data/models/voyage_4_nano`. See [README.md](README.md).

Use an MCP client to connect to the deployment's URL followed by its stored
`MCP_PATH`. Verify the tool list, `get_language_stats`, and one corpus query.
