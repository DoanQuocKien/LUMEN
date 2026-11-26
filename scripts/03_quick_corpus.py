"""Quick corpus for the W1 baselines (stand-in for W1-A3 + W2-A3 until the real parser exists).

Reads the cached ctsv + daa pages listed in post_status.jsonl and writes data/processed/docs.jsonl:
title (h1), date, body (.field-name-body), and text from PDF attachments that have a text layer.
Scanned PDFs get empty text (OCR is W1-A4). Run from the repository root:
    python scripts/03_quick_corpus.py
"""
import hashlib
import json
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


def parse_post(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("#block-system-main") or soup
    h1 = soup.select_one("h1")
    date = main.select_one(".submitted [content]")
    body = main.select_one(".field-name-body") or main.select_one("article")
    return {"title": h1.get_text(" ", strip=True) if h1 else "",
            "date": date["content"] if date else "",
            "body": body.get_text(" ", strip=True) if body else ""}


def pdf_text(data: bytes) -> tuple[bool, str]:
    """(has_text_layer, text). A PDF counts as scanned when most pages have < MIN_CHARS characters."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pages = [p.get_text() for p in list(doc)[:MAX_PAGES]]
    except Exception:       # corrupt or encrypted file
        return False, ""
    good = [t for t in pages if len(t.strip()) >= MIN_CHARS]
    return len(good) * 2 >= max(len(pages), 1), "\n".join(good)


def main() -> None:
    out_path = Path("data/processed/docs.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = scanned = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        for base, site in SITES:
            html_dir = Path(base) / "html"
            for line in Path(base, "post_status.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                raw = cached(html_dir, row["url"]) if row["status"] == 200 else None
                if raw is None:
                    continue
                doc = parse_post(raw.decode("utf-8", errors="replace"))
                path = urlsplit(row["url"]).path.strip("/")
                doc.update(doc_id=path if site == "ctsv" else f"daa/{path}", url=row["url"], attachments=[])
                for a in row["attachments"]:
                    if a["status"] != 200 or not a["url"].lower().endswith(".pdf"):
                        continue        # images, Word and Excel need OCR/other extractors later
                    data = cached(html_dir, a["url"])
                    layer, text = pdf_text(data) if data else (False, "")
                    scanned += not layer
                    doc["attachments"].append({"url": a["url"], "type": "pdf", "has_text_layer": layer, "text": text})
                out.write(json.dumps(doc, ensure_ascii=False) + "\n")
                n += 1
    print(f"{n} docs -> {out_path}; {scanned} PDFs without a usable text layer")


if __name__ == "__main__":
    main()
