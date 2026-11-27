"""Corpus statistics for the W2 milestone: posts, % with PDFs, % scanned, OCR time. [W2]"""
from __future__ import annotations

import json
from pathlib import Path

from lumen.text.pii import has_mssv


def corpus_stats(docs_jsonl: str | Path, ocr_dir: str | Path | None = None) -> dict:
    docs = [json.loads(ln) for ln in Path(docs_jsonl).read_text(encoding="utf-8").splitlines() if ln.strip()]
    n = len(docs) or 1
    pdfs = [a for d in docs for a in d["attachments"] if a["ext"] == "pdf"]
    got = [a for a in pdfs if a["status"] in ("ok", "partial", "failed")]
    scanned = [a for a in got if a["ocr_engine"]]
    ocr_seconds, ocr_pages, failed_pages = 0.0, 0, 0
    if ocr_dir and Path(ocr_dir).exists():
        for f in Path(ocr_dir).rglob("p*.json"):
            r = json.loads(f.read_text(encoding="utf-8"))
            ocr_pages += 1
            ocr_seconds += r.get("seconds", 0.0)
            failed_pages += r.get("status") == "failed"
    confs = [a["ocr_conf"] for a in scanned if a["ocr_conf"] is not None]
    return {
        "posts": len(docs),
        "duplicates": sum(1 for d in docs if d["duplicate_of"]),
        "posts_with_pdf_pct": round(100 * sum(1 for d in docs if any(a["ext"] == "pdf" for a in d["attachments"])) / n, 1),
        "pdfs_listed": len(pdfs),
        "pdfs_downloaded": len(got),
        "pdfs_scanned_pct": round(100 * len(scanned) / len(got), 1) if got else None,
        "content_source": {k: sum(1 for d in docs if d["content_source"] == k) for k in ("html", "pdf", "both")},
        "ocr_pages": ocr_pages,
        "ocr_hours": round(ocr_seconds / 3600, 2),
        "ocr_failed_pages": failed_pages,
        "ocr_mean_conf": round(sum(confs) / len(confs), 1) if confs else None,
        "docs_with_mssv_like_ids": sum(1 for d in docs if has_mssv(d["body"] + " ".join(a["text"] for a in d["attachments"]))),
    }
