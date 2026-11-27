"""Local hypothesis tests for the sites' built-in search (W1-C2). No network: never queries either site.

Scores variants of S0 (field set, AND/OR, tokenisation, folding, ...) against the hand-typed
observations, and predicts S0 / D7-model counts for the hand-test protocol. See docs/search_experiments.md.

    python -m lumen.eval.site_search --docs <docs.jsonl>                    # variant table + P01 order
    python -m lumen.eval.site_search --docs <docs.jsonl> --predict data/eval/site_search_protocol.tsv
"""
import argparse
import csv
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from lumen.retrieve.systems import load_docs
from lumen.text.normalize import STOPWORDS, normalize_numbers

_WORD = re.compile(r"\w+")
# Drupal 7 search_simplify(): digits joined across punctuation ("24/11" -> "2411"), runs of 2+ dots/dashes
# are word breaks, single . _ - are deleted ("ĐHQG-HCM" -> "đhqghcm"). ponytail: [^\w\s] approximates
# PREG_CLASS_PUNCTUATION (it also treats symbols such as + as punctuation).
_D7_NUM = re.compile(r"(\d+)[^\w\s]+(?=\d)")
_D7_DOTS = re.compile(r"[.\-]{2,}")
_D7_DEL = re.compile(r"[._\-]+")


def fold(text: str, mode: str) -> str:
    """'fold': strip marks, đ->d (S0). 'keep_d': strip marks, keep đ (MySQL-collation guess). 'exact': none."""
    text = unicodedata.normalize("NFC", text).lower()
    if mode == "exact":
        return text
    if mode == "fold":
        text = text.replace("đ", "d")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", text)


def tok(text: str, numbers: str = "s0", folding: str = "fold") -> list[str]:
    """numbers: 's0' (dates -> ISO, thousands joined), 'split' (as written), 'd7' (Drupal 7 rules)."""
    text = unicodedata.normalize("NFC", text or "").lower()
    if numbers == "s0":
        text = normalize_numbers(text)
    elif numbers == "d7":
        text = _D7_DEL.sub("", _D7_DOTS.sub(" ", _D7_NUM.sub(r"\1", text)))
    return _WORD.findall(fold(text, folding))


# name -> (fields, numbers, folding, match, query filter). S0 = title+body, s0 numbers, fold, AND.
TB, ALL = ("title", "body"), ("title", "body", "attachment")
VARIANTS = {
    "S0 (AND, title+body)": (TB, "s0", "fold", "and", None),
    "OR": (TB, "s0", "fold", "or", None),
    "min-should-match 50%": (TB, "s0", "fold", 0.5, None),
    "min-should-match 75%": (TB, "s0", "fold", 0.75, None),
    "title only": (("title",), "s0", "fold", "and", None),
    "body only": (("body",), "s0", "fold", "and", None),
    "+ attachment text": (ALL, "s0", "fold", "and", None),
    "+ attachment filename": (("title", "body", "afile"), "s0", "fold", "and", None),
    "exact diacritics": (TB, "s0", "exact", "and", None),
    "fold, keep đ": (TB, "s0", "keep_d", "and", None),
    "S0s (drop stopwords)": (TB, "s0", "fold", "and", "stop"),
    "drop words < 3 chars": (TB, "s0", "fold", "and", "min3"),
    "numbers as written": (TB, "split", "fold", "and", None),
    "phrase (consecutive)": (TB, "s0", "fold", "phrase", None),
    "D7 model (d7 tokens, đ=d)": (TB, "d7", "fold", "and", None),
    "D7 model, keep đ": (TB, "d7", "keep_d", "and", None),
    "D7 model + attachment text": (ALL, "d7", "fold", "and", None),
}


class Matcher:
    """One variant over a doc list; hits(query) -> doc_ids matching the query."""

    def __init__(self, docs, fields, numbers, folding, match, qfilter):
        self.numbers, self.folding, self.match, self.qfilter = numbers, folding, match, qfilter
        self.ids = [d["doc_id"] for d in docs]
        self.seqs = [[tok(_field(d, f), numbers, folding) for f in fields] for d in docs]
        self.sets = [set().union(*s) for s in self.seqs]
        self.stop = {t for w in STOPWORDS for t in tok(w, numbers, folding)}

    def query(self, q: str) -> list[str]:
        qt = tok(q, self.numbers, self.folding)
        if self.qfilter == "stop":
            qt = [t for t in qt if t not in self.stop]
        elif self.qfilter == "min3":
            qt = [t for t in qt if len(t) >= 3 or t.isdigit()]
        return qt

    def hits(self, q: str) -> list[str]:
        qt = self.query(q)
        if not qt:
            return []
        qs = set(qt)
        if self.match == "and":
            ok = [qs <= s for s in self.sets]
        elif self.match == "or":
            ok = [bool(qs & s) for s in self.sets]
        elif self.match == "phrase":
            ok = [any(_contains(seq, qt) for seq in seqs) for seqs in self.seqs]
        else:  # min-should-match fraction
            need = math.ceil(self.match * len(qs))
            ok = [len(qs & s) >= need for s in self.sets]
        return [i for i, y in zip(self.ids, ok) if y]


def _field(d, f):
    if f == "afile":   # what a Drupal file field renders: the file name
        return " ".join(a["url"].rsplit("/", 1)[-1] for a in d.get("attachments", []))
    return d.get(f) or ""


def _contains(seq, sub):
    n = len(sub)
    return any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


def parse_count(v: str):
    """Site count cell -> (low, high). 'many' = more than one result page (>= 10), no upper bound."""
    v = (v or "").strip().lower()
    if v.isdigit():
        return int(v), int(v)
    return (10, None) if v == "many" else (None, None)


def check(n: int, cell: str) -> str:
    """Our in-window count must not exceed the site's: the site indexes everything we have plus older posts.
    'ok', 'over' (we return more than the site), or 'n/a' (cell empty or 'many')."""
    lo, hi = parse_count(cell)
    if hi is None:
        return "n/a"
    return "ok" if n <= hi else "over"


def assess(rows, counts: dict[str, int]) -> dict[str, list[str]]:
    """Split rows by check(): 'ok' and 'over' are the assessable rows (numeric site count); 'na' ('many' or
    empty cell) cannot be checked. ok + over + na always equals len(rows)."""
    out = {"ok": [], "over": [], "na": []}
    for r in rows:
        out[{"ok": "ok", "over": "over", "n/a": "na"}[check(counts[r["qid"]], r["ctsv"])]].append(r["qid"])
    return out


# In-window docs the site is known to return (from the observation notes; ctsv). 14 doc-query pairs.
_B = "bai-viet/"
_HK1 = _B + "thong-bao-dang-ky-xet-cap-cac-loai-hoc-bong-hk-1-nh-2026-2027"
_DS = _B + "thong-bao-danh-sach-dang-ky-hoc-bong-kkht-hk1-2026-2027-va-hoc-bong-ngoai-ngan-sach-hk1"
KNOWN = {
    "P01": {_HK1, _DS,  # notes: "S0 returns the same 6"
            _B + "thong-bao-so-2-ve-danh-sach-dang-ky-hb-kkht-hk1-2026-2027",
            _B + "huong-dan-ve-qui-dinh-hoc-bong-khuyen-khich-hoc-tap-moi-tu-hk1-2026-2027",
            _B + "thong-bao-trien-khai-hoc-bong-uit-global-tu-hoc-ky-1-nam-hoc-2026-2027",
            _B + "quy-dinh-lien-quan-den-hoc-bong-sinh-vien"},
    "P05": {_HK1},  # notes: "the S0 hit is on the site's list"
    "P07": {_HK1, _DS,  # notes: "S0 returns 7 (site extras are older)", i.e. S0's 7 are among the site's 9
            _B + "danh-sach-du-kien-nhan-cac-loai-hoc-bong-tai-hk2-2025-2026",
            _B + "thong-bao-danh-sach-dang-ky-hoc-bong-kkht-hk1-2025-2026-va-hoc-bong-ngoai-ngan-sach-hk2",
            _B + "danh-sach-du-kien-nhan-cac-loai-hoc-bong-tai-hk1-2025-2026",
            _B + "thong-bao-danh-sach-dang-ky-hoc-bong-kkht-hk2-2024-2025-va-hoc-bong-ngoai-ngan-sach-hk1",
            _B + "thong-bao-dang-ky-xet-cap-cac-loai-hoc-bong-hoc-ky-1-nam-hoc-2025-2026"},
}
P01_SITE_DATES = ["2026-11-03", "2026-07-08", "2026-10-19", "2026-11-19", "2026-07-08", "2019-03-20"]


def d7_scores(docs, q: str) -> dict[str, float]:
    """Drupal 7 node-search relevance, approximated without HTML: title is <h1> (weight 1+25), body weight 1;
    'focus' decays with the number of distinct words seen; idf-like total = log10(1 + 1/sum of scores)."""
    per_doc = []
    for d in docs:
        sw, focus = Counter(), 1.0
        for words, w in ((tok(d.get("title"), "d7"), 26), (tok(d.get("body"), "d7"), 1)):
            for t in words:
                sw[t] += w * focus
                focus = min(1, .01 + 3.5 / (2 + len(sw) * .015))
        per_doc.append(sw)
    total = Counter()
    for sw in per_doc:
        total.update(sw)
    qt = set(tok(q, "d7"))
    return {d["doc_id"]: sum(sw[t] * math.log10(1 + 1 / max(1, total[t])) for t in qt)
            for d, sw in zip(docs, per_doc)}


def tfidf_scores(docs, q: str, field="body") -> dict[str, float]:
    df = Counter(t for d in docs for t in set(tok(d.get(field))))
    qt, n = set(tok(q)), len(docs)
    out = {}
    for d in docs:
        tf = Counter(tok(d.get(field)))
        out[d["doc_id"]] = sum((1 + math.log(tf[t])) * math.log(n / df[t]) for t in qt if tf[t])
    return out


def kendall_tau(order: list[str], ref: list[str]) -> float:
    """Kendall tau-a between two orderings of the same items (dates; equal dates count as concordant)."""
    pos = {x: i for i, x in enumerate(order)}
    pairs = [(a, b) for i, a in enumerate(ref) for b in ref[i + 1:]]
    s = sum(1 if pos[a] < pos[b] else (0 if pos[a] == pos[b] else -1) for a, b in pairs)
    return s / len(pairs)


def p01_order(ctsv, docs_by_id):
    """Each ranking's date sequence for the six P01 docs, and Kendall tau against the site's order."""
    q = "học bổng khuyến khích học tập HK1 2026-2027"
    pool = [docs_by_id[i] for i in KNOWN["P01"]]
    rankers = {"date (newest first)": {d["doc_id"]: d["date"] for d in pool},
               "D7 relevance (title x26)": d7_scores(ctsv, q),
               "tf-idf over body": tfidf_scores(ctsv, q),
               "tf-idf over title": tfidf_scores(ctsv, q, "title")}
    from lumen.index.bm25 import BM25F
    rankers["BM25 title+body"] = dict(BM25F(ctsv).search(q, k=len(ctsv)))
    rows = []
    for name, sc in rankers.items():
        dates = [docs_by_id[i]["date"][:10] for i in sorted(KNOWN["P01"], key=lambda i: (-_num(sc.get(i, 0)), i))]
        rows.append((name, dates, _tau_dates(dates, P01_SITE_DATES)))
    return rows


def _num(v):
    return v if isinstance(v, (int, float)) else int(re.sub(r"\D", "", v) or 0)


def _tau_dates(dates, ref):
    """tau over positions, matching repeated dates in order (the two 2026-07-08 posts are interchangeable)."""
    label = lambda seq: [f"{x}#{seq[:i].count(x)}" for i, x in enumerate(seq)]
    return kendall_tau(label(dates), label(ref))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="data/processed/docs.jsonl")
    ap.add_argument("--obs", default="data/eval/site_search_observations.tsv")
    ap.add_argument("--predict", help="TSV with qid and query columns: print S0 and D7-model counts per site")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if not Path(a.docs).exists():
        sys.exit(f"{a.docs} not found; build it with scripts/03_quick_corpus.py")
    docs = load_docs({"paths": {"docs": a.docs}})
    for d in docs:
        d["attachment"] = d.get("attachment") or ""
    ctsv = [d for d in docs if not d["doc_id"].startswith("daa/")]
    daa = [d for d in docs if d["doc_id"].startswith("daa/")]
    with open(a.predict or a.obs, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))  # queries may contain "
    if a.predict:
        return predict(rows, ctsv, daa)

    zeros = [r["qid"] for r in rows if r["ctsv"] == "0"]
    n_known = sum(len(ids) for q, ids in KNOWN.items() if any(r["qid"] == q for r in rows))
    print(f"ctsv docs: {len(ctsv)}; observations: {len(rows)}\n")
    print("Upper-bound check only: a variant that always returns zero would pass every assessable row, so read "
          "'zeros kept' and 'known pairs found' next to it."+"\n")
    print(f"| variant | ok (assessable) | over | n/a ('many') | excess docs | zeros kept (of {len(zeros)}) "
          f"| known site hits found (of {n_known}) |"+"\n"+"|---|---|---|---|---|---|---|")
    detail = {}
    for name, spec in VARIANTS.items():
        m = Matcher(ctsv, *spec)
        res = {r["qid"]: m.hits(r["query"]) for r in rows}
        a = assess(rows, {q: len(v) for q, v in res.items()})
        n_assess = len(a["ok"]) + len(a["over"])
        excess = sum(len(res[r["qid"]]) - parse_count(r["ctsv"])[1] for r in rows if r["qid"] in a["over"])
        kept = sum(not res[q] for q in zeros)
        known = sum(len(ids & set(res.get(q, []))) for q, ids in KNOWN.items())
        print(f"| {name} | {len(a['ok'])} of {n_assess} | {', '.join(a['over']) or '-'} | {len(a['na'])} "
              f"| {excess} | {kept} | {known} |")
        detail[name] = {q: len(v) for q, v in res.items()}
    print("\nUnassessable rows (site shows 'many'): "
          + ", ".join(r["qid"] for r in rows if parse_count(r["ctsv"])[1] is None))
    print("\nPer-query counts (ctsv, in-window corpus):\n")
    names = list(VARIANTS)
    print("| qid | site | " + " | ".join(f"v{i}" for i in range(len(names))) + " |")
    print("|---|---|" + "---|" * len(names))
    for r in rows:
        print(f"| {r['qid']} | {r['ctsv']} | " + " | ".join(str(detail[n][r['qid']]) for n in names) + " |")
    print("\n" + "; ".join(f"v{i} = {n}" for i, n in enumerate(names)))
    print("\nP01 order (site: " + ", ".join(P01_SITE_DATES) + ")\n")
    print("| ranking | order (dates) | Kendall tau vs site |\n|---|---|---|")
    for name, dates, tau in p01_order(ctsv, {d["doc_id"]: d for d in ctsv}):
        print(f"| {name} | {', '.join(dates)} | {tau:+.2f} |")


def predict(rows, ctsv, daa):
    ms = {(s, n): Matcher(c, *VARIANTS[v]) for s, c in (("ctsv", ctsv), ("daa", daa))
          for n, v in (("s0", "S0 (AND, title+body)"), ("d7", "D7 model (d7 tokens, đ=d)"),
                       ("d7k", "D7 model, keep đ"), ("att", "+ attachment text"))}
    print("qid\ts0_ctsv\td7_ctsv\td7k_ctsv\tatt_ctsv\ts0_daa\td7_daa")
    for r in rows:
        c = {k: len(m.hits(r["query"])) for k, m in ms.items()}
        print(f"{r['qid']}\t{c['ctsv', 's0']}\t{c['ctsv', 'd7']}\t{c['ctsv', 'd7k']}\t{c['ctsv', 'att']}"
              f"\t{c['daa', 's0']}\t{c['daa', 'd7']}")


if __name__ == "__main__":
    main()
