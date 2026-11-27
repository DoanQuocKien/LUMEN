"""Read-only access to the crawler's raw cache (PoliteFetcher layout). [W1-A3, W2-A1]

Each fetched URL is stored as `<sha1(url)>.body` (bytes) and `<sha1(url)>.json` (status, ...).
Only status-200 entries count as downloaded: failed rows (status 0 / 403 / 404) are ignored.
Pages and attachments share one cache directory per source.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def cached_body(cache_dir: str | Path, url: str) -> Path | None:
    """Path of the cached body for `url`, or None if missing or not HTTP 200."""
    key = cache_key(url)
    meta_p, body_p = Path(cache_dir) / f"{key}.json", Path(cache_dir) / f"{key}.body"
    if not (meta_p.exists() and body_p.exists()):
        return None
    try:
        status = json.loads(meta_p.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None
    return body_p if status == 200 else None


def lookup(cache_dirs: list[str | Path]):
    """fetch_path(url) -> first cache that holds the URL (ctsv and daa have separate caches)."""
    def fetch_path(url: str) -> Path | None:
        for d in cache_dirs:
            p = cached_body(d, url)
            if p is not None:
                return p
        return None
    return fetch_path
