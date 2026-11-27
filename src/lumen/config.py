"""Load configs/default.yaml and resolve repo-relative paths."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else ROOT / "configs" / "default.yaml"
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(rel: str | Path) -> Path:
    """Repo-relative path from the config -> absolute path."""
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p
