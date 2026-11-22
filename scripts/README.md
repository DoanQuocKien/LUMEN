# Pipeline scripts (planned)

Run them in order. Each one is resumable and reads paths from `configs/default.yaml`.

| Script | Task | Output |
|---|---|---|
| `01_crawl_listing.py` | W1-A1 | `data/raw/posts_index.csv` |
| `02_crawl_posts.py` | W1-A2 | `data/raw/html/`, `data/raw/attachments/` |
| `03_parse.py` | W1-A3 | `data/interim/posts.jsonl` |
| `04_ocr.py` | W2-A1 | `data/interim/ocr/` |
| `05_build_corpus.py` | W2-A2/A3 | `data/processed/docs.jsonl`, `passages.jsonl` |
| `06_build_indexes.py` | W1-C2 … W2-C3 | indexes in `data/processed/` |
| `07_run_systems.py` | W2–W3 | `experiments/runs/*.trec` |
| `08_evaluate.py` | W1-B2 | `experiments/results/*.csv` |
