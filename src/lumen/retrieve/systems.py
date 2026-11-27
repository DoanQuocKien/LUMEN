"""Builds S0, S0s, S1 (more later) from the corpus and writes TREC runs.

Usage: python -m lumen.retrieve.systems --system S1 --queries data/eval/queries_pilot.tsv
Corpus: data/processed/docs.jsonl if it exists, else the title-only listing index (W1 fallback).
"""
import argparse
import csv
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from lumen.index.bm25 import BM25F
from lumen.index.boolean import BooleanIndex


def load_docs(cfg) -> list[dict]:
    p = cfg["paths"]
    if Path(p["docs"]).exists():
        with open(p["docs"], encoding="utf-8") as f:
            docs = [json.loads(line) for line in f]
        for d in docs:
            d["attachment"] = " ".join(a.get("text") or "" for a in d.get("attachments", []))
        return docs
    with open(p["listing_index"], encoding="utf-8", newline="") as f:
        return [{"doc_id": urlsplit(r["url"]).path.strip("/"), "title": r["title"],
                 "date": r["date"], "body": ""} for r in csv.DictReader(f)]


def load_queries(path) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        return [(r["qid"], r["query"]) for r in csv.DictReader(f, delimiter="\t")]


def build(system: str, docs, cfg):
    """Return search(query, k) -> list of (doc_id, score)."""
    if system in ("S0", "S0s"):
        idx = BooleanIndex(docs)
        stop = system == "S0s"
        return lambda q, k: [(d, float(k - i)) for i, d in enumerate(idx.search(q, stop=stop, k=k))]
    c = cfg["bm25"]
    if system == "S1":
        idx = BM25F(docs, {"title": 1.0, "body": 1.0}, c["k1"], c["b"])
    elif system == "S2":
        idx = BM25F(docs, c["field_boost"], c["k1"], c["b"])
    else:
        raise ValueError(f"{system} is not implemented yet")
    return idx.search


def write_trec(path, results: dict[str, list[tuple[str, float]]], run_id: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for qid, hits in results.items():
            for rank, (doc, score) in enumerate(hits, start=1):
                f.write(f"{qid} Q0 {doc} {rank} {score:.6f} {run_id}\n")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True, choices=["S0", "S0s", "S1", "S2"])
    ap.add_argument("--queries", default="data/eval/queries_pilot.tsv")
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("-k", type=int, default=100)
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    search = build(a.system, load_docs(cfg), cfg)
    run_id = f"{a.system}_{time.strftime('%Y%m%d-%H%M')}"
    out = Path(cfg["paths"]["runs"]) / f"{run_id}.trec"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_trec(out, {qid: search(q, a.k) for qid, q in load_queries(a.queries)}, run_id)
    out.with_suffix(".json").write_text(json.dumps({"system": a.system, "queries": a.queries,
                                                    "bm25": cfg["bm25"]}, indent=1), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
