"""
Modal deployment for the Võro MCP server (Tier 2: full, incl. GiellaLT tools).

Deploy with:   modal deploy modal_app.py
See DEPLOY.md for the full first-time setup (volume upload + secret).

Heavy data (SQLite DBs + Giella FST models) lives in the "south-estonian-mcp-data" Modal
Volume, NOT in this image or in git. Only code + system binaries are baked in.
"""

import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import modal

APP_NAME = os.getenv("MODAL_APP_NAME", "south-estonian-mcp")
VOLUME_NAME = os.getenv("MODAL_VOLUME_NAME", "south-estonian-mcp-data")
SECRET_NAME = os.getenv("MODAL_SECRET_NAME", "south-estonian-mcp-secret")

# --- System binaries the Giella wrappers shell out to --------------------------
# hfst-optimized-lookup, hfst-ospell, and divvun-checker come from the Apertium/
# Divvun nightly apt repo. Use a Bookworm base because the Bullseye nightly
# metadata has pointed at removed .deb files.
image = (
    modal.Image.from_registry("python:3.11-slim-bookworm")
    .apt_install("curl", "ca-certificates", "gnupg", "perl", "gawk", "bash", "lsb-release")
    .run_commands(
        "curl -fsSL https://apertium.projectjj.com/apt/install-nightly.sh | bash",
        "apt-get update",
        "apt-get install -y --no-install-recommends "
        "hfst hfst-ospell cg3 divvun-gramcheck",
        "rm -rf /var/lib/apt/lists/*",
    )
    .pip_install("mcp>=1.0.0", "libsql>=0.1.11")
    # Point config + Giella wrappers at the Volume-mounted data (see /data below).
    .env(
        {
            "PYTHONPATH": "/app/src",
            "VRO_SOUTH_ESTONIAN_DB": "/data/south_estonian_public.db",
            "VRO_GIELLA_SHARE_DIR": "/data/giella-share",
            "VRO_MODELS_DIR": "/data/models",
        }
    )
    # App code (small) is added last so Modal can mount it efficiently at startup.
    .add_local_dir("src", "/app/src")
    .add_local_dir("resources", "/app/resources")
    .add_local_dir("tools/giella/bin", "/app/tools/giella/bin")
)

app = modal.App(APP_NAME)

# Persistent storage for the big read-only data. Uploaded once from your laptop.
data = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _download_and_extract(url: str, destination: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".tar.xz") as archive:
        print(f"Downloading {url}")
        urllib.request.urlretrieve(url, archive.name)
        with tarfile.open(archive.name, "r:xz") as tar:
            for member in tar.getmembers():
                target = (destination / member.name).resolve()
                if destination.resolve() not in target.parents and target != destination.resolve():
                    raise ValueError(f"archive member escapes destination: {member.name}")
            tar.extractall(destination, filter="data")


@app.function(
    image=image,
    volumes={"/data": data},
    timeout=600,
)
def hydrate_release_data(
    *,
    force: bool = False,
    repo: str = "Leo-Martin-Pala/south-estonian-mcp",
    data_tag: str = "data-v3-nc",
    giella_tag: str = "giella-v1",
):
    data_root = Path("/data")
    db_path = data_root / "south_estonian_public.db"
    giella_root = data_root / "giella-share"
    release_marker = data_root / ".dataset-release"
    release = f"{repo}@{data_tag}"
    installed_release = release_marker.read_text().strip() if release_marker.exists() else None

    if force or not db_path.exists() or installed_release != release:
        from vro_mcp.public_data import verify_public_data

        url = f"https://github.com/{repo}/releases/download/{data_tag}/vro-data.tar.xz"
        with tempfile.TemporaryDirectory() as extracted:
            extracted_root = Path(extracted)
            _download_and_extract(url, extracted_root)
            source = extracted_root / db_path.name
            verify_public_data(source)
            staged = data_root / f".{db_path.name}.incoming"
            shutil.copy2(source, staged)
            staged.replace(db_path)
        release_marker.write_text(release + "\n")
        print("Public dataset is present in the Modal Volume.")
    else:
        print("Public dataset already exists; skipping release download.")

    if force or not giella_root.exists():
        url = f"https://github.com/{repo}/releases/download/{giella_tag}/giella-share.tar.xz"
        giella_root.mkdir(parents=True, exist_ok=True)
        _download_and_extract(url, giella_root)
        print("Giella artifacts are present in the Modal Volume.")
    else:
        print("Giella artifacts already exist; skipping release download.")

    data.commit()


@app.local_entrypoint()
def hydrate_release():
    force = os.getenv("FORCE_DATA", "0") == "1"
    repo = os.getenv("VRO_DATA_REPO", "Leo-Martin-Pala/south-estonian-mcp")
    data_tag = os.getenv("VRO_DATA_TAG", "data-v3-nc")
    giella_tag = os.getenv("VRO_GIELLA_TAG", "giella-v1")
    hydrate_release_data.remote(
        force=force,
        repo=repo,
        data_tag=data_tag,
        giella_tag=giella_tag,
    )


@app.function(
    image=image,
    volumes={"/data": data},
    # Holds MCP_PATH=/<random>/mcp -> the unguessable secret URL segment.
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    min_containers=0,  # scale to zero when idle => effectively free
    timeout=120,
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def serve():
    from vro_mcp.server import create_server

    return create_server().streamable_http_app()
