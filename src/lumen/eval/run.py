"""CLI: evaluate a TREC run against qrels, overall and per query style. [W1-B2]

Usage: python -m lumen.eval.run --run experiments/runs/X.trec --qrels data/eval/qrels_dev.txt \
           --queries data/eval/queries_dev.tsv [--baseline experiments/runs/Y.trec]
Queries without any qrels row are skipped (not judged yet). Unjudged documents count as non-relevant."""
import argparse
import csv
from collections import defaultdict

from lumen.eval import metrics as M
from lumen.eval.significance import bootstrap_ci, paired_randomization

METRICS = {
    "ndcg@10": lambda r, q: M.ndcg_at_k(r, q, 10),
    "mrr@10": lambda r, q: M.reciprocal_rank(r, q, 10),
    "p@5": lambda r, q: M.precision_at_k(r, q, 5),
    "recall@10": lambda r, q: M.recall_at_k(r, q, 10),
    "recall@100": lambda r, q: M.recall_at_k(r, q, 100),
    "map": lambda r, q: M.average_precision(r, q),
}


def read_run(path) -> dict[str, list[str]]:
    """TREC run -> {qid: doc_ids by rank}. Ordered by the rank column, not by file order."""
    rows = defaultdict(list)
    seen = set()
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            p = line.split()
            if len(p) >= 6:
                if (p[0], p[2]) in seen:   # a repeated document would count twice in Recall/AP
                    raise ValueError(f"{path}:{n}: duplicate document {p[2]!r} for query {p[0]!r}")
                seen.add((p[0], p[2]))
                rows[p[0]].append((int(p[3]), p[2]))
    return {q: [d for _, d in sorted(v)] for q, v in rows.items()}


def read_qrels(path) -> dict[str, dict[str, int]]:
    out = defaultdict(dict)
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.split()
            if len(p) >= 4:
                out[p[0]][p[2]] = int(p[3])
    return dict(out)


def read_styles(path) -> dict[str, str]:
    with open(path, encoding="utf-8", newline="") as f:
        return {r["qid"]: r["style"] for r in csv.DictReader(f, delimiter="\t")}


def per_query(run, qrels) -> dict[str, dict[str, float]]:
    """Metric values for every judged query; a query missing from the run scores 0."""
    return {q: {m: fn(run.get(q, []), qrels[q]) for m, fn in METRICS.items()} for q in qrels}


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def table(scores, styles) -> str:
    groups = {"ALL": list(scores)}
    for q in scores:
        groups.setdefault(styles.get(q, "?"), []).append(q)
    head = f"{'style':6}{'n':>4} " + " ".join(f"{m:>10}" for m in METRICS)
    lines = [head]
    for g, qs in groups.items():
        lines.append(f"{g:6}{len(qs):>4} " + " ".join(f"{mean([scores[q][m] for q in qs]):>10.4f}" for m in METRICS))
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--qrels", required=True)
    ap.add_argument("--queries", help="TSV with a style column, for the per-style rows")
    ap.add_argument("--baseline", help="second run: paired significance on nDCG@10")
    a = ap.parse_args(argv)
    qrels = read_qrels(a.qrels)
    styles = read_styles(a.queries) if a.queries else {}
    sc = per_query(read_run(a.run), qrels)
    print(table(sc, styles))
    nd = [sc[q]["ndcg@10"] for q in sc]
    lo, hi = bootstrap_ci(nd)
    print(f"\nnDCG@10 95% CI: [{lo:.4f}, {hi:.4f}]")
    if a.baseline:
        base = per_query(read_run(a.baseline), qrels)
        p = paired_randomization(nd, [base[q]["ndcg@10"] for q in sc])
        print(f"vs baseline: mean diff {mean(nd) - mean([base[q]['ndcg@10'] for q in sc]):+.4f}, p = {p:.4f}")


if __name__ == "__main__":
    main()
