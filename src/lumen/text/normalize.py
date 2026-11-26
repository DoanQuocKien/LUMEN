"""Vietnamese text normalization. [W1-C1]

normalize() keeps diacritics; fold() also removes them so that 'hoc bong' matches 'học bổng'.
Index both versions of each field. tokens() is the shared tokenizer for all indexes.
"""
import re
import unicodedata

_WS = re.compile(r"\s+")
_THOUSANDS = re.compile(r"(?<=\d)[.,](?=\d{3}(?!\d))")
_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_WORD = re.compile(r"\w+")

# Common Vietnamese function words (with diacritics). Used only when stop=True (S0s, ablations).
STOPWORDS = frozenset("""
là của và các những một này đó khi nào thế sao gì ai đâu bao nhiêu có không cần phải được bị
để cho với từ trong ngoài về theo tại sau trước đã đang sẽ rồi chưa vẫn cũng còn nên nhưng
hay hoặc nếu thì mà ra vào lên xuống em anh chị tôi mình ạ nhé ơi xin vui lòng
hỏi e ac ak ạ okla k ko th đcko mk nhỉ vậy
""".split())


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


def normalize_numbers(text: str) -> str:
    """'1.487.000' -> '1487000'; '1/9/2026' -> '2026-09-01' (day-first, as written in Vietnam)."""
    text = _DATE.sub(lambda m: f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}", text)
    return _THOUSANDS.sub("", text)


_FOLDED_STOP = frozenset(fold(w) for w in STOPWORDS)


def tokens(text: str, folded: bool = True, stop: bool = False) -> list[str]:
    """Syllable tokens. folded=True removes diacritics; stop=True drops stopwords."""
    text = normalize_numbers(text)
    text = fold(text) if folded else normalize(text)
    toks = _WORD.findall(text)
    if stop:
        sw = _FOLDED_STOP if folded else STOPWORDS
        toks = [t for t in toks if t not in sw]
    return toks


def segment(text: str) -> list[str]:
    """Word-segmented tokens (compound words joined with '_') via pyvi if installed.

    Falls back to syllables so the pipeline still runs without the optional dependency."""
    try:
        from pyvi import ViTokenizer
    except ImportError:
        return _WORD.findall(normalize(normalize_numbers(text)))
    return ViTokenizer.tokenize(normalize(normalize_numbers(text))).split()
