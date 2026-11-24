# LUMEN — Implementation Plan (4 weeks, 3 members)

**Project:** LUMEN — Legal-University Multi-stage Evidence Navigation
**Course:** CS419 Information Retrieval (UIT)
**Plan version:** v1, 2026-11-22 · **Spec:** [PROJECT_SPECIFICATION.md](PROJECT_SPECIFICATION.md)
**Weeks:** W1 Mon 23/11 – Sun 29/11 · W2 30/11 – 06/12 · W3 07/12 – 13/12 · W4 14/12 – 20/12
*(Shift the dates if the course deadline is different. Keep the order of the weeks.)*

---

## 1. Goal and scope

**Task.** A user types a Vietnamese text query. LUMEN returns a ranked list of
**links to posts on ctsv.uit.edu.vn**, each with its date, a short snippet, and the matched
passage. If the passage came from an attached PDF, the result says so.

**What we build and evaluate:** document-level ranked retrieval, built as a multi-stage pipeline
(lexical → dense → fusion → cross-encoder rerank → metadata boost).

**What we do not build or evaluate:** generated answers. The course asks RAG topics to
focus on retrieval (slide 19, lecture 1). An optional LLM summary can appear in the demo, but it
is not part of the evaluation.

**Corpus:** posts on `ctsv.uit.edu.vn/bai-viet/...`, including notices, decisions,
scholarships and regulations. Many are HTML text. Many others are a one-line body plus an
attached PDF, and **most of those PDFs are scans**.

**Course chapter mapping**

| Component | Chapter |
|---|---|
| Boolean baseline, inverted index, tokenization, Vietnamese word segmentation | Ch1, Ch5 |
| Evaluation: P@k, R@k, MRR, MAP, nDCG, P-R curves, kappa, significance tests | Ch2 |
| LSI baseline (TF-IDF + truncated SVD) | Ch3 |
| BM25 / BM25F with tuned k1 and b | Ch4 |
| Crawling, parsing, OCR, indexing, ranking pipeline, demo | Ch5 |
| Document-type / query-intent classifier used for routing or boosting | Ch6 |

---

## 2. What we already know (pre-checks, 22/11)

- **robots.txt** is the stock Drupal 7 file plus `Crawl-delay: 10`.
  `/bai-viet/`, listing pages and `/sites/default/files/` are allowed. **`/search/` is disallowed.**
  There is no `Sitemap:` line.
- **Listing:** about 330 listing pages.
- **Post types:**
  1. HTML text, sometimes with external links (forms, forum, short links).
  2. A one-line body plus a PDF at `/sites/default/files/uploads/files/YYYYMM/*.pdf`, usually a scan.
  3. Possibly both. Each post has a "Bài viết liên quan" block, no tags and no breadcrumbs.
- **Site search = unranked Boolean AND.** Matching ignores diacritics and results are sorted by date.
  "học bổng" returns results and "học bổng glao" returns nothing.
  - On pilot queries it works for keyword and no-diacritic queries.
  - It fails for natural questions (stopwords break the AND) and for series/time queries.
  - It probably cannot see the content of scanned PDFs (to confirm in W1).
- **Privacy:** some posts and PDFs list student names and MSSV. These must never be committed
  to git, shown on slides, or printed in the report.

---

## 3. System architecture

```
                 ┌──────────── offline ────────────────────────────────────────────┐
listing pages ──▶ crawl (10 s delay, resumable, cached)
                   ├─ post HTML ──▶ boilerplate strip ──▶ body text
                   └─ attachments ─▶ text-layer check ──┬─ text PDF ─▶ pdftotext
                                                        └─ scanned  ─▶ OCR (cached)
                 ──▶ normalize (NFC, lowercase, + diacritic-folded copy)
                 ──▶ word segmentation (underthesea / pyvi)
                 ──▶ metadata extraction (doc type, số văn bản, năm học/HK, date, series)
                 ──▶ docs.jsonl + passages.jsonl
                 ──▶ indexes: Boolean | BM25F | LSI | dense (FAISS)
                 └─────────────────────────────────────────────────────────────────┘
query ──▶ normalize/segment ──▶ intent classifier (doc type)
      ──▶ BM25F top-100  ┐
      ──▶ dense top-100  ┴─▶ RRF fusion ──▶ cross-encoder rerank top-k
      ──▶ metadata boost (recency, series number, intent match)
      ──▶ group passages → posts (MaxP) ──▶ ranked links + snippet + "from PDF" badge
```

### Data model

`data/processed/docs.jsonl`, one post per line:

```json
{
  "doc_id": "bai-viet/<slug>",
  "url": "https://ctsv.uit.edu.vn/bai-viet/<slug>",
  "title": "...",
  "date": "2026-11-19T15:02",
  "body_text": "...",
  "attachments": [{"url": "...", "type": "pdf", "has_text_layer": false,
                   "text": "...", "ocr_engine": "tesseract-vie", "ocr_conf": 0.81}],
  "related": ["bai-viet/<slug>", "..."],
  "meta": {"doc_type": "quyet_dinh", "doc_number": "1487/2026",
           "notice_seq": null, "academic_year": "2026-2027", "semester": "HK1"},
  "content_source": "html|pdf|both"
}
```

`data/processed/passages.jsonl` holds the text split into passages:
`{passage_id, doc_id, field: title|body|attachment, text, text_folded, tokens}`.
Passages are about 150–250 syllables with roughly 30 syllables of overlap. Each title is its own
passage.

### Evaluation files (TREC format, tracked in git)

- `data/eval/queries_{pilot,dev,test}.tsv`: `qid \t query \t style \t notes`
- `data/eval/qrels_{dev,test}.txt`: `qid 0 doc_id grade`, where grade is 0/1/2
- `experiments/runs/<run_id>.trec`: `qid Q0 doc_id rank score run_id`

---

## 4. Systems and ablations

### Systems compared (main results table)

| ID | System | Purpose |
|---|---|---|
| S0 | Boolean AND, diacritic-insensitive, sorted by date (site replica) | Baseline |
| S0s | S0 with stopwords removed from the query | Separates the stopword effect from the ranking effect |
| S1 | BM25 on title + body (no attachments) | Ranked baseline without OCR |
| S2 | BM25F on title + body + attachment text (title boosted) | Effect of OCR |
| S3 | LSI (TF-IDF + SVD) | Ch3 baseline |
| S4 | Dense retrieval (bge-m3 or multilingual-e5) on passages, MaxP | Semantic retrieval |
| S5 | RRF(S2, S4) | Hybrid |
| S6 | S5 + cross-encoder rerank top-k | Rerank stage |
| S7 | S6 + metadata boost + intent routing | **Full LUMEN** |

### Ablations

1. **Fields:** title only / title + body / title + body + OCR (S1 vs S2).
2. **OCR engine:** best vs worst engine from the W1 bake-off, measured by retrieval quality, not only by CER.
3. **Text processing:** syllables vs word segmentation, with vs without diacritic folding, with vs without stopwords.
4. **BM25:** k1 ∈ {0.6 … 2.0}, b ∈ {0.3 … 1.0}, title boost ∈ {1, 2, 3, 5}, tuned on dev only.
5. **Fusion:** RRF (k=60) vs weighted score fusion after min-max normalization.
6. **Rerank depth:** k ∈ {20, 50, 100}, measuring quality and latency.
7. **Passage size:** 128 / 256 / 512 tokens, with MaxP vs FirstP aggregation.
8. **Metadata:** S6 vs S6 + recency vs S6 + series boost vs S6 + intent.

### Query styles (every result is also reported per style)

| Style | Example | Expected winner |
|---|---|---|
| K: keyword | `học bổng khuyến khích học tập HK1` | All roughly equal |
| Q: natural question | `Em cần nộp gì để xét miễn giảm học phí?` | Dense + rerank |
| N: no diacritics, slang, abbreviations | `hb kkht hk1 nam nay co danh sach chua` | Folding + BM25 |
| T: time-bound or series | `thông báo số 2 về danh sách học bổng` | Metadata boost |
| A: answer only inside an attachment | Content found only in a scanned decision | OCR (S2+) |
| X: no relevant post | A topic the site does not cover | Measures false confidence |

---

## 5. Evaluation protocol

- **Size:** about 200 queries, 50 for dev (tuning) and 150 for test (touched only for final runs).
  Aim for at least 25 test queries per style K/Q/N/T/A and about 10 of style X.
- **Writing queries:** write them before looking at any system output. Sources are:
  - each member writes queries from what students actually ask;
  - questions from 5–10 classmates;
  - paraphrases of post titles, never verbatim copies.
  LLM-generated queries may be used only for dev, and this must be disclosed.
- **Relevance labels:** graded 2 = directly answers, 1 = related or partially useful, 0 = not relevant.
  Guidelines go in `docs/judging_guidelines.md`.
- **Pooling:** for each query, take the top 10 of S0, S2, S4 and S6, deduplicate, and judge.
  Run a second pooling round in W3 for new systems (S7), so new runs are not penalized for
  documents nobody judged. Unjudged documents count as non-relevant.
- **Agreement:** 20% of queries are judged by two members. Report Cohen's kappa and resolve
  disagreements by discussion.
- **Metrics:** nDCG@10 (primary), MRR@10, P@5, Recall@10/@100, MAP, plus an interpolated 11-point
  P-R curve for the main systems. Also report the share of queries for which S0 returns nothing.
- **Significance:** paired randomization test or bootstrap (10k samples) between adjacent systems,
  at p < 0.05. Report 95% confidence intervals.
- **Efficiency:** median and p95 query latency per stage, plus index size.

---

## 6. Team roles

| Member | Person | Role | Owns |
|---|---|---|---|
| **A** | Nguyễn Huy Hoàng | Data and OCR | Crawler, parsing, text-layer detection, OCR, metadata extraction, passages |
| **B** | Bùi Diên Gia Bảo | Evaluation and classification | Queries, judging, qrels, metrics/eval harness, intent classifier, error analysis |
| **C** | Đoàn Quốc Kiên (team leader) | Retrieval | Normalization/segmentation, S0–S7, indexing, fusion, reranking, tuning, demo backend |

Everyone writes the report section for their part and presents it.
**Weekly sync on Sunday evening (30 min):** results table, blockers, plan for next week.
Daily async updates in the group chat: done / doing / blocked.

---

## 7. Week-by-week plan

### W1 (23/11 – 29/11): data pipeline and baselines

| ID | Owner | Task | Done when |
|---|---|---|---|
| W1-A1 | A | Listing crawler: all ~330 listing pages → `posts_index.csv` (url, title, date). Waits 10 s, resumable, caches raw HTML. About 1 h runtime. | CSV covers every listing page and the post count is known |
| W1-A2 | A | Choose the corpus window from the counts (target: the last 2–3 years first). Start the post + attachment crawl in the background. | Background job running, with status saved per URL |
| W1-A3 | A | HTML parser: strip boilerplate (header spam, menus, footer), extract body, attachment links and related posts. | 20 random posts checked by eye |
| W1-A4 | A+B | **OCR bake-off** on 15 scanned PDFs: Tesseract `vie`, PaddleOCR (`vi`), VietOCR (+ detector), and optionally a vision LLM (disclose it). Hand-transcribe 3 pages and compute CER/WER. Measure seconds per page. | Engine chosen, recorded in `docs/decisions.md` |
| W1-A5 | A | Text-layer detector (PyMuPDF character count per page) to route PDFs to pdftotext or OCR. | Share of scanned PDFs measured |
| W1-B1 | B | Query style taxonomy, judging guidelines, and 60 pilot queries (20 per member, all styles). | `queries_pilot.tsv`, `judging_guidelines.md` |
| W1-B2 | B | Eval harness: read TREC runs and qrels, compute all metrics overall and per style, run the significance test. Check the numbers against `ranx` or `pytrec_eval`. | `python -m lumen.eval.run --run X --qrels Y` prints the metrics table |
| W1-C1 | C | Normalization: NFC, lowercase, diacritic folding (đ→d), number/date normalization. Word segmentation wrapper. Stopword list. | Unit tests pass |
| W1-C2 | C | **S0** Boolean AND replica. Check it against the site on 10 queries by hand (no scripted use of `/search/`). | Matches the site's behavior on 8 of 10 or better |
| W1-C3 | C | **S1** BM25 on title + body for the posts crawled so far. | Runs on the pilot queries |
| W1-ALL | All | Send the lecturer the one-paragraph scope (retrieval over ctsv posts, Ch2 evaluation, no answer generation). | Reply recorded in `decisions.md` |

**W1 status check (25/11, from the repo, not from a run):**

| ID | Status | Evidence / what is left |
|---|---|---|
| W1-A1 | Code done, **not run yet** | `crawl/listing.py` + `crawl/http.py` + offline tests exist. Run it (~45 min) to produce `posts_index.csv`. |
| W1-A2 | Blocked on A1 | Needs the counts. |
| W1-A3, A4, A5 | Not started | `parse/html.py`, `ocr/*` are stubs. A4 is the critical path: start it first. |
| W1-B1 | Partial | `queries_pilot.tsv` has 11 lines (target 60) and `judging_guidelines.md` is a draft. |
| W1-B2 | Partial | `eval/metrics.py` has the metrics. Missing: TREC/qrels reader, per-style table, significance test, `ranx` cross-check; `run.py` is a stub. |
| W1-C1 | Partial | `normalize()` + `fold()` + test exist. Missing: number/date normalization, word segmentation, stopwords. |
| W1-C2, C3 | Not started | `index/boolean.py`, `index/bm25.py` are stubs. Both can be finished this week without OCR. C3 needs A3 output, so use the A1 titles until then. |
| W1-ALL | Not done | Send the scope paragraph to the lecturer. |

**W1 milestone:** about 500+ posts parsed, OCR engine chosen, S0 and S1 running, eval harness
working on the pilot queries.

### W2 (30/11 – 06/12): full corpus and core retrieval

| ID | Owner | Task | Done when |
|---|---|---|---|
| W2-A1 | A | Run OCR on all scanned PDFs in the background, caching per page to `data/interim/ocr/`. Store confidence. Rotate or deskew low-confidence pages. | 100% of the corpus window has text or is flagged as failed |
| W2-A2 | A | Metadata extraction with regex: `Quyết định số …/YYYY`, `Thông báo số N`, `HK1/HK2`, `năm học 20xx-20xx`, document-type keywords. Deduplicate and group series. | 50 documents checked by hand, ≥90% correct |
| W2-A3 | A | Build `docs.jsonl` and `passages.jsonl` (passage splitting, title passages). | Files built from one command |
| W2-B1 | B | Write the dev + test queries (about 200) before seeing system output. Members swap and review each other's queries. | Frozen `queries_dev.tsv`, `queries_test.tsv` |
| W2-B2 | B (+A, C) | Judging round 1: pool the top 10 of S0, S2, S4 (and S1). Each member judges about 70 queries. Double-judge 20%. | `qrels_dev.txt` complete, kappa reported |
| W2-C1 | C | **S2** BM25F with fields (title, body, attachment) and title boost. Tune k1, b and the boost on dev. | Tuned parameters logged |
| W2-C2 | C | **S3** LSI: TF-IDF + TruncatedSVD (k ∈ {100, 200, 300}), cosine ranking. | Runs on dev |
| W2-C3 | C | **S4** Dense: encode passages with bge-m3 (and multilingual-e5 for comparison) in Colab/Kaggle on GPU. FAISS flat index, MaxP to posts. | Index saved, runs on dev |
| W2-C4 | C | **S5** RRF fusion of S2 and S4. | Runs on dev |

**W2 milestone (Sun 06/12):** a first results table on dev for S0–S5, plus a corpus statistics
table (number of posts, % with PDFs, % scanned, OCR time).

### W3 (07/12 – 13/12): advanced stages and experiments

| ID | Owner | Task | Done when |
|---|---|---|---|
| W3-C1 | C | **S6** cross-encoder rerank (bge-reranker-v2-m3) over the fused top-k, k ∈ {20, 50, 100}. Measure latency. | Runs on dev, depth chosen |
| W3-A1 | A | Metadata boost: recency decay, series-number match (`số 2` ↔ notice_seq 2), academic-year match. Tune on dev. | Gain on style T measured |
| W3-B1 | B | **Intent classifier (Ch6):** label about 300 titles into document types (học bổng, học phí, quyết định khen thưởng/kỷ luật, thi/tốt nghiệp, hoạt động, BHYT, …). Use weak labels from title patterns plus manual fixes. Train TF-IDF + LinearSVC or LogisticRegression on docs and apply it to queries. Report P/R/F1. | Classifier evaluated, used as a boost in S7 |
| W3-C2 | C | **S7** = S6 + metadata boost + intent boost. | Runs on dev |
| W3-B2 | B (+A, C) | Judging round 2: pool new documents from S6 and S7 for test queries and judge them. | `qrels_test.txt` complete |
| W3-ALL | All | Freeze all parameters on dev, then run **every system and ablation once on test**. Run significance tests. | `experiments/results/final_test.csv` |
| W3-STR | C | *Stretch:* fine-tune the reranker on (query, title/passage) pairs from dev plus synthetic queries. Only if S6 is finished by Wed 09/12. | — |

**W3 milestone (Sun 13/12):** results frozen. No parameter changes after this point.

### W4 (14/12 – 20/12): analysis, demo, report, slides

| ID | Owner | Task | Done when |
|---|---|---|---|
| W4-1 | All | Error analysis: each member takes two query styles. Classify failures (OCR error, missing data, vocabulary mismatch, wrong series/year, judging ambiguity) with 3 concrete examples each. | Failure table + examples |
| W4-2 | C | Demo (Streamlit or Gradio): query box, top-10 links, date, snippet, highlighted passage, "from PDF" badge, toggle to compare S0 vs S7. Hide MSSV and names. | Demo runs locally from one command |
| W4-3 | All | Report (see §9), with figures: P-R curves, per-style bar chart, rerank depth vs latency. | Draft by Wed 16/12 |
| W4-4 | All | Slides plus one rehearsal with timing, including likely questions (why AND fails, why OCR, why not generation). | Rehearsed Fri 18/12 |
| W4-5 | All | Code freeze Thu 17/12. README with reproduction steps. Submit on courses.uit.edu.vn. | Submitted |

---

## 8. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| OCR quality too poor (stamps, tables, low-resolution scans) | High | Bake-off in W1. Title as a strong fallback field. Keep OCR confidence. Report the OCR ablation honestly. |
| Crawl too slow (10 s/request) | Medium | Listing first. Narrow window first. One resumable background worker. Never re-fetch. |
| BM25 already near-perfect, so later stages show no gain | Medium | Include hard styles (Q, N, T, A, X). Report per style. A tie on K is an acceptable finding. |
| Judging takes longer than planned | High | Pool depth 10, a judging tool (a simple Streamlit page), and a fixed 2.5 h block per member in W2. |
| No GPU | Medium | Colab/Kaggle for encoding. CPU is fine for BM25/LSI. Lower rerank depth. |
| Site changes or blocks the crawler | Low | Cache everything raw. Polite User-Agent with a contact email. |
| Privacy leak (MSSV, names) | Medium | `data/` is gitignored. Mask on screenshots. No raw student lists in the report. |
| Scope creep (UI, fine-tuning, versioning) | High | Stretch items only after the W3 milestone. |

---

## 9. Report and presentation outline

1. **Introduction:** the problem (finding ctsv posts), why the current Boolean search fails (with examples).
2. **Related work:** Boolean vs ranked retrieval, BM25, LSI, dense retrieval, cross-encoders, RRF.
3. **Data:** crawling under robots.txt, corpus statistics, OCR pipeline, metadata extraction, privacy handling.
4. **Method:** S0–S7, each stage and its course chapter.
5. **Evaluation setup:** queries and styles, pooling, graded labels, kappa, metrics, significance tests.
6. **Results:** main table, per-style breakdown, ablations, efficiency.
7. **Error analysis:** failure categories with examples.
8. **Conclusion and future work:** answer generation, diacritic restoration, versioned regulations, an updating crawler.
9. **Appendix:** GenAI usage disclosure, task split, reproduction steps.

---

## 10. Conventions

- **Language and tools:** Python 3.10+, `src/lumen` package, configuration in `configs/default.yaml`.
- **Runs:** every run writes `experiments/runs/<system>_<yyyymmdd-hhmm>.trec` plus a JSON copy
  of its configuration. Results tables are generated, never typed by hand.
- **Data:** `data/raw` and `data/interim` are never committed. `data/eval` is committed.
- **Test discipline:** tune on dev only. Run on test once, after the W3 freeze.
- **GenAI:** log every substantial use in `docs/genai_usage.md` (tool, purpose, what was kept).
  Do not paste outputs verbatim into the report.
- **Git:** one branch per task ID (e.g. `w2-c3-dense`), small PRs. **Every PR needs at least 1 approval from another
  teammate before it can be merged** (enforced by branch protection on `main`; nobody approves their own PR).

---

## 11. Open decisions (record answers in `docs/decisions.md`)

1. Corpus window: last 2 years vs everything (decide after W1-A1 counts).
2. OCR engine (decide after W1-A4).
3. Dense model: bge-m3 vs multilingual-e5 vs a Vietnamese bi-encoder (decide on dev in W2).
4. Project title: keep "Academic Regulations" in the name, or widen it to student-affairs posts, since the corpus is broader than regulations.
5. Lecturer's reply on scope.
