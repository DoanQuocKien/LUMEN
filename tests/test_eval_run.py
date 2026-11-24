import pytest
from ranx import Qrels, Run, evaluate

from lumen.eval.run import per_query, read_qrels, read_run
from lumen.eval.significance import bootstrap_ci, paired_randomization


def test_matches_ranx(tmp_path):
    (tmp_path / "r.trec").write_text(
        "q1 Q0 a 1 9 x\nq1 Q0 b 2 8 x\nq1 Q0 c 3 7 x\nq2 Q0 c 1 5 x\nq2 Q0 a 2 4 x\n")
    (tmp_path / "q.txt").write_text("q1 0 a 2\nq1 0 c 1\nq2 0 a 1\nq2 0 b 2\n")
    sc = per_query(read_run(tmp_path / "r.trec"), read_qrels(tmp_path / "q.txt"))
    ref = evaluate(
        Qrels({"q1": {"a": 2, "c": 1}, "q2": {"a": 1, "b": 2}}),
        Run({"q1": {"a": 9, "b": 8, "c": 7}, "q2": {"c": 5, "a": 4}}),
        ["ndcg@10", "mrr@10", "map@100", "recall@10"], return_mean=False)
    # ranx 'ndcg' uses linear gain by default; compare the metrics that do not depend on gain
    for i, q in enumerate(["q1", "q2"]):
        assert sc[q]["mrr@10"] == pytest.approx(ref["mrr@10"][i])
        assert sc[q]["map"] == pytest.approx(ref["map@100"][i])
        assert sc[q]["recall@10"] == pytest.approx(ref["recall@10"][i])


def test_significance():
    a = [0.9] * 30
    assert paired_randomization(a, [0.1] * 30, n=2000) < 0.01
    assert paired_randomization(a, a, n=2000) == pytest.approx(1.0, abs=0.01)
    lo, hi = bootstrap_ci([0.2, 0.4, 0.6, 0.8] * 10, n=1000)
    assert lo < 0.5 < hi
