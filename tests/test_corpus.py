import json

from lumen.corpus.build import build_corpus, make_passages, split_passages


def test_split_passages():
    text = " ".join(f"w{i}" for i in range(500))
    ps = split_passages(text, 200, 30)
    assert [len(p.split()) for p in ps] == [200, 200, 160]
    assert ps[1].split()[:30] == ps[0].split()[-30:]
    assert split_passages("a b c") == ["a b c"] and split_passages("") == []


def _post(i, title, body, atts=()):
    return {"url": f"https://ctsv.uit.edu.vn/bai-viet/p{i}", "title": title, "date": "2025-03-14",
            "body_text": body, "attachments": list(atts), "related": [], "external_links": []}


def test_build_corpus_end_to_end(tmp_path, text_pdf):
    posts = [_post(1, "Thông báo số 2 học bổng", "Nội dung " * 300),
             _post(2, "Quyết định", "", [{"url": "https://ctsv.uit.edu.vn/f/a.pdf", "name": "a.pdf", "ext": "pdf"}]),
             _post(3, "Thông báo số 2 học bổng", "Nội dung " * 300),  # exact duplicate of p1
             _post(4, "Mẫu đơn", "x", [{"url": "https://ctsv.uit.edu.vn/f/missing.pdf", "name": "m.pdf", "ext": "pdf"}])]
    pj = tmp_path / "posts.jsonl"
    pj.write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in posts), encoding="utf-8")
    fp = lambda u: text_pdf if u.endswith("a.pdf") else None  # noqa: E731
    args = (pj, tmp_path, tmp_path / "ocr", tmp_path / "docs.jsonl", tmp_path / "pass.jsonl", fp)
    res = build_corpus(*args)
    res2 = build_corpus(*args)
    assert res == res2 and res["docs"] == 4 and res["duplicates"] == 1
    docs = {json.loads(l)["url"][-2:]: json.loads(l) for l in (tmp_path / "docs.jsonl").read_text(encoding="utf-8").splitlines()}
    assert docs["p2"]["content_source"] == "pdf" and docs["p2"]["attachments"][0]["has_text_layer"] is True
    assert docs["p1"]["content_source"] == "html" and docs["p3"]["duplicate_of"] == docs["p1"]["doc_id"]
    assert docs["p4"]["attachments"][0]["status"] == "not_downloaded"
    assert docs["p1"]["meta"]["notice_seq"] == 2
    passages = [json.loads(l) for l in (tmp_path / "pass.jsonl").read_text(encoding="utf-8").splitlines()]
    assert not any(p["doc_id"] == docs["p3"]["doc_id"] for p in passages)
    assert sum(1 for p in passages if p["field"] == "title" and p["doc_id"] == docs["p1"]["doc_id"]) == 1
    assert any(p["source"] == "pdf" for p in passages)
