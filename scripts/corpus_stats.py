"""Print corpus statistics for the W2 milestone table."""
import json

from _common import load_config, resolve

from lumen.corpus.stats import corpus_stats

p = load_config()["paths"]
print(json.dumps(corpus_stats(resolve(p["docs"]), resolve(p["ocr_cache"])), ensure_ascii=False, indent=2))
