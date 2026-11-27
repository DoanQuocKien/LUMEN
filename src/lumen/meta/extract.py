"""Regex metadata: 'Quyết định số X/YYYY', 'Thông báo số N', HK1/HK2, năm học, doc type. [W2-A2]

Everything except `doc_number` runs on fold()ed text (lowercase, no diacritics), so the same
functions also parse queries typed without diacritics (used by retrieve/boost.py).
"""
from __future__ import annotations

import hashlib
import re

from lumen.text.dates import parse_date
from lumen.text.normalize import fold, normalize

# (label, folded keyword). Earliest keyword in the title wins; then the first 300 chars of the body.
DOC_TYPES = [
    ("quyet_dinh", "quyet dinh"), ("thong_bao", "thong bao"), ("ke_hoach", "ke hoach"),
    ("huong_dan", "huong dan"), ("the_le", "the le"), ("quy_che", "quy che"),
    ("quy_dinh", "quy dinh"), ("cong_van", "cong van"), ("danh_sach", "danh sach"),
    ("to_trinh", "to trinh"), ("bien_ban", "bien ban"), ("ket_qua", "ket qua"),
]
_DOC_NUMBER = re.compile(r"\b[Ss]ố\s*[:：]?\s*(\d{1,5}(?:\s*/\s*[0-9A-ZĐ][0-9A-ZĐa-z\-\.]*){1,3})")
_NOTICE_SEQ = re.compile(r"thong bao\s*(?:so\s*)?(\d{1,3})(?![\d/])|\blan\s*(?:thu\s*)?(\d{1,2})\b|\bdot\s*(\d{1,2})\b")
_ACAD_YEAR = re.compile(r"(?<!\d)(20\d{2})\s*[-–—/]\s*(20\d{2})(?!\d)")
_SEMESTER = re.compile(r"\bhk\s*([123])\b|\bhoc\s*k[yi]\s*(1|2|3|i{1,2}\b|he\b)")


def _doc_type(title_f: str, body_f: str) -> str:
    best = None
    for label, kw in DOC_TYPES:
        i = title_f.find(kw)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, label)
    if best:
        return best[1]
    head = body_f[:300]
    for label, kw in DOC_TYPES:
        if kw in head:
            return label
    return "khac"


def _notice_seq(text_f: str) -> int | None:
    m = _NOTICE_SEQ.search(text_f)
    return int(next(g for g in m.groups() if g)) if m else None


def _academic_year(text_f: str) -> str | None:
    for m in _ACAD_YEAR.finditer(text_f):
        a, b = int(m.group(1)), int(m.group(2))
        if b == a + 1:
            return f"{a}-{b}"
    return None


def _semesters(text_f: str) -> list[str]:
    out: list[str] = []
    for m in _SEMESTER.finditer(text_f):
        v = (m.group(1) or m.group(2)).lower()
        label = {"1": "HK1", "i": "HK1", "2": "HK2", "ii": "HK2", "3": "HK3", "he": "HKH"}[v]
        if label not in out:
            out.append(label)
    return out


def extract_meta(title: str, body: str = "", pdf_text: str = "") -> dict:
    """Metadata for one document. Title evidence is tried first, then the start of the body/PDF."""
    title_f = fold(title)
    head = (body[:3000] + "\n" + pdf_text[:3000])
    head_f = fold(head)
    dn = _DOC_NUMBER.search(title) or _DOC_NUMBER.search(head)
    doc_number = re.sub(r"\s*/\s*", "/", dn.group(1)).strip() if dn else None
    doc_year = None
    if doc_number:
        y = next((p for p in doc_number.split("/") if re.fullmatch(r"(19|20)\d{2}", p)), None)
        doc_year = int(y) if y else None
    sems = _semesters(title_f) or _semesters(head_f)
    return {
        "doc_type": _doc_type(title_f, fold(body)),
        "doc_number": doc_number,
        "doc_year": doc_year,
        "notice_seq": _notice_seq(title_f) or _notice_seq(head_f[:600]),
        "academic_year": _academic_year(title_f) or _academic_year(head_f),
        "semester": sems[0] if sems else None,
        "semesters": sems,
        "doc_date": parse_date(pdf_text[:2500]) or parse_date(body[:1500]),
    }


# ---- series grouping and de-duplication ---------------------------------------------------
_SERIES_NOISE = re.compile(
    r"thong bao\s*(so\s*)?\d*|\blan\s*(thu\s*)?\d+|\bdot\s*\d+|\bso\s*[:]?\s*\d+(/[\w\-\.]+)*|"
    r"\bhk\s*[123]\b|hoc\s*k[yi]\s*\w+|nam hoc\s*\d{4}\s*[-–—/]\s*\d{4}|\d{4}\s*[-–—/]\s*\d{4}|\d+"
)


def series_key(title: str, doc_type: str) -> str:
    """Same series = same doc type + same title once numbers, years and semesters are removed."""
    core = _SERIES_NOISE.sub(" ", fold(title))
    core = re.sub(r"[^a-z\s]", " ", core)
    core = " ".join(core.split())
    return hashlib.sha1(f"{doc_type}|{core}".encode()).hexdigest()[:10]


def body_fingerprint(text: str) -> str:
    return hashlib.sha1(normalize(text).encode()).hexdigest()[:16]
