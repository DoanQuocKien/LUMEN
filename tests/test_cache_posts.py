import csv
import json

from lumen.corpus.cache import cache_key, cached_body, lookup
from lumen.corpus.posts import parse_cached_posts

URL = "https://ctsv.uit.edu.vn/bai-viet/a"


def _put(d, url, body: bytes, status=200):
    k = cache_key(url)
    (d / f"{k}.body").write_bytes(body)
    (d / f"{k}.json").write_text(json.dumps({"url": url, "status": status}), encoding="utf-8")


def test_cached_body_only_status_200(tmp_path):
    _put(tmp_path, URL, b"x")
    _put(tmp_path, URL + "2", b"x", status=403)
    _put(tmp_path, URL + "3", b"", status=0)
    assert cached_body(tmp_path, URL) is not None
    assert cached_body(tmp_path, URL + "2") is None and cached_body(tmp_path, URL + "3") is None
    assert cached_body(tmp_path, URL + "missing") is None


def test_lookup_tries_each_cache(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    _put(b, URL, b"x")
    assert lookup([a, b])(URL).parent == b and lookup([a])(URL) is None


def test_parse_cached_posts(tmp_path):
    cache = tmp_path / "html"
    cache.mkdir()
    _put(cache, URL, "<html><body><h1>Tiêu đề</h1><div class='field-name-body'>Nội dung bài.</div></body></html>".encode())
    _put(cache, URL + "-bad", b"", status=403)
    csv_p = tmp_path / "idx.csv"
    with open(csv_p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["url", "title", "date", "sections"])
        w.writeheader()
        w.writerow({"url": URL, "title": "t", "date": "2025-03-01", "sections": "/thong-bao;/quyet-dinh"})
        w.writerow({"url": URL + "-bad", "title": "t2", "date": "", "sections": ""})
    posts, missing = parse_cached_posts(csv_p, cache)
    assert missing == 1 and len(posts) == 1
    p = posts[0]
    assert p["title"] == "Tiêu đề" and p["date"] == "2025-03-01" and p["sections"] == ["/thong-bao", "/quyet-dinh"]
    assert "Nội dung" in p["body_text"]


def test_ocr_reads_pdf_from_body_cache(tmp_path, text_pdf):
    from lumen.ocr.engines import ocr_pdf  # pymupdf must open a '.body' file by content, not extension

    pdf_url = "https://ctsv.uit.edu.vn/sites/default/files/a.pdf"
    _put(tmp_path, pdf_url, text_pdf.read_bytes())
    pages = ocr_pdf(cached_body(tmp_path, pdf_url), "tesseract", tmp_path / "ocr")
    assert [p["source"] for p in pages] == ["text_layer", "text_layer"]
