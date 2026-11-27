"""W1-A3: parse cached post HTML -> data/interim/posts.jsonl (no network).

  python scripts/03_parse.py --config configs/default.yaml configs/daa.yaml --sample 20
Reads the crawler's listing CSV + cache (paths.listing_index, paths.raw_html) of every config.
"""
import argparse
import random

from _common import load_config, resolve

from lumen.corpus.posts import parse_cached_posts, write_posts

ap = argparse.ArgumentParser()
ap.add_argument("--config", nargs="+", default=["configs/default.yaml"])
ap.add_argument("--out", default="data/interim/posts.jsonl")
ap.add_argument("--sample", type=int, default=0, help="print N random parsed posts to check by eye")
args = ap.parse_args()
allp = []
for c in args.config:
    p = load_config(c)["paths"]
    posts, missing = parse_cached_posts(resolve(p["listing_index"]), resolve(p["raw_html"]))
    print(f"{c}: parsed {len(posts)} posts ({missing} listed but not fetched / non-200)")
    allp += posts
write_posts(allp, resolve(args.out))
empty = sum(1 for x in allp if len(x["body_text"]) < 20)
print(f"{len(allp)} posts -> {args.out}; (almost) empty body: {empty} (expected for PDF-only posts)")
for x in random.Random(0).sample(allp, min(args.sample, len(allp))):
    print("\n" + "=" * 70, f"\n{x['title']} | {x['date']} | {x['url']}\nattachments: {[a['name'] for a in x['attachments']]}"
          f"\nrelated: {len(x['related'])}\n{x['body_text'][:500]}")
