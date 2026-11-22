"""Ranking metrics for one query (Ch2). [W1-B2]

ranking: list of doc_ids in rank order.
qrels:   {doc_id: grade}, grade 0/1/2. Unjudged documents count as non-relevant.
A document is relevant when grade >= rel_threshold (default 1).
Cross-check against ranx before reporting numbers.
"""
import math


def _rel(qrels, doc, t):
    return qrels.get(doc, 0) >= t


def precision_at_k(ranking, qrels, k, rel_threshold=1):
    return sum(_rel(qrels, d, rel_threshold) for d in ranking[:k]) / k


def recall_at_k(ranking, qrels, k, rel_threshold=1):
    n_rel = sum(g >= rel_threshold for g in qrels.values())
    if n_rel == 0:
        return 0.0
    return sum(_rel(qrels, d, rel_threshold) for d in ranking[:k]) / n_rel


def reciprocal_rank(ranking, qrels, k=None, rel_threshold=1):
    for i, d in enumerate(ranking[:k] if k else ranking, start=1):
        if _rel(qrels, d, rel_threshold):
            return 1.0 / i
    return 0.0


def average_precision(ranking, qrels, rel_threshold=1):
    n_rel = sum(g >= rel_threshold for g in qrels.values())
    if n_rel == 0:
        return 0.0
    hits, total = 0, 0.0
    for i, d in enumerate(ranking, start=1):
        if _rel(qrels, d, rel_threshold):
            hits += 1
            total += hits / i
    return total / n_rel


def ndcg_at_k(ranking, qrels, k):
    """Graded nDCG with gain (2^grade - 1) and log2 discount."""
    def dcg(grades):
        return sum((2 ** g - 1) / math.log2(i + 1) for i, g in enumerate(grades, start=1))

    actual = dcg([qrels.get(d, 0) for d in ranking[:k]])
    ideal = dcg(sorted(qrels.values(), reverse=True)[:k])
    return actual / ideal if ideal > 0 else 0.0
