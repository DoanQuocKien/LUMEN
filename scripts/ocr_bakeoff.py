"""W1-A4 OCR bake-off. `sample` picks 15 scanned PDFs + 3 reference pages; `run` compares engines.

  python scripts/ocr_bakeoff.py sample
  (hand-transcribe the 3 files in data/interim/bakeoff/refs/)
  python scripts/ocr_bakeoff.py run --engines tesseract paddleocr vietocr
"""
import argparse
import json

from _common import load_config, resolve

from lumen.ocr.bakeoff import run_bakeoff, sample_scanned
from lumen.ocr.engines import make_engine

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["sample", "run"])
ap.add_argument("--engines", nargs="+", default=["tesseract"])
ap.add_argument("--n", type=int, default=15)
args = ap.parse_args()
cfg = load_config()
out = resolve(cfg["ocr"]["bakeoff_dir"])
if args.cmd == "sample":
    r = sample_scanned(resolve(cfg["paths"]["raw_attachments"]), out, n_pdfs=args.n, min_chars=cfg["ocr"]["min_chars_per_page"])
    print(f"{r['n_scanned_found']} scanned PDFs found; sampled {len(r['items'])}. Transcribe the empty files in {out / 'refs'}")
else:
    items = json.loads((out / "sample.json").read_text(encoding="utf-8"))["items"]
    engines = {}
    for name in args.engines:
        try:
            engines[name] = make_engine(name, cfg["ocr"]["lang"])
        except Exception as e:
            print(f"skip {name}: {type(e).__name__}: {e}")
    for row in run_bakeoff(items, engines, out, cfg["ocr"]["dpi"]):
        print(row)
    print(f"-> {out / 'results.csv'}, summary.csv. Record the choice in docs/decisions.md")
