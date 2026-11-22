# LUMEN — Project Specification

**Project:** LUMEN — Legal-University Multi-stage Evidence Navigation
**Course:** CS419 Information Retrieval, UIT · group of 3
**Version:** v1, 2026-11-22 · **Status:** draft, pending lecturer approval
**Related:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) explains *how and when* we build this.
This document defines *what* we build and how we judge whether it works.

---

## 1. Problem statement

UIT's Student Affairs Office (Phòng Công tác Sinh viên) publishes notices, decisions, scholarship
announcements and regulations on `ctsv.uit.edu.vn`. Students struggle to find the right post
for three reasons:

1. **Boolean AND search.** The site's search returns only posts that contain *every* query word,
   ordered by date. One extra word ("em", "gì", a typo) gives zero results, so natural questions fail.
2. **Content locked in scanned PDFs.** Many posts are a single sentence plus an attached scan.
   The useful text (who, what, deadline, decision number) is not searchable at all.
3. **Repeated series.** Notices repeat every semester and come in numbered series
   ("Thông báo số 1, số 2…"). Nothing ranks the right semester or the latest notice first.

**LUMEN** is a ranked retrieval system that takes a Vietnamese text query and returns the most
relevant posts as links, with evidence showing why each post matched.

---

## 2. Goals and non-goals

### Goals
- **G1.** Return a ranked list of relevant ctsv posts for Vietnamese text queries, including
  natural questions, no-diacritic or abbreviated queries, and time/series-specific queries.
- **G2.** Make the content of scanned PDF attachments searchable through OCR.
- **G3.** Show measurable improvement over the site's current search using standard IR evaluation (Ch2).
- **G4.** Quantify what each stage contributes (BM25, OCR, dense retrieval, fusion, reranking,
  metadata/intent boosting) through ablations.

### Non-goals
- **NG1.** Generating natural-language answers. An LLM summary may appear in the demo but is never evaluated.
- **NG2.** Image or voice queries.
- **NG3.** A production deployment or a continuously updating crawler.
- **NG4.** Legal interpretation of regulations or resolving conflicts between regulation versions.
- **NG5.** Sources outside `ctsv.uit.edu.vn` (e.g. daa.uit.edu.vn, the forum), unless the scope is extended in `decisions.md`.

---

## 3. Users and use cases

**Primary user:** a UIT student looking for an announcement, decision or regulation.
**Secondary users:** the course lecturer and classmates, who evaluate the system and its results.

| ID | Use case | Example query |
|---|---|---|
| UC1 | Find a specific notice by topic keywords | `học bổng khuyến khích học tập HK1 2026-2027` |
| UC2 | Ask a natural question about a procedure | `Em cần nộp giấy tờ gì để xét miễn giảm học phí?` |
| UC3 | Search quickly without diacritics or with abbreviations | `hb kkht hk1 nam nay co danh sach chua` |
| UC4 | Find the latest notice in a series or the right semester | `thông báo số 2 về danh sách học bổng` |
| UC5 | Find a decision whose content exists only in a scanned PDF | `thong bao cu sinh vien thi an toan thong tin` |
| UC6 | Learn that nothing relevant exists, without being misled | A topic the site doesn't cover |

---

## 4. Data specification

### 4.1 Source
- **Site:** `https://ctsv.uit.edu.vn` (Drupal 7).
- **Included:** post pages under `/bai-viet/<slug>` and their attachments under
  `/sites/default/files/uploads/files/YYYYMM/` (PDF; DOCX/XLSX if present).
- **Excluded:** `/search/` and every other path disallowed by robots.txt, external links
  (Google Forms, forum, short links), images and media.
- **Corpus window:** decided after the listing crawl (default: the last 2 years; the site has about 330 listing pages in total).

### 4.2 Collection constraints
| ID | Constraint |
|---|---|
| DC1 | Follow robots.txt: at least 10 s between requests, a single worker, no `/search/`. |
| DC2 | Identify the crawler with a User-Agent that names the course project and a contact email. |
| DC3 | Cache every response. Never fetch the same URL twice during a crawl. |
| DC4 | Crawls must be resumable, with status stored per URL. |

### 4.3 Document model
One **document** = one post, identified by `doc_id = "bai-viet/<slug>"`. It has these fields:

| Field | Source | Notes |
|---|---|---|
| `url` | listing | The link shown to the user |
| `title` | post page | Clean, human-written. Strongest field |
| `date` | post page | Publication date and time |
| `body_text` | post page | HTML body without the site template |
| `attachments[].text` | PDF text layer or OCR | Includes OCR engine and confidence |
| `related` | "Bài viết liên quan" block | Links to other posts |
| `meta.doc_type` | classifier and rules | e.g. `hoc_bong`, `quyet_dinh`, `hoc_phi`, `thi`, `hoat_dong`, `bhyt` |
| `meta.doc_number` | regex | e.g. `1487/2026` |
| `meta.notice_seq` | regex | N in "Thông báo số N" |
| `meta.academic_year`, `meta.semester` | regex | e.g. `2026-2027`, `HK1` |
| `content_source` | derived | `html`, `pdf` or `both` |

Documents are split into **passages** (about 200 syllables, 30 overlapping) for dense retrieval
and reranking. A document's score is the score of its best passage (MaxP).
Exact schemas are in IMPLEMENTATION_PLAN.md §3.

### 4.4 Privacy
| ID | Requirement |
|---|---|
| PR1 | Raw and processed data, which can contain student names and MSSV, are never committed to git. |
| PR2 | Slides, the report, screenshots and the demo must not show student names or MSSV. Mask them if needed. |
| PR3 | Data is used only for this course project and deleted or archived privately afterwards. |

---

## 5. Functional requirements

### 5.1 Data pipeline
| ID | Requirement | Priority |
|---|---|---|
| FR1 | Crawl all listing pages and record `url, title, date` for every post. | Must |
| FR2 | Fetch post pages and attachments within the corpus window. | Must |
| FR3 | Remove the site template (menus, header links, footer, listing pagination) from post bodies. | Must |
| FR4 | Detect whether each PDF page has a text layer. Extract text directly when it does, and run OCR otherwise. | Must |
| FR5 | Cache OCR output per page and store a confidence score. | Must |
| FR6 | Extract metadata: document number, notice sequence, academic year, semester. | Should |
| FR7 | Split documents into passages with configurable size and overlap. | Must |

### 5.2 Query processing
| ID | Requirement | Priority |
|---|---|---|
| FR8 | Accept free-text Vietnamese queries of 1–50 words. | Must |
| FR9 | Normalize text (NFC, lowercase) and match queries with or without diacritics. | Must |
| FR10 | Support Vietnamese word segmentation as a configurable option. | Should |
| FR11 | Extract time and series cues from the query (HK, năm học, "số N"). | Should |
| FR12 | Predict the query's intended document type (Ch6 classifier). | Should |

### 5.3 Retrieval and ranking
| ID | Requirement | Priority |
|---|---|---|
| FR13 | **S0:** reproduce the site's Boolean AND search (diacritic-insensitive, sorted by date) as a baseline. | Must |
| FR14 | **S1/S2:** BM25 over title + body, and BM25F over title + body + attachment text, with field weights. | Must |
| FR15 | **S3:** LSI (TF-IDF + truncated SVD). | Should |
| FR16 | **S4:** dense passage retrieval with a multilingual embedding model. | Must |
| FR17 | **S5:** fuse lexical and dense rankings (RRF by default). | Must |
| FR18 | **S6:** rerank the top-k fused candidates with a cross-encoder. k is configurable. | Must |
| FR19 | **S7:** apply recency, series-number, academic-year and intent boosts on top of S6. | Should |
| FR20 | Any system S0–S7 can be selected by name for a given query. | Must |

### 5.4 Output
| ID | Requirement | Priority |
|---|---|---|
| FR21 | Return the top-k posts (default 10). Each result has rank, title, URL, date, score, a snippet, the best matching passage, and the field it came from. | Must |
| FR22 | Mark results whose best evidence came from an attachment (e.g. a "from PDF" badge). | Must |
| FR23 | Group passages so each post appears at most once in the results. | Must |
| FR24 | Write results for a query set as a TREC run file. | Must |

### 5.5 Interfaces
| ID | Requirement | Priority |
|---|---|---|
| FR25 | Python API: `search(query: str, system: str = "S7", k: int = 10) -> list[Result]`. | Must |
| FR26 | CLI to build the corpus and indexes, run a system over a query file, and evaluate a run. | Must |
| FR27 | Web demo (Streamlit/Gradio): query box, results list, and a side-by-side S0 vs S7 comparison. | Should |
| FR28 | An optional generated summary in the demo, clearly labelled as not evaluated. | Could |

`Result` fields: `rank, doc_id, url, title, date, score, snippet, evidence_text, evidence_field
(title|body|attachment), system`.

---

## 6. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR1 | Reproducibility | Every number in the report can be regenerated from code, configuration and the cached data with the documented commands. |
| NFR2 | Reproducibility | Each run saves its configuration (model names, parameters) next to its TREC file. Fixed random seeds. |
| NFR3 | Efficiency (target) | S0–S2: median latency under 200 ms per query. S6/S7 at depth 50: median under 3 s on a GPU. CPU latency is measured and reported. |
| NFR4 | Resources | Must run on a student laptop (16 GB RAM) for querying. GPU (Colab/Kaggle) is used only for encoding and reranking experiments. |
| NFR5 | Robustness | A failed OCR page or a broken attachment must not stop the pipeline. It is logged and skipped. |
| NFR6 | Maintainability | Python 3.10+, the `src/lumen` package, unit tests for normalization, metrics, fusion and metadata extraction. |
| NFR7 | Ethics and compliance | Follows DC1–DC4 and PR1–PR3. GenAI use is logged in `docs/genai_usage.md` and not copied verbatim. |

---

## 7. Evaluation specification

### 7.1 Test collection
- **Queries:** about 200 Vietnamese queries, split into 50 dev and 150 test. They are written before seeing any system output.
- **Styles:** K keyword · Q natural question · N no diacritics/slang/abbreviation · T time/series ·
  A answer only in an attachment · X no relevant post. Target at least 25 test queries per style K–A and about 10 for X.
- **Relevance:** graded 2 (directly answers) / 1 (related, partly useful) / 0 (not relevant), following `docs/judging_guidelines.md`.
- **Pooling:** top 10 from several systems per query, with a second round for later systems. Unjudged documents count as non-relevant.
- **Agreement:** 20% of queries are judged by two people, and Cohen's kappa is reported.

### 7.2 Metrics
- **Primary:** nDCG@10.
- **Secondary:** MRR@10, P@5, Recall@10, Recall@100, MAP, the interpolated 11-point P-R curve, and the share of S0 queries with no results.
- **Efficiency:** median and p95 latency per stage, and index size.
- **OCR quality:** CER/WER on hand-transcribed sample pages.
- **Classifier:** macro precision/recall/F1 on held-out labeled titles and queries.
- **Significance:** paired randomization or bootstrap test (10,000 samples, p < 0.05), with 95% confidence intervals.

### 7.3 Experimental rules
- Tune every parameter on dev only. Run the test set once, after the parameter freeze.
- Report every metric both overall and per query style.
- Report negative results (e.g. a stage that doesn't help) as findings, not omissions.

---

## 8. Acceptance criteria

The project meets its specification when all **Must** criteria hold.

| ID | Criterion | Priority |
|---|---|---|
| AC1 | The corpus covers the chosen window, and the report gives statistics on posts, attachments, the scanned share and OCR coverage. | Must |
| AC2 | S0 matches the site's search behaviour on at least 8 of 10 manually checked queries. | Must |
| AC3 | The full system (S6 or S7) beats S0 on test nDCG@10 overall, with p < 0.05. | Must |
| AC4 | The full system beats S0 on styles Q and A, with p < 0.05 for each. | Must |
| AC5 | Adding attachment text (S1 → S2) is measured, and its effect on style A is reported with a confidence interval. | Must |
| AC6 | An ablation table covers at least: fields, fusion, rerank depth, and diacritic folding. | Must |
| AC7 | The test collection has at least 150 test queries with graded qrels and a reported kappa. | Must |
| AC8 | Every reported number can be reproduced from the repository (NFR1). | Must |
| AC9 | The metadata/intent boost (S7) is evaluated on style T against S6. | Should |
| AC10 | The demo shows the S0 vs S7 comparison on live queries. | Should |
| AC11 | The error analysis classifies failures with at least 3 examples per category. | Should |

There is no fixed target score: the corpus and queries are new, so the comparison with S0 and the
per-stage gains are the result.

---

## 9. Constraints and assumptions

**Constraints**
- Team of 3, about 4 weeks, with the course deadline fixed by the lecturer.
- Course rule: RAG-style topics must focus on retrieval, not generation.
- Course rule: GenAI may be used but not copied verbatim. Shared projects across courses need the lecturer's approval.
- `Crawl-delay: 10` makes a full crawl take many hours. It runs in the background.
- No paid APIs are required. Free GPU (Colab/Kaggle) is the only accelerator assumed.

**Assumptions** (checked during W1, recorded in `decisions.md`)
- The listing pages give post URLs, titles and dates in a parseable form.
- Most attachments are scanned PDFs, and Vietnamese OCR is good enough for retrieval even if it is imperfect.
- The site's structure doesn't change during the project.
- The lecturer approves the scope: retrieval over ctsv posts with no generated answers.

---

## 10. Deliverables

| Deliverable | Format | Due |
|---|---|---|
| Source code and README with reproduction steps | Git repository | Code freeze (W4) |
| Test collection: queries, qrels, judging guidelines | `data/eval/`, `docs/` | End of W3 |
| Run files and results tables | `experiments/` | End of W3 |
| Project report | PDF on courses.uit.edu.vn | Course deadline |
| Presentation slides | PDF/PPTX on courses.uit.edu.vn | Presentation date |
| Demo | Streamlit/Gradio app, run locally | Presentation date |

---

## 11. Glossary

| Term | Meaning |
|---|---|
| Boolean AND retrieval | Returns only documents that contain every query term, without ranking by relevance |
| BM25 / BM25F | Probabilistic ranking function (Ch4). BM25F weights fields such as title and body separately |
| LSI | Latent Semantic Indexing: TF-IDF matrix reduced with SVD (Ch3) |
| Dense retrieval | Ranking by similarity of neural embeddings of query and passage |
| RRF | Reciprocal Rank Fusion: combines rankings by summing 1/(k + rank) |
| Cross-encoder | A model that reads query and passage together and outputs a relevance score. Used for reranking |
| MaxP | A document's score is the score of its best passage |
| Pooling | Judging only the union of the top-ranked documents from several systems |
| qrels | Relevance judgments: (query, document, grade) |
| HB KKHT | Học bổng khuyến khích học tập (academic encouragement scholarship) |
| ĐUT | Điểm ưu tiên (priority points used in scholarship ranking) |
