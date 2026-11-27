"""Build docs.jsonl and passages.jsonl from parsed posts + cached OCR. [W2-A3]

Input  data/interim/posts.jsonl (from scripts/03_parse.py).
Output data/processed/docs.jsonl, passages.jsonl (gitignored: may contain personal data).
Deterministic: sorted by URL, ids are hashes of the URL, so reruns give identical files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lumen.meta.extract import body_fingerprint, extract_meta, series_key
from lumen.ocr.engines import ocr_pdf
from lumen.text.normalize import normalize


def split_passages(text: str, size: int = 200, overlap: int = 30) -> list[str]:
    """Windows of `size` syllables (whitespace tokens: one Vietnamese syllable each) with `overlap`."""
    toks = text.split()
    if not toks:
        return []
    if len(toks) <= size:
        return [" ".join(toks)]
    step = max(1, size - overlap)
    out = []
    for start in range(0, len(toks), step):
        out.append(" ".join(toks[start:start + size]))
        if start + size >= len(toks):
            break
    return out


def doc_id_for(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def build_doc(post: dict, attach_dir: Path, ocr_dir: Path, engine_name: str, lang: str,
              min_chars: int, fetch_path) -> dict:
    """One docs.jsonl record. `fetch_path(url)` maps an attachment URL to its local file (or None)."""
    atts, pdf_texts = [], []
    for a in post.get("attachments", []):
        rec = {"url": a["url"], "name": a["name"], "ext": a["ext"], "has_text_layer": None,
               "ocr_engine": None, "ocr_conf": None, "n_pages": None, "status": "not_pdf", "text": ""}
        local = fetch_path(a["url"]) if a["ext"] == "pdf" else None
        if a["ext"] == "pdf" and local is None:
            rec["status"] = "not_downloaded"
        elif local is not None:
            pages = ocr_pdf(local, engine_name, ocr_dir, min_chars=min_chars, lang=lang)
            used_ocr = [p for p in pages if p["source"] == "ocr"]
            confs = [p["conf"] for p in used_ocr if p.get("conf") is not None]
            rec.update({
                "n_pages": len(pages),
                "has_text_layer": any(p["source"] == "text_layer" for p in pages),
                "ocr_engine": engine_name if used_ocr else None,
                "ocr_conf": round(sum(confs) / len(confs), 1) if confs else None,
                "text": "\n".join(p["text"] for p in pages if p["status"] == "ok").strip(),
            })
            bad = [p for p in pages if p["status"] != "ok"]
            rec["status"] = "ok" if not bad else ("failed" if len(bad) == len(pages) else "partial")
            rec["pages_missing_or_failed"] = [p["page"] + 1 for p in bad]
            pdf_texts.append(rec["text"])
        atts.append(rec)
    body = post.get("body_text", "")
    has_pdf = any(t for t in pdf_texts)
    meta = extract_meta(post.get("title", ""), body, "\n".join(pdf_texts))
    return {
        "doc_id": doc_id_for(post["url"]),
        "url": post["url"],
        "title": post.get("title", ""),
        "date": post.get("date"),
        "body": body,
        "attachments": atts,
        "content_source": "both" if (body and has_pdf) else ("pdf" if has_pdf else "html"),
        "meta": meta,
        "series_id": series_key(post.get("title", ""), meta["doc_type"]),
        "fingerprint": body_fingerprint(body + "\n" + "\n".join(pdf_texts)),
        "duplicate_of": None,
    }


def mark_duplicates(docs: list[dict]) -> None:
    seen: dict[tuple, str] = {}
    for d in docs:
        key = (d["fingerprint"],) if len(d["body"]) + sum(len(a["text"]) for a in d["attachments"]) > 80 else (d["series_id"], d["date"], normalize(d["title"]))
        if key in seen:
            d["duplicate_of"] = seen[key]
        else:
            seen[key] = d["doc_id"]


def make_passages(doc: dict, size: int, overlap: int) -> list[dict]:
    out = []

    def add(field, text, source, att=None):
        out.append({"doc_id": doc["doc_id"], "field": field, "source": source, "attachment": att, "text": text,
                    "n_syllables": len(text.split())})

    if doc["title"]:
        add("title", doc["title"], "html")  # each title is its own passage
    for t in split_passages(doc["body"], size, overlap):
        add("body", t, "html")
    for i, a in enumerate(doc["attachments"]):
        for t in split_passages(a["text"], size, overlap):
            add("attachment", t, "pdf", i)
    for n, p in enumerate(out):
        p["passage_id"] = f"{doc['doc_id']}-{n:03d}"
    return out


def build_corpus(posts_jsonl: str | Path, attach_dir: str | Path, ocr_dir: str | Path, docs_out: str | Path,
                 passages_out: str | Path, fetch_path, engine_name: str = "tesseract", lang: str = "vie",
                 min_chars: int = 50, size: int = 200, overlap: int = 30) -> dict:
    posts = [json.loads(ln) for ln in Path(posts_jsonl).read_text(encoding="utf-8").splitlines() if ln.strip()]
    posts.sort(key=lambda p: p["url"])
    docs = [build_doc(p, Path(attach_dir), Path(ocr_dir), engine_name, lang, min_chars, fetch_path) for p in posts]
    mark_duplicates(docs)
    Path(docs_out).parent.mkdir(parents=True, exist_ok=True)
    n_pass = 0
    with open(docs_out, "w", encoding="utf-8") as fd, open(passages_out, "w", encoding="utf-8") as fp:
        for d in docs:
            fd.write(json.dumps(d, ensure_ascii=False) + "\n")
            if d["duplicate_of"]:
                continue  # duplicates stay in docs.jsonl but are not indexed
            for p in make_passages(d, size, overlap):
                fp.write(json.dumps(p, ensure_ascii=False) + "\n")
                n_pass += 1
    return {"docs": len(docs), "duplicates": sum(1 for d in docs if d["duplicate_of"]), "passages": n_pass}
