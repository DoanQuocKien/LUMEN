"""OCR bake-off helpers: sample scanned PDFs, compute CER/WER, time per page. [W1-A4]

Workflow (see scripts/ocr_bakeoff.py):
  1. `sample`  picks 15 scanned PDFs (fixed seed) and creates empty reference files for 3 pages.
  2. You hand-transcribe those 3 reference pages (data/interim/bakeoff/refs/*.txt).
  3. `run`     OCRs the sampled pages with every engine and writes results.csv + summary.csv.
"""
from __future__ import annotations

import csv
import json
import random
import time
import unicodedata
from pathlib import Path

import pymupdf

from lumen.ocr.detect import analyze_pdf
from lumen.ocr.engines import render_page


def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).split())


def edit_distance(a, b) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    r, h = _norm(ref), _norm(hyp)
    return edit_distance(r, h) / max(1, len(r))


def wer(ref: str, hyp: str) -> float:
    r, h = _norm(ref).split(), _norm(hyp).split()
    return edit_distance(r, h) / max(1, len(r))


def sample_scanned(pdf_dir: str | Path, out_dir: str | Path, n_pdfs: int = 15, n_ref_pages: int = 3,
                   seed: int = 0, min_chars: int = 50) -> dict:
    scanned = []
    for p in sorted(Path(pdf_dir).rglob("*.pdf")):
        info = analyze_pdf(p, min_chars)
        if info["route"] == "ocr":
            scanned.append((p, info["n_pages"]))
    rng = random.Random(seed)
    pick = rng.sample(scanned, min(n_pdfs, len(scanned)))
    items = [{"pdf": str(p), "page": 0} for p, _ in pick]  # first page of each: the one with stamps/tables
    ref_items = items[:n_ref_pages]
    out = Path(out_dir)
    (out / "refs").mkdir(parents=True, exist_ok=True)
    for it in ref_items:
        ref = out / "refs" / f"{Path(it['pdf']).stem}_p{it['page'] + 1}.txt"
        it["ref"] = str(ref)
        ref.touch(exist_ok=True)
    (out / "sample.json").write_text(json.dumps({"n_scanned_found": len(scanned), "items": items},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    return {"n_scanned_found": len(scanned), "items": items}


def run_bakeoff(items: list[dict], engines: dict, out_dir: str | Path, dpi: int = 300) -> list[dict]:
    rows = []
    for it in items:
        with pymupdf.open(it["pdf"]) as doc:
            img = render_page(doc, it["page"], dpi)
        ref = None
        if it.get("ref") and Path(it["ref"]).exists() and Path(it["ref"]).read_text(encoding="utf-8").strip():
            ref = Path(it["ref"]).read_text(encoding="utf-8")
        for name, eng in engines.items():
            t0 = time.perf_counter()
            try:
                text, conf = eng.recognize(img)
                err = ""
            except Exception as e:
                text, conf, err = "", None, f"{type(e).__name__}: {e}"
            sec = time.perf_counter() - t0
            rows.append({"pdf": Path(it["pdf"]).name, "page": it["page"] + 1, "engine": name,
                         "seconds": round(sec, 2), "conf": conf, "chars": len(text),
                         "cer": round(cer(ref, text), 4) if ref else "",
                         "wer": round(wer(ref, text), 4) if ref else "", "error": err})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "results.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["pdf"])
        w.writeheader()
        w.writerows(rows)
    summ = []
    for name in engines:
        rs = [r for r in rows if r["engine"] == name and not r["error"]]
        ref_rs = [r for r in rs if r["cer"] != ""]
        summ.append({"engine": name, "pages": len(rs), "errors": sum(1 for r in rows if r["engine"] == name and r["error"]),
                     "sec_per_page": round(sum(r["seconds"] for r in rs) / len(rs), 2) if rs else "",
                     "mean_cer": round(sum(r["cer"] for r in ref_rs) / len(ref_rs), 4) if ref_rs else "",
                     "mean_wer": round(sum(r["wer"] for r in ref_rs) / len(ref_rs), 4) if ref_rs else "",
                     "ref_pages": len(ref_rs)})
    with open(out / "summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0]) if summ else ["engine"])
        w.writeheader()
        w.writerows(summ)
    return summ
