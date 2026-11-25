#!/usr/bin/env sh
# Download the Võro SQLite datasets from the GitHub release and extract them
# into data/. The archive bundles the dataset LICENSE and NOTICE.
set -eu

# Bump this default tag whenever you publish a new dataset release.
REPO="${VRO_DATA_REPO:-Leo-Martin-Pala/south-estonian-mcp}"
TAG="${VRO_DATA_TAG:-data-v4-nc}"
ASSET="vro-data.tar.xz"

cd "$(dirname "$0")/.."
mkdir -p data

tmp="$(mktemp)"
staging="$(mktemp -d data/.public-dataset.XXXXXX)"
trap 'rm -f "$tmp"; rm -rf "$staging"' EXIT

echo "Fetching $ASSET from $REPO@$TAG ..."
if command -v gh >/dev/null 2>&1; then
    gh release download "$TAG" --repo "$REPO" --pattern "$ASSET" --output "$tmp" --clobber
else
    curl -fL "https://github.com/$REPO/releases/download/$TAG/$ASSET" -o "$tmp"
fi

tar xJf "$tmp" -C "$staging" south_estonian_public.db LICENSE NOTICE
python3 src/vro_mcp/public_data.py "$staging/south_estonian_public.db"
if grep -Fq 'LICENSE-NC-SA' "$staging/NOTICE"; then
    tar xJf "$tmp" -C "$staging" LICENSE-NC-SA
    mv "$staging/LICENSE-NC-SA" data/LICENSE-NC-SA
fi
mv "$staging/LICENSE" data/LICENSE
mv "$staging/NOTICE" data/NOTICE
mv "$staging/south_estonian_public.db" data/south_estonian_public.db
ls -lh data/south_estonian_public.db
