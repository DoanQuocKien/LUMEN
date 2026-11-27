import hashlib
import importlib.util
import json
from pathlib import Path

import pymupdf
import pytest

spec = importlib.util.spec_from_file_location("quick_corpus", Path(__file__).parents[1] / "scripts" / "03_quick_corpus.py")
qc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qc)

POST = ('<html><body><h1>Thong bao A</h1><div id="block-system-main"><article>'
        '<div class="submitted"><span content="2026-11-19T15:02:02+07:00"></span></div>'
        '<div class="field-name-body">Noi dung bai viet</div></article></div></body></html>')


def pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for t in pages:
        doc.new_page().insert_text((72, 72), t)
    return doc.tobytes()


def put(html_dir: Path, url: str, data: bytes) -> None:
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.body").write_bytes(data)


def site(tmp_path, name, rows, bodies):
    base = tmp_path / name
    (base / "html").mkdir(parents=True)
    (base / "post_status.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    for url, data in bodies.items():
        put(base / "html", url, data)
    return str(base)


def row(url, atts=(), status=200):
    return {"url": url, "status": status, "attachments": [{"url": u, "status": 200, "bytes": 1} for u in atts]}


LONG = "x" * 80


def test_pdf_outcomes_are_counted_apart(tmp_path):
    u = "https://ctsv.example/bai-viet/a"
    atts = [f"https://ctsv.example/f/{n}.pdf" for n in ("text", "scan", "bad", "gone")]
    base = site(tmp_path, "ctsv", [row(u, atts)], {
        u: POST.encode(), atts[0]: pdf([LONG]), atts[1]: pdf([""]), atts[2]: b"not a pdf"})
    m = qc.build([(base, "ctsv")], tmp_path / "out" / "docs.jsonl")
    assert m["counts"] == {"docs": 1, "pdf_text": 1, "pdf_scan": 1, "pdf_parse_error": 1, "pdf_missing": 1}
    doc = json.loads((tmp_path / "out" / "docs.jsonl").read_text(encoding="utf-8"))
    assert doc["title"] == "Thong bao A" and doc["date"].startswith("2026-11-19") and doc["doc_id"] == "bai-viet/a"
    assert [a["status"] for a in doc["attachments"]] == ["text", "scan", "parse_error", "missing"]


def test_only_max_pages_are_examined(tmp_path, monkeypatch):
    monkeypatch.setattr(qc, "MAX_PAGES", 2)
    res = qc.pdf_text(pdf([LONG] * 5))
    assert (res["pages_examined"], res["pages_total"], res["status"]) == (2, 5, "text")


def test_missing_body_fails_and_keeps_previous_corpus(tmp_path):
    out = tmp_path / "docs.jsonl"
    out.write_bytes(b"previous corpus\n")
    u = "https://ctsv.example/bai-viet/a"
    base = site(tmp_path, "ctsv", [row(u)], {})                       # HTTP 200 in the manifest, no cached body
    with pytest.raises(RuntimeError, match="no cached body"):
        qc.build([(base, "ctsv")], out)
    assert out.read_bytes() == b"previous corpus\n" and not list(tmp_path.glob("*.tmp"))
    m = qc.build([(base, "ctsv")], out, allow_partial=True)
    assert m["partial"] and m["missing_html"] == [f"ctsv {u}"] and m["docs"] == 0


def test_malformed_second_manifest_keeps_previous_corpus(tmp_path):
    out = tmp_path / "docs.jsonl"
    out.write_bytes(b"previous corpus\n")
    u = "https://ctsv.example/bai-viet/a"
    ok = site(tmp_path, "ctsv", [row(u)], {u: POST.encode()})
    bad = tmp_path / "daa"
    bad.mkdir()
    (bad / "post_status.jsonl").write_text('{"url": "https://daa.example/x"\n', encoding="utf-8")   # truncated line
    with pytest.raises(ValueError, match="post_status.jsonl:1"):
        qc.build([(ok, "ctsv"), (str(bad), "daa")], out)
    assert out.read_bytes() == b"previous corpus\n"


def test_last_status_row_per_url_wins(tmp_path):
    u = "https://ctsv.example/bai-viet/a"
    base = site(tmp_path, "ctsv", [row(u, status=403), row(u)], {u: POST.encode()})
    m = qc.build([(base, "ctsv")], tmp_path / "docs.jsonl")
    assert m["docs"] == 1 and "posts_failed_in_crawl" not in m["counts"]
    assert m["docs_sha256"] == qc.sha256(tmp_path / "docs.jsonl")
