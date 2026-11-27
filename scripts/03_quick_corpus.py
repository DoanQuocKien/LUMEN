"""Quick corpus for the W1 baselines (stand-in for W1-A3 + W2-A3 until the real parser exists).

Reads the cached ctsv + daa pages listed in post_status.jsonl and writes data/processed/docs.jsonl
(title from h1, date, body from .field-name-body, text of PDF attachments that have a text layer)
plus docs.manifest.json (counts, problems, SHA-256 of the inputs and of the output, so teammates
can check they evaluated the same corpus). Run from the repository root:
    python scripts/03_quick_corpus.py [--allow-partial]

Safety: the output is written to a temporary file and replaces docs.jsonl only after every site was
read successfully, so a failed rebuild leaves the previous corpus untouched. A post that the manifest
records as HTTP 200 but whose cached body is missing is an error (the document would silently drop out
of the evaluation); --allow-partial builds anyway and lists the missing URLs in the manifest.
PDF outcomes are kept apart: text, scan (opened, no usable text layer: needs OCR), parse_error (could not
be opened), missing (no cached file).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import pymupdf  # PyMuPDF
from bs4 import BeautifulSoup

SITES = [("data/raw", "ctsv"), ("data/raw/daa", "daa")]
MIN_CHARS = 50       # per page, same as ocr.min_chars_per_page in configs/default.yaml
MAX_PAGES = 60


def cached(html_dir: Path, url: str) -> bytes | None:
    p = html_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.body"
    return p.read_bytes() if p.exists() else None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_post(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("#block-system-main") or soup
    h1 = soup.select_one("h1")
    date = main.select_one(".submitted [content]")
    body = main.select_one(".field-name-body") or main.select_one("article")
    return {"title": h1.get_text(" ", strip=True) if h1 else "",
            "date": date["content"] if date else "",
            "body": body.get_text(" ", strip=True) if body else ""}


def pdf_text(data: bytes) -> dict:
    """Outcome of one PDF: status 'text' | 'scan' | 'parse_error', pages examined/total, text.

    Only the first MAX_PAGES pages are loaded. 'text' means at least half of the examined pages have
    MIN_CHARS or more characters."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            total = len(doc)
            n = min(total, MAX_PAGES)
            pages = [doc[i].get_text() for i in range(n)]
    except Exception:       # corrupt or encrypted file
        return {"status": "parse_error", "pages_examined": 0, "pages_total": 0, "text": ""}
    good = [t for t in pages if len(t.strip()) >= MIN_CHARS]
    ok = len(good) * 2 >= max(n, 1)
    return {"status": "text" if ok else "scan", "pages_examined": n, "pages_total": total,
            "text": "\n".join(good) if ok else ""}


def read_status(path: Path) -> list[dict]:
    """Last row per URL (post_status.jsonl is append-only, retried URLs appear more than once).
    A malformed line raises ValueError with the line number."""
    rows: dict[str, dict] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            rows[row["url"]] = row
        except (ValueError, KeyError) as exc:
            raise ValueError(f"{path}:{n}: bad status row ({exc})") from exc
    return list(rows.values())


def build(sites, out_path: Path, allow_partial: bool = False) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    stats: Counter = Counter()
    missing_html: list[str] = []
    inputs = {}
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as out:
            for base, site in sites:
                status_path = Path(base, "post_status.jsonl")
                inputs[site] = sha256(status_path)
                html_dir = Path(base) / "html"
                for row in read_status(status_path):
                    if row["status"] != 200:
                        stats["posts_failed_in_crawl"] += 1
                        continue
                    raw = cached(html_dir, row["url"])
                    if raw is None:
                        missing_html.append(f"{site} {row['url']}")
                        continue
                    doc = parse_post(raw.decode("utf-8", errors="replace"))
                    path = urlsplit(row["url"]).path.strip("/")
                    doc.update(doc_id=path if site == "ctsv" else f"daa/{path}", url=row["url"], attachments=[])
                    for a in row["attachments"]:
                        if a["status"] != 200 or not a["url"].lower().endswith(".pdf"):
                            continue        # images, Word and Excel need OCR/other extractors later
                        data = cached(html_dir, a["url"])
                        res = pdf_text(data) if data else {"status": "missing", "pages_examined": 0,
                                                           "pages_total": 0, "text": ""}
                        stats["pdf_" + res["status"]] += 1
                        doc["attachments"].append({"url": a["url"], "type": "pdf",
                                                   "has_text_layer": res["status"] == "text", **res})
                    out.write(json.dumps(doc, ensure_ascii=False) + "\n")
                    stats["docs"] += 1
        if missing_html and not allow_partial:
            raise RuntimeError(f"{len(missing_html)} posts recorded as HTTP 200 have no cached body "
                               f"(first: {missing_html[0]}); re-run the crawl or pass --allow-partial")
        os.replace(tmp, out_path)           # only now does the previous corpus disappear
    finally:
        tmp.unlink(missing_ok=True)
    manifest = {"docs": stats["docs"], "partial": bool(missing_html), "missing_html": missing_html,
                "counts": dict(stats), "status_sha256": inputs, "docs_sha256": sha256(out_path)}
    out_path.with_name("docs.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                                        encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/processed/docs.jsonl")
    ap.add_argument("--allow-partial", action="store_true", help="build even if some cached bodies are missing")
    a = ap.parse_args(argv)
    try:
        m = build(SITES, Path(a.out), a.allow_partial)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"build failed, previous corpus kept: {exc}", file=sys.stderr)
        return 1
    c = m["counts"]
    print(f"{m['docs']} docs -> {a.out}{' (PARTIAL: %d missing bodies)' % len(m['missing_html']) if m['partial'] else ''}")
    print(f"PDFs: {c.get('pdf_text', 0)} with text, {c.get('pdf_scan', 0)} scans (need OCR), "
          f"{c.get('pdf_parse_error', 0)} unreadable, {c.get('pdf_missing', 0)} missing from the cache")
    return 0


if __name__ == "__main__":
    sys.exit(main())
