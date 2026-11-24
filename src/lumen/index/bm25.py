"""BM25 / BM25F over title, body and attachment fields (S1, S2). [W1-C3, W2-C1]

BM25F (Robertson & Zaragoza): per-field term frequency is length-normalized and boosted,
summed into one pseudo-frequency, then saturated once. One field with boost 1 is plain BM25.
"""
import math
from collections import Counter, defaultdict

from lumen.text.normalize import tokens


class BM25F:
    def __init__(self, docs, boosts=None, k1=1.2, b=0.75, stop=False):
        """docs: dicts with doc_id and the fields named in boosts (default: title+body, boost 1)."""
        self.boosts = boosts or {"title": 1.0, "body": 1.0}
        self.k1, self.b, self.stop = k1, b, stop
        self.ids = [d["doc_id"] for d in docs]
        self.tf = defaultdict(dict)      # term -> {doc index: [per-field tf]}
        self.len = {f: [0] * len(docs) for f in self.boosts}
        fields = list(self.boosts)
        for i, d in enumerate(docs):
            for j, f in enumerate(fields):
                toks = tokens(d.get(f) or "", stop=stop)
                self.len[f][i] = len(toks)
                for t, c in Counter(toks).items():
                    self.tf[t].setdefault(i, [0] * len(fields))[j] = c
        n = len(docs)
        self.avg = {f: (sum(v) / n if n else 0) or 1 for f, v in self.len.items()}
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.tf.items()}
        self._fields = fields

    def search(self, query: str, k: int = 100) -> list[tuple[str, float]]:
        scores = defaultdict(float)
        for t in set(tokens(query, stop=self.stop)):
            for i, tfs in self.tf.get(t, {}).items():
                pseudo = 0.0
                for j, f in enumerate(self._fields):
                    if tfs[j]:
                        norm = 1 - self.b + self.b * self.len[f][i] / self.avg[f]
                        pseudo += self.boosts[f] * tfs[j] / norm
                scores[i] += self.idf[t] * pseudo / (self.k1 + pseudo)
        top = sorted(scores.items(), key=lambda x: (-x[1], self.ids[x[0]]))[:k]
        return [(self.ids[i], s) for i, s in top]
