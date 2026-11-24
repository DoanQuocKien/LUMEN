"""Inverted index with diacritic-insensitive AND matching, sorted by date (S0 site replica). [W1-C2]"""
from collections import defaultdict

from lumen.text.normalize import tokens


class BooleanIndex:
    """docs: list of dicts with doc_id, date (ISO string or ''), and text fields named in `fields`."""

    def __init__(self, docs, fields=("title", "body")):
        self.date = {d["doc_id"]: d.get("date") or "" for d in docs}
        self.post = defaultdict(set)
        for d in docs:
            for f in fields:
                for t in tokens(d.get(f) or ""):
                    self.post[t].add(d["doc_id"])

    def search(self, query: str, stop: bool = False, k: int | None = None) -> list[str]:
        """Docs containing every query term, newest first. stop=True is S0s."""
        terms = set(tokens(query, stop=stop))
        if not terms:
            return []
        sets = [self.post.get(t, set()) for t in terms]
        hits = set.intersection(*sets)
        out = sorted(hits, key=lambda i: (self.date[i], i), reverse=True)
        return out[:k] if k else out
