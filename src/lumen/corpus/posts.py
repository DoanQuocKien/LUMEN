"""Parse every cached post page into posts.jsonl (no network). [W1-A3]

Input: the listing CSV written by the crawler (columns url,title,date,sections) and its cache.
Posts that were not fetched, or fetched with a non-200 status, are counted and skipped.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from lumen.corpus.cache import cached_body
from lumen.parse.html import parse_post


def parse_cached_posts(listing_csv: str | Path, cache_dir: str | Path) -> tuple[list[dict], int]:
    posts, missing = [], 0
    with open(listing_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        body = cached_body(cache_dir, r["url"])
        if body is None:
            missing += 1
            continue
        post = parse_post(body.read_text(encoding="utf-8", errors="replace"), r["url"])
        post["date"] = post["date"] or (r.get("date") or None)  # page date wins; listing date is the fallback
        post["title"] = post["title"] or r.get("title", "")
        post["sections"] = [s for s in (r.get("sections") or "").split(";") if s]
        posts.append(post)
    return posts, missing


def write_posts(posts: list[dict], out: str | Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in posts), encoding="utf-8")
