"""Vietnamese text normalization. [W1-C1]

normalize() keeps diacritics; fold() also removes them so that 'hoc bong' matches 'học bổng'.
Index both versions of each field.
"""
import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Unicode NFC, lowercase, collapse whitespace."""
    text = unicodedata.normalize("NFC", text).lower()
    return _WS.sub(" ", text).strip()


def fold(text: str) -> str:
    """normalize() and remove diacritics, mapping đ to d."""
    text = normalize(text).replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", stripped)
