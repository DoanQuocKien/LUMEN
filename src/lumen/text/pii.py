"""Privacy helpers: student IDs (MSSV) must never reach git, slides or the report."""
from __future__ import annotations

import re

# UIT student IDs are 8 digits (e.g. 21520001). Match bare 8-digit runs, not longer numbers.
MSSV = re.compile(r"(?<!\d)\d{8}(?!\d)")


def has_mssv(text: str) -> bool:
    return bool(MSSV.search(text))


def mask_mssv(text: str) -> str:
    return MSSV.sub("********", text)
