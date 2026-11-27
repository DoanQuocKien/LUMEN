"""Detect whether a PDF has a usable text layer (PyMuPDF characters per page). [W1-A5]

A page counts as 'text' when it has at least `min_chars` non-space characters and most of
them look like real text (letters/digits/punctuation). Pages below that are 'scanned' and
go to OCR. Routing is per page, so mixed PDFs work.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf


def _looks_like_text(s: str) -> bool:
    chars = [c for c in s if not c.isspace()]
    if not chars:
        return False
    good = sum(1 for c in chars if c.isalnum() or c in ".,;:()-/%\"'“”–—+&@#!?")
    return good / len(chars) >= 0.8


def analyze_pdf(path: str | Path, min_chars: int = 50) -> dict:
    """Return {n_pages, chars, text_pages, scanned_pages, text_fraction, route, error}.

    route: 'text' (all pages text) | 'ocr' (no page has text) | 'mixed' | 'empty' | 'error'.
    """
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:  # corrupt / encrypted / not a PDF
        return {"n_pages": 0, "chars": [], "text_pages": [], "scanned_pages": [],
                "text_fraction": 0.0, "route": "error", "error": f"{type(e).__name__}: {e}"}
    with doc:
        if doc.needs_pass:
            return {"n_pages": doc.page_count, "chars": [], "text_pages": [], "scanned_pages": [],
                    "text_fraction": 0.0, "route": "error", "error": "encrypted"}
        chars, text_pages, scanned = [], [], []
        for i, page in enumerate(doc):
            t = page.get_text("text")
            n = sum(1 for c in t if not c.isspace())
            chars.append(n)
            (text_pages if n >= min_chars and _looks_like_text(t) else scanned).append(i)
        n_pages = doc.page_count
    if n_pages == 0:
        route = "empty"
    elif not scanned:
        route = "text"
    elif not text_pages:
        route = "ocr"
    else:
        route = "mixed"
    return {"n_pages": n_pages, "chars": chars, "text_pages": text_pages, "scanned_pages": scanned,
            "text_fraction": len(text_pages) / n_pages if n_pages else 0.0, "route": route, "error": None}


def extract_text_layer(path: str | Path, pages: list[int] | None = None) -> dict[int, str]:
    """Text of the given pages (default all) straight from the PDF text layer."""
    out: dict[int, str] = {}
    with pymupdf.open(str(path)) as doc:
        for i in pages if pages is not None else range(doc.page_count):
            out[i] = doc[i].get_text("text").strip()
    return out
