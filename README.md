# LUMEN

**Legal-University Multi-stage Evidence Navigation**: ranked search over student-affairs posts
and regulations on [ctsv.uit.edu.vn](https://ctsv.uit.edu.vn/). CS419 Information Retrieval, UIT.

You type a Vietnamese query and get back ranked links to the relevant posts, including posts whose
only content is a scanned PDF. The pipeline runs Boolean → BM25F → dense → RRF → cross-encoder
rerank → metadata boost.

- What we build and how it is judged: [`docs/PROJECT_SPECIFICATION.md`](docs/PROJECT_SPECIFICATION.md)
- How and when we build it: [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)

## Layout

```
configs/            run and crawl configuration (default.yaml)
data/raw/           cached HTML and attachments (gitignored)
data/interim/ocr/   per-page OCR cache (gitignored)
data/processed/     docs.jsonl, passages.jsonl, indexes (gitignored)
data/eval/          queries and qrels (tracked)
src/lumen/
  crawl/            listing and post crawler (10 s delay, resumable)
  parse/            HTML boilerplate removal, attachment links
  ocr/              text-layer detection, OCR engines
  text/             normalization, diacritic folding, word segmentation
  meta/             doc number, notice series, academic year, doc type
  index/            Boolean, BM25F, LSI, dense (FAISS) indexes
  retrieve/         systems S0–S7, fusion, rerank, boosting
  classify/         doc-type / query-intent classifier (Ch6)
  eval/             metrics, significance tests, run evaluation
  app/              demo UI
scripts/            numbered pipeline entry points
experiments/        TREC run files and results tables
tests/              unit tests
docs/               plan, decisions, judging guidelines, GenAI log
reports/            report and slide figures
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
pytest
```

OCR also needs system packages: Tesseract with the `vie` language pack, and Poppler (for `pdf2image`).

## Crawling rules

`robots.txt` sets `Crawl-delay: 10` and disallows `/search/`.
The crawler uses one worker, waits at least 10 s between requests, caches every response, and never
calls the site search. Raw data may contain student names and MSSV, so keep it out of git, slides
and the report.

## Team

| # | Member | Role |
|---|--------|------|
| 1 | [Doan Quoc Kien](https://github.com/DoanQuocKien) | Team leader |
