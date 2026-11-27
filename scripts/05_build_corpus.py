"""W2-A3: one command -> data/processed/docs.jsonl + passages.jsonl (reads OCR from cache only).

  python scripts/05_build_corpus.py --config configs/default.yaml configs/daa.yaml
"""
import argparse

from _common import load_config, resolve

from lumen.corpus.build import build_corpus
from lumen.corpus.cache import lookup
from lumen.corpus.stats import corpus_stats

ap = argparse.ArgumentParser()
ap.add_argument("--config", nargs="+", default=["configs/default.yaml"])
ap.add_argument("--posts", default="data/interim/posts.jsonl")
args = ap.parse_args()
cfgs = [load_config(c) for c in args.config]
cfg = cfgs[0]
p, o, ps = cfg["paths"], cfg["ocr"], cfg["passages"]
fetch_path = lookup([resolve(c["paths"]["raw_html"]) for c in cfgs])
res = build_corpus(resolve(args.posts), resolve(p["raw_html"]), resolve(p["ocr_cache"]), resolve(p["docs"]),
                   resolve(p["passages"]), fetch_path, o["engine"], o["lang"], o["min_chars_per_page"],
                   ps["size_syllables"], ps["overlap_syllables"])
print(res)
print(corpus_stats(resolve(p["docs"]), resolve(p["ocr_cache"])))
