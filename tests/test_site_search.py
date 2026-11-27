from lumen.eval.site_search import Matcher, VARIANTS, assess, check, kendall_tau, p01_order, tok

DOCS = [  # P77 in miniature: a table with row numbers 24 and 11, and a post that writes the holiday date
    {"doc_id": "table", "date": "2025-11-08", "title": "Danh sách", "body": "24 quả lê 11 đề nghị có được trường không 2025-2026"},
    {"doc_id": "holiday", "date": "2023-03-01", "title": "Nghỉ lễ", "body": "trường có được nghỉ lễ 24/11 không"},
]


def test_d7_tokens():
    assert tok("24/11/2025", "d7") == ["24112025"]
    assert tok("24/11") == ["24", "11"]                       # S0 splits
    assert tok("ĐHQG-HCM", "d7") == ["dhqghcm"]
    assert tok("ĐHQG-HCM", "d7", "keep_d") == ["đhqghcm"]
    assert tok("a--b", "d7") == ["a", "b"]                     # 2+ dashes are a word break


def test_number_joining_explains_p77():
    q = "trường 24/11 có được lễ nghỉ không"
    assert Matcher(DOCS, *VARIANTS["S0 (AND, title+body)"]).hits(q) == ["table", "holiday"]
    assert Matcher(DOCS, *VARIANTS["D7 model (d7 tokens, đ=d)"]).hits(q) == ["holiday"]
    assert Matcher(DOCS, *VARIANTS["phrase (consecutive)"]).hits("nghỉ lễ 24/11") == ["holiday"]


def test_check_and_tau():
    assert (check(3, "1"), check(1, "1"), check(5, "many"), check(0, "")) == ("over", "ok", "n/a", "n/a")
    assert kendall_tau(list("abc"), list("abc")) == 1 and kendall_tau(list("cba"), list("abc")) == -1


def test_assess_counts_assessable_and_unassessable_rows_apart():
    rows = [{"qid": "A", "ctsv": "2"}, {"qid": "B", "ctsv": "many"}, {"qid": "C", "ctsv": "1"}]
    a = assess(rows, {"A": 0, "B": 0, "C": 3})
    assert a == {"ok": ["A"], "over": ["C"], "na": ["B"]}           # B is not credited as consistent
    assert sum(len(v) for v in a.values()) == len(rows)


def test_p01_order_is_deterministic_with_tied_scores(monkeypatch):
    import lumen.eval.site_search as ss
    ids = sorted(ss.KNOWN["P01"])
    docs = {i: {"doc_id": i, "date": d, "title": "học bổng", "body": "học bổng"}
            for i, d in zip(ids, ss.P01_SITE_DATES)}
    monkeypatch.setattr(ss, "d7_scores", lambda ctsv, q: {i: 1.0 for i in ids})      # every score tied
    monkeypatch.setattr(ss, "tfidf_scores", lambda ctsv, q, field="body": {i: 1.0 for i in ids})
    rows = {name: dates for name, dates, _ in p01_order(list(docs.values()), docs)}
    assert rows["D7 relevance (title x26)"] == ss.P01_SITE_DATES   # ties broken by doc_id
