import shutil

import pytest

from lumen.ocr.bakeoff import cer, wer
from lumen.ocr.engines import TesseractEngine, estimate_skew, ocr_pdf


def test_cer_wer():
    assert cer("học bổng", "học bổng") == 0
    assert cer("abcd", "abxd") == 0.25
    assert wer("a b c d", "a x c d") == 0.25


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_ocr_pdf_cache_and_text_layer(scanned_pdf, mixed_pdf, tmp_path):
    eng = TesseractEngine(lang="eng")
    cache = tmp_path / "ocr"
    pages = ocr_pdf(scanned_pdf, eng, cache, dpi=200, lang="eng")
    assert pages[0]["source"] == "ocr" and pages[0]["status"] == "ok"
    assert "Scholarship" in pages[0]["text"] and pages[0]["conf"] > 50

    class Boom:  # a cache hit must not call the engine again
        name = "tesseract"

        def recognize(self, img):
            raise AssertionError("engine called on cached page")

    again = ocr_pdf(scanned_pdf, Boom(), cache, dpi=200, lang="eng")
    assert again[0]["text"] == pages[0]["text"]
    # read-only access by engine name (used when building the corpus)
    assert ocr_pdf(scanned_pdf, "tesseract", cache, lang="eng")[0]["status"] == "ok"
    assert ocr_pdf(scanned_pdf, "tesseract", tmp_path / "empty", lang="eng")[0]["status"] == "missing"
    mixed = ocr_pdf(mixed_pdf, eng, cache, dpi=200, lang="eng")
    assert [p["source"] for p in mixed] == ["text_layer", "ocr"]


def test_skew_estimate_is_zero_for_straight_text(scanned_pdf):
    import pymupdf
    from lumen.ocr.engines import render_page
    with pymupdf.open(str(scanned_pdf)) as d:
        assert abs(estimate_skew(render_page(d, 0, 100))) <= 1.0
