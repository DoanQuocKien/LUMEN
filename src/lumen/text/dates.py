"""Date parsing helpers shared by the crawler, parser and metadata extractor."""
from __future__ import annotations

import datetime as dt
import re

_DMY = re.compile(r"(?<!\d)(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})(?!\d)")
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_VN = re.compile(r"ng[àa]y\s*(\d{1,2})\s*th[áa]ng\s*(\d{1,2})\s*n[ăa]m\s*(\d{4})", re.I)


def _valid(y: int, m: int, d: int) -> str | None:
    try:
        return dt.date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_date(text: str) -> str | None:
    """First valid date in `text` as YYYY-MM-DD, else None.

    Understands 'ngày 5 tháng 11 năm 2025', '05/11/2025', '5-11-2025', '2025-11-05'.
    """
    if not text:
        return None
    for rx, order in ((_VN, "dmy"), (_ISO, "ymd"), (_DMY, "dmy")):
        for m in rx.finditer(text):
            a, b, c = (int(x) for x in m.groups())
            iso = _valid(a, b, c) if order == "ymd" else _valid(c, b, a)
            if iso:
                return iso
    return None
