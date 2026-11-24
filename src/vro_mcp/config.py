from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser() if value else default


def _str_from_env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    south_estonian_db: Path
    models_dir: Path
    resources_dir: Path
    rules_dir: Path
    neurotolge_base_url: str
    analyzer_cmd: str
    generator_cmd: str
    speller_cmd: str
    grammar_cmd: str
    giella_share_dir: Path | None = None


def load_settings() -> Settings:
    giella_bin = REPO_ROOT / "tools" / "giella" / "bin"
    return Settings(
        south_estonian_db=_path_from_env("VRO_SOUTH_ESTONIAN_DB", REPO_ROOT / "data" / "south_estonian_public.db"),
        models_dir=_path_from_env("VRO_MODELS_DIR", REPO_ROOT / "models"),
        resources_dir=_path_from_env("VRO_RESOURCES_DIR", REPO_ROOT / "resources"),
        rules_dir=_path_from_env("VRO_RULES_DIR", REPO_ROOT / "src" / "vro_mcp" / "rules"),
        neurotolge_base_url=_str_from_env(
            "VRO_NEUROTOLGE_BASE_URL",
            "https://api.tartunlp.ai/translation/v2",
        ),
        analyzer_cmd=_str_from_env("VRO_ANALYZER_CMD", str(giella_bin / "analyze-vro")),
        generator_cmd=_str_from_env("VRO_GENERATOR_CMD", str(giella_bin / "generate-vro")),
        speller_cmd=_str_from_env("VRO_SPELLER_CMD", str(giella_bin / "spellcheck-vro")),
        grammar_cmd=_str_from_env("VRO_GRAMMAR_CMD", str(giella_bin / "grammar-check-vro")),
        giella_share_dir=_path_from_env("VRO_GIELLA_SHARE_DIR", REPO_ROOT / "data" / "giella-share"),
    )
