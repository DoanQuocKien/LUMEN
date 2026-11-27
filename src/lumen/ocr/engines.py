"""OCR engine wrappers (Tesseract vie, PaddleOCR, VietOCR) with a per-page cache. [W1-A4, W2-A1]

Only the Tesseract wrapper is tested (tests/test_ocr.py). PaddleOCR and VietOCR wrappers are
written against their public APIs but could not be run where this was written; if the API
differs in your installed version, fix `recognize()` only: the rest of the pipeline just
needs (text, confidence 0-100 or None).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

from lumen.ocr.detect import analyze_pdf, extract_text_layer


# ---- engines ---------------------------------------------------------------------------
class TesseractEngine:
    name = "tesseract"

    def __init__(self, lang: str = "vie", psm: int = 6):
        import pytesseract

        self.pt, self.lang, self.psm = pytesseract, lang, psm

    def recognize(self, img: Image.Image) -> tuple[str, float | None]:
        d = self.pt.image_to_data(img, lang=self.lang, config=f"--psm {self.psm}", output_type=self.pt.Output.DICT)
        words, confs, lines = [], [], {}
        for txt, conf, b, p, ln in zip(d["text"], d["conf"], d["block_num"], d["par_num"], d["line_num"]):
            if not txt.strip():
                continue
            lines.setdefault((b, p, ln), []).append(txt)
            if float(conf) >= 0:
                confs.append(float(conf))
        text = "\n".join(" ".join(w) for _, w in sorted(lines.items()))
        return text, (float(np.mean(confs)) if confs else None)


class PaddleEngine:
    """PaddleOCR with the Vietnamese recognizer (`lang='vi'`). UNTESTED here."""

    name = "paddleocr"

    def __init__(self, lang: str = "vi"):
        from paddleocr import PaddleOCR

        self.ocr = PaddleOCR(lang=lang)

    def recognize(self, img: Image.Image) -> tuple[str, float | None]:
        arr = np.array(img.convert("RGB"))
        res = self.ocr.predict(arr) if hasattr(self.ocr, "predict") else self.ocr.ocr(arr)
        texts, scores = [], []
        for page in res or []:
            if isinstance(page, dict):  # PaddleOCR 3.x
                texts += list(page.get("rec_texts", []))
                scores += [float(s) for s in page.get("rec_scores", [])]
            else:  # PaddleOCR 2.x: [[box, (text, score)], ...]
                for item in page or []:
                    texts.append(item[1][0])
                    scores.append(float(item[1][1]))
        return "\n".join(texts), (100 * float(np.mean(scores)) if scores else None)


class VietOcrEngine:
    """VietOCR recognizer with Tesseract line boxes as the detector. UNTESTED here."""

    name = "vietocr"

    def __init__(self, config_name: str = "vgg_transformer", det_lang: str = "vie", device: str = "cpu"):
        import pytesseract
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        cfg = Cfg.load_config_from_name(config_name)
        cfg["device"] = device
        cfg["predictor"]["beamsearch"] = False
        self.pred, self.pt, self.det_lang = Predictor(cfg), pytesseract, det_lang

    def recognize(self, img: Image.Image) -> tuple[str, float | None]:
        d = self.pt.image_to_data(img, lang=self.det_lang, config="--psm 6", output_type=self.pt.Output.DICT)
        boxes: dict[tuple, list[int]] = {}
        for i, txt in enumerate(d["text"]):
            if not txt.strip():
                continue
            k = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            x0, y0, x1, y1 = d["left"][i], d["top"][i], d["left"][i] + d["width"][i], d["top"][i] + d["height"][i]
            b = boxes.setdefault(k, [x0, y0, x1, y1])
            b[:] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)]
        lines = [self.pred.predict(img.crop(tuple(b)).convert("RGB")) for _, b in sorted(boxes.items())]
        return "\n".join(lines), None  # VietOCR gives no per-line confidence


def make_engine(name: str, lang: str = "vie"):
    if name == "tesseract":
        return TesseractEngine(lang=lang)
    if name == "paddleocr":
        return PaddleEngine()
    if name == "vietocr":
        return VietOcrEngine(det_lang=lang)
    raise ValueError(f"unknown OCR engine: {name}")


# ---- image helpers ---------------------------------------------------------------------
def render_page(doc: pymupdf.Document, index: int, dpi: int = 300) -> Image.Image:
    pix = doc[index].get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def estimate_skew(img: Image.Image, max_angle: float = 5.0, step: float = 0.5) -> float:
    """Projection-profile skew estimate in degrees (positive = rotate image clockwise to fix)."""
    g = img.convert("L")
    g = g.resize((800, max(1, round(g.height * 800 / g.width))))
    best, best_var = 0.0, -1.0
    for a in np.arange(-max_angle, max_angle + 1e-9, step):
        r = g.rotate(float(a), resample=Image.BILINEAR, fillcolor=255)
        v = float(np.var((np.asarray(r) < 128).sum(axis=1)))
        if v > best_var:
            best, best_var = float(a), v
    return best


def deskew(img: Image.Image) -> tuple[Image.Image, float]:
    a = estimate_skew(img)
    if abs(a) < 0.5:
        return img, 0.0
    return img.rotate(a, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)), a


def recognize_with_fallback(engine, img: Image.Image, low_conf: float = 60.0) -> dict:
    """Run OCR; if confidence is low, retry with deskew and 90/180/270 rotations, keep the best."""
    t0 = time.perf_counter()
    text, conf = engine.recognize(img)
    best = {"text": text, "conf": conf, "rotation": 0, "deskew": 0.0}
    if conf is not None and conf < low_conf:
        cands = []
        d_img, angle = deskew(img)
        if angle:
            cands.append((d_img, 0, angle))
        cands += [(img.rotate(-r, expand=True, fillcolor=(255, 255, 255)), r, 0.0) for r in (90, 180, 270)]
        for c_img, rot, ang in cands:
            t, c = engine.recognize(c_img)
            if c is not None and c > (best["conf"] or 0):
                best = {"text": t, "conf": c, "rotation": rot, "deskew": ang}
    best["seconds"] = round(time.perf_counter() - t0, 3)
    return best


# ---- per-page cached OCR of a whole PDF ------------------------------------------------
def pdf_key(path: str | Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def ocr_pdf(path: str | Path, engine, cache_dir: str | Path, dpi: int = 300, min_chars: int = 50,
            low_conf: float = 60.0, cache_only: bool = False, retry_failed: bool = False,
            lang: str = "vie") -> list[dict]:
    """Per-page results: {page, source: text_layer|ocr, status: ok|failed|missing, text, conf,
    engine, seconds, rotation, deskew}. OCR results are cached per page under
    cache_dir/<pdf sha1>/pNNNN.<engine>.<lang>.json so reruns are free."""
    ename = engine if isinstance(engine, str) else getattr(engine, "name", None)
    if isinstance(engine, str):  # name only -> read-only access to the cache
        engine, cache_only = None, True
    info = analyze_pdf(path, min_chars)
    if info["route"] == "error":
        return [{"page": 0, "source": "none", "status": "failed", "text": "", "conf": None,
                 "engine": None, "seconds": 0.0, "error": info["error"]}]
    layer = extract_text_layer(path, info["text_pages"]) if info["text_pages"] else {}
    out: list[dict] = []
    cdir = Path(cache_dir) / pdf_key(path)
    doc = None
    try:
        for i in range(info["n_pages"]):
            if i in layer:
                out.append({"page": i, "source": "text_layer", "status": "ok", "text": layer[i],
                            "conf": None, "engine": None, "seconds": 0.0})
                continue
            f = cdir / f"p{i + 1:04d}.{ename}.{lang}.json"
            if f.exists():
                rec = json.loads(f.read_text(encoding="utf-8"))
                if rec["status"] == "ok" or not retry_failed:
                    out.append(rec)
                    continue
            if cache_only or engine is None:
                out.append({"page": i, "source": "ocr", "status": "missing", "text": "", "conf": None,
                            "engine": ename, "seconds": 0.0})
                continue
            doc = doc or pymupdf.open(str(path))
            try:
                r = recognize_with_fallback(engine, render_page(doc, i, dpi), low_conf)
                rec = {"page": i, "source": "ocr", "status": "ok", "engine": engine.name, **r}
            except Exception as e:
                rec = {"page": i, "source": "ocr", "status": "failed", "text": "", "conf": None,
                       "engine": engine.name, "seconds": 0.0, "error": f"{type(e).__name__}: {e}"}
            cdir.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            out.append(rec)
    finally:
        if doc is not None:
            doc.close()
    return out
