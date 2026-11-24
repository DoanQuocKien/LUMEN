"""Crawl the site's listing pages into posts_index.csv. [W1-A1]

Site structure (checked 22/11/2026, Drupal 7):
- Each menu section (/thong-bao, /quyet-dinh, /quy-che-quy-dinh, ...) is a listing
  inside `#block-system-main`, paginated with `?page=N` and a `.pager-next` link.
- /thong-bao shows teasers: `article.node-teaser` > `h2 a`, date in
  `.submitted span[content]` (ISO 8601).
- /quyet-dinh and most others show title lists: `.views-row` > `a`, sometimes with
  `span.date` "(dd-mm-yyyy)", often with no date at all (filled in later from the post page).

Usage (from the repository root):
    python -m lumen.crawl.listing                    # every section in the config
    python -m lumen.crawl.listing --max-pages 2 -v   # quick test
    python -m lumen.crawl.listing --refresh          # re-fetch listings to pick up new posts

Re-running is cheap: pages already fetched come from the cache, so a crash only
costs the page that was in progress.
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import yaml
from bs4 import BeautifulSoup

from lumen.crawl.http import PoliteFetcher

log = logging.getLogger(__name__)

POST_PATH = "/bai-viet/"
CSV_FIELDS = ["url", "title", "date", "sections"]
_DMY = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})")


@dataclass
class ListingItem:
    url: str
    title: str
    date: str | None
    sections: set[str] = field(default_factory=set)


def clean_url(href: str, page_url: str, post_path: str = POST_PATH) -> str | None:
    """Absolute post URL without query or fragment, or None if it isn't a post.

    post_path "/" accepts any path (daa.uit.edu.vn posts are root-level slugs)."""
    parts = urlsplit(urljoin(page_url, href))
    if not parts.path.startswith(post_path) or parts.path.rstrip("/") == post_path.rstrip("/"):
        return None
    if parts.netloc != urlsplit(page_url).netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _dmy_to_iso(text: str) -> str | None:
    m = _DMY.search(text)
    if not m:
        return None
    d, mth, y = m.groups()
    return f"{y}-{int(mth):02d}-{int(d):02d}"


def parse_listing(html: str, page_url: str,
                  post_path: str = POST_PATH) -> tuple[list[ListingItem], str | None]:
    """Return the posts on one listing page and the absolute URL of the next page."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("#block-system-main")
    if main is None:
        log.warning("%s: no #block-system-main, falling back to #content", page_url)
        main = soup.select_one("#content") or soup

    items: dict[str, ListingItem] = {}

    def add(a, date):
        url = clean_url(a.get("href", ""), page_url, post_path)
        title = a.get_text(" ", strip=True)
        if url and title and url not in items:
            items[url] = ListingItem(url, title, date)

    for art in main.select("article.node-teaser"):
        a = art.select_one("h2 a[href]")
        stamp = art.select_one(".submitted [content]")
        if a is not None:
            add(a, stamp.get("content") if stamp else None)

    for row in main.select(".views-row"):
        a = row.select_one(f'a[href*="{post_path}"]')
        date_el = row.select_one(".date")
        if a is not None:
            add(a, _dmy_to_iso(date_el.get_text()) if date_el else None)

    nxt = main.select_one(".pager-next a[href]")
    return list(items.values()), (urljoin(page_url, nxt["href"]) if nxt else None)


def load_index(path: Path) -> dict[str, ListingItem]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {r["url"]: ListingItem(r["url"], r["title"], r["date"] or None,
                                      set(filter(None, r["sections"].split(";"))))
                for r in csv.DictReader(f)}


def save_index(index: dict[str, ListingItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dated = sorted((r for r in index.values() if r.date), key=lambda it: it.date, reverse=True)
    undated = sorted((r for r in index.values() if not r.date), key=lambda it: it.url)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for it in dated + undated:
            w.writerow({"url": it.url, "title": it.title, "date": it.date or "",
                        "sections": ";".join(sorted(it.sections))})


def merge(index: dict[str, ListingItem], items: list[ListingItem], section: str) -> int:
    """Add items to the index; return how many URLs were new."""
    new = 0
    for it in items:
        cur = index.get(it.url)
        if cur is None:
            it.sections.add(section)
            index[it.url] = it
            new += 1
        else:
            cur.sections.add(section)
            if not cur.date and it.date:
                cur.date = it.date
    return new


def crawl_sections(fetcher: PoliteFetcher, sections: list[str], out_csv: Path,
                   max_pages: int | None = None, refresh: bool = False,
                   post_path: str = POST_PATH, since: str | None = None) -> dict[str, ListingItem]:
    """since: ISO date; a section stops at the first page whose dated posts are all older."""
    index = load_index(out_csv)
    for section in sections:
        url: str | None = urljoin(fetcher.base_url, section.lstrip("/"))
        page = 0
        while url and (max_pages is None or page < max_pages):
            res = fetcher.get(url, refresh=refresh)
            if res.status != 200:
                log.warning("%s -> HTTP %d, stopping section %s", url, res.status, section)
                break
            items, url_next = parse_listing(res.text, url, post_path)
            dated = [it.date[:10] for it in items if it.date]
            too_old = bool(since) and bool(dated) and all(d < since for d in dated)
            if since:
                items = [it for it in items if not it.date or it.date[:10] >= since]
            new = merge(index, items, section)
            save_index(index, out_csv)
            log.info("%-32s page %3d: %2d posts (%2d new)%s  total %d", section, page,
                     len(items), new, " [cache]" if res.from_cache else "", len(index))
            if not items or too_old:
                break
            url, page = url_next, page + 1
    return index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Crawl ctsv.uit.edu.vn listing pages.")
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--sections", nargs="+", help="override the sections in the config")
    ap.add_argument("--max-pages", type=int, help="pages per section (for testing)")
    ap.add_argument("--refresh", action="store_true", help="ignore cached listing pages")
    ap.add_argument("--out", help="output CSV (default: paths.listing_index)")
    ap.add_argument("--since", help="YYYY-MM-DD: stop each section once posts are older (default: crawl.since)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    c, paths = cfg["crawl"], cfg["paths"]
    if "<your-email>" in c["user_agent"]:
        print("Set a contact email in crawl.user_agent in the config first.", file=sys.stderr)
        return 2

    fetcher = PoliteFetcher(c["base_url"], paths["raw_html"], c["user_agent"],
                            delay_s=c["crawl_delay_s"], timeout_s=c["timeout_s"],
                            max_retries=c["max_retries"])
    out = Path(args.out or paths["listing_index"])
    sections = args.sections or c["sections"]
    index = crawl_sections(fetcher, sections, out, args.max_pages, args.refresh,
                           c.get("post_path", POST_PATH), args.since or c.get("since"))
    n_dated = sum(1 for it in index.values() if it.date)
    print(f"{len(index)} posts ({n_dated} with a listing date) -> {out}; "
          f"{fetcher.n_requests} requests to the site")
    return 0


if __name__ == "__main__":
    sys.exit(main())
