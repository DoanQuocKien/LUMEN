import math

from lumen.eval.metrics import (average_precision, ndcg_at_k, precision_at_k,
                                recall_at_k, reciprocal_rank)

RUN = ["d1", "d2", "d3", "d4"]
QRELS = {"d2": 2, "d4": 1, "d9": 1}  # d9 relevant but never retrieved


def test_precision_recall():
    assert precision_at_k(RUN, QRELS, 2) == 0.5
    assert math.isclose(recall_at_k(RUN, QRELS, 4), 2 / 3)


def test_rr_and_ap():
    assert reciprocal_rank(RUN, QRELS) == 0.5
    assert math.isclose(average_precision(RUN, QRELS), (1 / 2 + 2 / 4) / 3)


def test_ndcg_perfect_and_empty():
    assert ndcg_at_k(["d2", "d4", "d9"], QRELS, 3) == 1.0
    assert ndcg_at_k(RUN, {}, 10) == 0.0
