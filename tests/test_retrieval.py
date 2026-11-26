from lumen.index.bm25 import BM25F
from lumen.index.boolean import BooleanIndex
from lumen.text.normalize import normalize_numbers, tokens

DOCS = [
    {"doc_id": "a", "date": "2026-01-01", "title": "Học bổng khuyến khích học tập HK1", "body": "danh sách"},
    {"doc_id": "b", "date": "2026-03-01", "title": "Học bổng Glao", "body": "học bổng học bổng học bổng"},
    {"doc_id": "c", "date": "2026-02-01", "title": "Điểm rèn luyện", "body": "học kỳ 1"},
]


def test_numbers_and_dates():
    assert normalize_numbers("1.487.000 đồng, hạn 1/9/2026") == "1487000 đồng, hạn 2026-09-01"


def test_stopwords_removed():
    assert tokens("Em cần nộp gì?", stop=True) == ["nop"]


def test_boolean_and_folding_and_date_order():
    idx = BooleanIndex(DOCS)
    assert idx.search("hoc bong") == ["b", "a"]            # no diacritics, newest first
    assert idx.search("học bổng glao") == ["b"]
    assert idx.search("học bổng xyz") == []                # AND: one unknown term kills it
    assert idx.search("em cần học bổng") == []             # stopwords break the AND (S0)
    assert idx.search("em cần học bổng", stop=True) == ["b", "a"]  # S0s: stopwords dropped


def test_bm25_ranks_and_title_boost():
    plain = BM25F(DOCS, {"title": 1.0, "body": 1.0})
    assert plain.search("học bổng")[0][0] == "b"           # more occurrences
    boosted = BM25F(DOCS, {"title": 5.0, "body": 1.0})
    assert [d for d, _ in boosted.search("khuyến khích")] == ["a"]
    assert plain.search("zzz") == []
