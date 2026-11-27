"""W2-A1: OCR all scanned PDFs, cached per page in data/interim/ocr/. Run in the background; resumable.

  python scripts/04_ocr.py --config configs/default.yaml configs/daa.yaml
"""
import argparse
import json

from _common import load_config, resolve

from lumen.corpus.cache import lookup
from lumen.ocr.engines import make_engine, ocr_pdf

ap = argparse.ArgumentParser()
ap.add_argument("--config", nargs="+", default=["configs/default.yaml"])
ap.add_argument("--posts", default="data/interim/posts.jsonl")
ap.add_argument("--engine", default=None, help="default: ocr.engine from the first config (decide after W1-A4)")
ap.add_argument("--limit", type=int, default=None)
ap.add_argument("--retry-failed", action="store_true")
args = ap.parse_args()
cfgs = [load_config(c) for c in args.config]
cfg = cfgs[0]
o = cfg["ocr"]
fetch_path = lookup([resolve(c["paths"]["raw_html"]) for c in cfgs])
engine = make_engine(args.engine or o["engine"], o["lang"])
seen, n = set(), 0
for ln in resolve(args.posts).read_text(encoding="utf-8").splitlines():
    for a in json.loads(ln)["attachments"]:
        if a["ext"] != "pdf" or a["url"] in seen:
            continue
        seen.add(a["url"])
        f = fetch_path(a["url"])
        if f is None:
            continue
        n += 1
        pages = ocr_pdf(f, engine, resolve(cfg["paths"]["ocr_cache"]), o["dpi"], o["min_chars_per_page"],
                        o.get("low_conf", 60.0), retry_failed=args.retry_failed, lang=o["lang"])
        bad = sum(1 for x in pages if x["status"] != "ok")
        print(f"[{n}] {a['url'].rsplit('/', 1)[-1]}: {len(pages)} pages, {bad} failed/missing", flush=True)
        if args.limit and n >= args.limit:
            raise SystemExit
