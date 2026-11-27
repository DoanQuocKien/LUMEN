"""Recency, series-number, academic-year and intent boosts (S7). [W3-A1, W3-C2]

This file implements the metadata part (A's W3-A1). The intent boost is B/C's (W3-B1/C2):
`apply_metadata_boost` returns a new score you can add the intent term to.

final = norm(base) + w_recency*recency + w_seq*seq_match + w_year*year_match
  recency   = 0.5 ** (age_days / half_life_days)           in (0, 1]
  seq_match = +1 query asks 'thông báo số N' and doc.notice_seq == N, -1 if different, else 0
  year_match= +1 same academic year, -1 different (and +0.5 / -0.5 for semester), else 0
Tune the weights on DEV ONLY (plan §10), then freeze.
"""
from __future__ import annotations

import datetime as dt

from lumen.meta.extract import _academic_year, _notice_seq, _semesters
from lumen.text.normalize import fold

DEFAULTS = {"w_recency": 0.10, "w_seq": 0.30, "w_year": 0.30, "half_life_days": 365.0}


def parse_query_meta(query: str) -> dict:
    q = fold(query)
    sems = _semesters(q)
    return {"notice_seq": _notice_seq(q), "academic_year": _academic_year(q), "semester": sems[0] if sems else None}


def recency(date: str | None, today: dt.date, half_life_days: float) -> float:
    if not date:
        return 0.0
    age = max(0, (today - dt.date.fromisoformat(date)).days)
    return 0.5 ** (age / half_life_days)


def metadata_features(qmeta: dict, doc: dict, today: dt.date, half_life_days: float) -> dict:
    m = doc.get("meta", {})
    seq = 0.0
    if qmeta["notice_seq"] is not None and m.get("notice_seq") is not None:
        seq = 1.0 if qmeta["notice_seq"] == m["notice_seq"] else -1.0
    yr = 0.0
    if qmeta["academic_year"] and m.get("academic_year"):
        yr += 1.0 if qmeta["academic_year"] == m["academic_year"] else -1.0
    if qmeta["semester"] and m.get("semester"):
        yr += 0.5 if qmeta["semester"] == m["semester"] else -0.5
    return {"recency": recency(doc.get("date"), today, half_life_days), "seq": seq, "year": yr}


def apply_metadata_boost(ranked: list[tuple[str, float]], docs: dict[str, dict], query: str,
                         today: dt.date | None = None, **params) -> list[tuple[str, float]]:
    """ranked: [(doc_id, base_score)] best first. Returns re-ranked [(doc_id, final_score)]."""
    p = {**DEFAULTS, **params}
    today = today or dt.date.today()
    if not ranked:
        return []
    scores = [s for _, s in ranked]
    lo, hi = min(scores), max(scores)
    qmeta = parse_query_meta(query)
    out = []
    for doc_id, s in ranked:
        base = (s - lo) / (hi - lo) if hi > lo else 1.0
        f = metadata_features(qmeta, docs[doc_id], today, p["half_life_days"])
        out.append((doc_id, base + p["w_recency"] * f["recency"] + p["w_seq"] * f["seq"] + p["w_year"] * f["year"]))
    return sorted(out, key=lambda x: (-x[1], x[0]))
