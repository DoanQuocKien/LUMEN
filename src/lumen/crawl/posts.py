"""Fetch the selected post pages and their attachments into the raw cache. [W1-A2]

Selection rules live in the config (`crawl.select`); see select_posts(). Order: newest dated
posts first, then undated ones, then reference documents, so the run can be stopped at any time
and still hold the most useful posts. Resumable: every response is cached by URL, and
`post_status.jsonl` (next to the listing CSV) records one line per post.

Usage:  python scripts/02_crawl_posts.py --config configs/default.yaml -v
        python scripts/02_crawl_posts.py --config configs/daa.yaml -v
        --max 20 for a quick test, --no-attachments to fetch pages only.
Attachments share the post cache and the 10 s delay (one fetcher, one clock).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import yaml
from bs4 import BeautifulSoup

from lumen.crawl.http import DisallowedError, PoliteFetcher
from lumen.crawl.listing import ListingItem, load_index

log = logging.getLogger(__name__)

ATTACH_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png")


def select_posts(index: dict[str, ListingItem], rules: dict) -> list[ListingItem]:
    """Apply crawl.select rules and return posts in crawl order.

    rules: since (ISO date), undated_title_regex, reference_sections (kept regardless of date),
    exclude_title_regex (dropped first). Missing keys disable that rule."""
    since = rules.get("since")
    undated_re = re.compile(rules["undated_title_regex"]) if rules.get("undated_title_regex") else None
    exclude = re.compile(rules["exclude_title_regex"], re.I) if rules.get("exclude_title_regex") else None
    ref_sections = set(rules.get("reference_sections", []))
    recent, undated, reference = [], [], []
    for it in index.values():
        if exclude and exclude.search(it.title):
            continue
        if since is None or (it.date and it.date[:10] >= since):
            recent.append(it)
        elif it.sections & ref_sections:
            reference.append(it)
        elif not it.date and undated_re and undated_re.search(it.title):
            undated.append(it)
    recent.sort(key=lambda it: it.date or "", reverse=True)
    undated.sort(key=lambda it: it.url)
    reference.sort(key=lambda it: it.url)
    return recent + undated + reference


def attachment_links(html: str, page_url: str) -> list[str]:
    """Same-host file links inside the main content block (PDF, Office, images)."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("#block-system-main") or soup
    host = urlsplit(page_url).netloc
    out: list[str] = []
    for a in main.select("a[href]"):
        u = urlsplit(urljoin(page_url, a["href"]))
        if u.netloc == host and u.path.lower().endswith(ATTACH_EXT):
            url = u._replace(query="", fragment="").geturl()
            if url not in out:
                out.append(url)
    return out


def _done(status_path: Path) -> dict[str, dict]:
    if not status_path.exists():
        return {}
    rows = [json.loads(l) for l in status_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {r["url"]: r for r in rows}


@dataclass
class _Failed:
    """Stand-in for a fetch that raised after all retries (status 0)."""
    status: int = 0
    content: bytes = b""
    text: str = ""
    from_cache: bool = False


def _get(fetcher: PoliteFetcher, url: str):
    try:
        return fetcher.get(url)
    except (RuntimeError, DisallowedError) as exc:     # one bad URL must not stop a multi-hour crawl
        log.warning("%s: %s", url, exc)
        return _Failed()


def crawl_posts(fetcher: PoliteFetcher, items: list[ListingItem], status_path: Path,
                attachments: bool = True, limit: int | None = None) -> dict[str, int]:
    done = _done(status_path)
    stats = {"posts": 0, "failed": 0, "attachments": 0, "attachments_failed": 0, "skipped": 0}
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("a", encoding="utf-8") as out:
        for n, it in enumerate(items):
            if limit is not None and n >= limit:
                break
            if done.get(it.url, {}).get("status") == 200:
                stats["skipped"] += 1
                continue
            res = _get(fetcher, it.url)
            row = {"url": it.url, "status": res.status, "attachments": [],
                   "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            if res.status == 200:
                stats["posts"] += 1
                if attachments:
                    for au in attachment_links(res.text, it.url):
                        ar = _get(fetcher, au)
                        row["attachments"].append({"url": au, "status": ar.status, "bytes": len(ar.content)})
                        stats["attachments" if ar.status == 200 else "attachments_failed"] += 1
            else:
                stats["failed"] += 1
                log.warning("%s -> HTTP %d", it.url, res.status)
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            log.info("%4d/%d %s (%d attachments)%s", n + 1, len(items), it.url.rsplit("/", 1)[-1][:60],
                     len(row["attachments"]), " [cache]" if res.from_cache else "")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch selected posts and attachments.")
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--max", type=int, help="stop after N posts (for testing)")
    ap.add_argument("--no-attachments", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    c, paths = cfg["crawl"], cfg["paths"]
    if "<your-email>" in c["user_agent"]:
        print("Set a contact email in crawl.user_agent in the config first.", file=sys.stderr)
        return 2
    index = load_index(Path(paths["listing_index"]))
    items = select_posts(index, c.get("select", {}))
    print(f"{len(items)} of {len(index)} posts selected")
    fetcher = PoliteFetcher(c["base_url"], paths["raw_html"], c["user_agent"], delay_s=c["crawl_delay_s"],
                            timeout_s=c["timeout_s"], max_retries=c["max_retries"])
    status = Path(paths["listing_index"]).with_name("post_status.jsonl")
    stats = crawl_posts(fetcher, items, status, not args.no_attachments, args.max)
    print(stats, f"{fetcher.n_requests} requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
