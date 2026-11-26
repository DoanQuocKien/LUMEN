# W1-C2: site search experiments and hand-test protocol (2026-11-26)

**What this is:** local experiments on how the built-in search of ctsv.uit.edu.vn and daa.uit.edu.vn
matches and orders posts. The goal is to make S0 a faithful copy of it, because S0 stands in for the site search as a baseline.
**What it is not:** an evaluation of relevance. The site search is poor and its results are **never ground truth**,
never qrels, never a reason to call a document relevant.

Rules kept: no network at all, no request to `/search/` or any search URL, no scripted searching (robots.txt
disallows it). Every site number below was typed by hand by a team member (`data/eval/site_search_observations.tsv`).

Reproduce (reads `docs.jsonl`, writes nothing):

```
python -m lumen.eval.site_search --docs <main checkout>/data/processed/docs.jsonl
python -m lumen.eval.site_search --docs ... --predict data/eval/site_search_protocol.tsv
```

## 1. The site is Drupal 7 core search

The cached pages (`data/raw/html`, `data/raw/daa/html`) of both sites load `Drupal.settings`,
`misc/form-single-submit.js`, `modules/search/search.css` and a `search_block_form`. Neither loads assets from
`search_api`, `apachesolr` or `custom_search`. So the search box is very likely **Drupal 7 core node search**.
The behaviour of that module is documented (PR #22, `docs/research_search_approaches.md`, sources on api.drupal.org):

| D7 rule | Effect on our queries |
|---|---|
| `search_simplify()` merges digit groups separated only by punctuation | "24/11" -> `2411`, "24/11/2025" -> `24112025`, "2026-2027" -> `20262027` |
| single `.`, `_`, `-` are deleted, other punctuation is a word break | "ĐHQG-HCM" -> `đhqghcm`; URL slugs become one long word |
| no accent removal in code; matching uses the MySQL collation | accent-insensitive in practice; whether `đ` = `d` is unknown |
| all words are ANDed; `OR` (uppercase) makes a group; `-word` excludes; `"..."` is a phrase; lowercase `and` is ignored | |
| index ignores words under 3 characters (numbers exempt); a query with only short words errors | short words in a longer query are still checked against the stored text |
| ranking: weights default to 0; relevance = sum of tf (title in `<h1>` counts 26x) x log10(1 + 1/total) | not newest-first; `recent` needs an admin setting |
| indexing happens only on cron, 100 nodes per run by default | new posts can be missing for a while |

`lumen.eval.site_search` implements the matching rules (`tok(..., numbers="d7")`) and an approximate relevance
score (`d7_scores`, title weight 26, body 1, the D7 "focus" decay, no other HTML tag weights).

## 2. Method

- Corpus: the 617 ctsv docs in `docs.jsonl` (mostly 2024-11 to 2026-11, plus about 60 older reference pages).
  daa observations are left out of the scoring: the daa site returns only programme pages, which are not in our corpus.
- The site indexes everything we have **plus older posts**. So for a variant to fit, its count on our corpus must be
  **at most** the site count. A site count of `0` must give `0`. `many` (more than one page) sets no limit.
- Known site hits: 14 (query, doc) pairs the human confirmed in our window: P01 (6 docs, "S0 returns the same 6"),
  P05 (1), P07 (7, inferred from "site extras are older"). A variant should find them.
- Each variant changes one thing in S0 (AND, title+body, diacritics folded with đ->d, dates rewritten to ISO).

## 3. Matching results (ctsv, 20 queries)

| variant | fits (of 20) | over-matches | excess docs | zeros kept (of 5) | known hits (of 14) | verdict |
|---|---|---|---|---|---|---|
| **S0** (current) | 19 | P77 | 2 | 5 | 14 | good except P77 |
| OR | 8 | 12 queries | 5408 | 0 | 14 | rejected |
| min-should-match 50% | 9 | 11 queries | 1244 | 1 | 14 | rejected |
| min-should-match 75% | 12 | 8 queries | 155 | 4 | 14 | rejected |
| title only | 20 | - | 0 | 5 | **1** | rejected (misses known hits) |
| body only | 19 | P77 | 2 | 5 | 13 | worse than title+body |
| + attachment text | 17 | P64, P77, P88 | 11 | 5 | 14 | rejected (see below) |
| + attachment file name | 19 | P77 | 2 | 5 | 14 | no effect, cannot tell |
| exact diacritics | 20 | - | 0 | 5 | **6** | rejected (P07 has no accents and the site found it) |
| fold, keep đ | 19 | P77 | 2 | 5 | 14 | cannot tell |
| S0s (drop stopwords) | 17 | P05, P04, P77 | 21 | 4 | 14 | rejected |
| drop words < 3 chars | 18 | P04, P77 | 7 | 4 | 14 | rejected (as found before) |
| numbers as written (no ISO dates) | 19 | P77 | 2 | 5 | 14 | no effect |
| phrase (consecutive words) | 20 | - | 0 | 5 | **0** | rejected |
| **D7 model** (d7 tokens, đ=d) | **20** | - | 0 | 5 | 14 | **best** |
| D7 model, keep đ | **20** | - | 0 | 5 | 14 | equal best |
| D7 model + attachment text | 18 | P64, P88 | 2 | 5 | 14 | rejected |

Per-query counts (site / S0 / D7): P01 6/6/6, P07 9/7/7, P05 7/1/1, P04 0/0/0, P61 0/0/0, P64 2/0/0, P71 0/0/0,
P72 0/0/0, P77 **1/3/0**, P85 2/0/0, P88 1/0/0, P89 0/0/0; for the `many` queries D7 returns 0 to 53 (S0 0 to 56; P79 is 0 for both, its site hits are all old).
The full 17-variant table is printed by the command above.

**P77 is explained.** S0's three P77 hits are tables: "24" and "11" are row numbers, "lê" (folds to "le", matching
"lễ") is a surname, and "nghi" is a given name. Under D7 the query token is `2411`, which none of them contain, so
D7 returns 0 in our window. That fits the site's single 2023 post (outside our window), which presumably writes
"24/11" without a year. Same problem in another form: S0 also matches words inside URL slugs (daa posts that link to
`mot-so-quy-trinh-danh-cho-sinh-vien` match the query "Một số quy trình dành cho sinh viên"). D7 joins slugs into one
word, so they do not match.

**Attachments are probably not indexed.** With PDF text added, P64 returns 3 in-window posts (2026-07, 2018, 2019)
where the site lists only 2 (2017 and 2012), and P88 returns 2 (2018, 2019) where the site lists a single 2020 post.
P85 is within the count but returns a 2016 post the site did not list. This matches stock D7, which indexes the
rendered node (an attached file shows only its name).

## 4. Order

The only fully recorded order is P01 (6 results, site: 2026-11-03, 2026-07-08, 2026-10-19, 2026-11-19, 2026-07-08, 2019-03-20).

| ranking of the same 6 docs | order (dates) | Kendall tau vs site |
|---|---|---|
| date, newest first (current S0) | 2026-11-19, 2026-11-03, 2026-10-19, 2026-07-08, 2026-07-08, 2019-03-20 | +0.47 |
| **D7 relevance** (title x26, idf, focus decay) | 2026-11-03, 2026-07-08, 2026-10-19, 2026-11-19, 2026-07-08, 2019-03-20 | **+1.00** |
| tf-idf over body | 2026-10-19, 2026-07-08, 2026-11-03, 2026-11-19, 2026-07-08, 2019-03-20 | +0.60 |
| tf-idf over title | 2026-07-08, 2026-11-03, 2026-11-19, 2026-07-08, 2026-10-19, 2019-03-20 | +0.60 |
| BM25 title+body | 2026-07-08, 2026-10-19, 2026-11-03, 2019-03-20, 2026-11-19, 2026-07-08 | +0.47 |

Ablation of the D7 score: a title weight of 26 or more and the idf factor are both needed for tau = 1.
Title weight 11 gives 0.87, no idf gives at most 0.60, and the focus decay changes nothing here. A random order matches
exactly with probability about 1/360, but this is **one query**, and we cannot tell the two 2026-07-08 posts apart in
the notes (we assume the matching assignment).
It also fits the qualitative notes. For P13, D7 puts the 2025-12/2026-01 BHYT 2026 notices first, then two 2020
"[NHẬP HỌC]" guides ("BHYT 2026 notices mixed with a 2020 enrolment guide"). For P03, D7 ranks "Thông báo cập nhật
BHYT - Chấm điểm rèn luyện" posts high, and the site's top hit is a 2022 "BHYT update".

## 5. Not testable locally

- **Index freshness (cron, 100 nodes per run).** Model: only a subset of recent posts is searchable. That can only
  lower site counts, so it is consistent with every observation and cannot be refuted from our data. One bound: P01
  found a 2026-11-19 post a week later, so the ctsv index was at most about 7 days behind. Hand tests X26, X27.
- **daa.** The best explanation is a daa index that stopped being updated (only old static pages are indexed). An
  excluded content type is the other candidate. Hand tests X28 and X29.
- **đ vs d.** Both D7 variants fit equally, because no observed query needs đ (P09 "dang" also matches "dạng").
  Hand tests X08 to X10.
- Other D7 inputs we do not have: comments, taxonomy terms, the "submitted by" line, link/bold tag weights,
  the site's ranking weights.

## 6. Conclusions

1. The site search behaves like stock Drupal 7 core search: AND over title+body, accent-insensitive, no attachment
   text, digit groups and dashed words joined into single tokens, relevance order. The D7 model fits all 20
   observations, keeps the 14 known hits and fixes P77. S0 fits 19.
2. Rejected: OR / min-should-match, title-only, phrase matching, exact diacritics, dropping stopwords, dropping short
   words, indexing attachment text. Date sort (current S0) does not reproduce the site order; D7 relevance does on P01.
3. Proposed S0 change (separate PR after the hand test, since `retrieve/systems.py` is outside this task): tokenise
   with `tok(..., numbers="d7")` for S0 only, and order by `d7_scores` instead of date. Keep our own systems (S1+)
   on S0-style tokens plus a date field: for retrieval we want "24/11" to match "24/11/2025".
4. Uncertainty is large: n = 20, only 12 queries have exact counts, 5 are zeros, the site has years of posts we do
   not have, and the order evidence is one query. The D7 rules are from documentation, not from the site's own config.

## 7. Hand-test protocol (`data/eval/site_search_protocol.tsv`)

30 new queries (X01 to X30), each aimed at one hypothesis. **Type each query by hand** into the search box of ctsv
and of daa, exactly as written: quotes, dashes, `OR` and capitals included. Do not use scripts, URL tools or the
`/search/` address bar.

Columns given: `tests` (hypothesis), `if_d7_core` (what stock D7 should do), and predicted **in-window** counts on our
corpus: `s0_*` = current S0; `d7_*` = D7 model with đ=d (the operators in X14 and X16 to X21 were applied by hand);
`d7k_ctsv` = D7 with đ different from d; `att_ctsv` = S0 plus PDF text. The site also has older posts, so a site
count **below** a prediction refutes that model. A count above it does not.

Paste format: fill the empty columns in the TSV (keep the tabs), one row per query:

| column | what to write |
|---|---|
| `ctsv`, `daa` | exact count: D7 shows 10 per page, so count = 10 x (pages - 1) + results on the last page. `0` if none, `err` if an error message appears (copy the message into `notes`). |
| `ctsv_top`, `daa_top` | first 3 results as `YYYY-MM-DD title start` separated by ` \|\| `; first 10 for X12 and X13 |
| `notes` | anything odd; date you typed it |

Decision rules:

| rows | D7 predicts | S0 predicts |
|---|---|---|
| X01 / X02 (24/11 vs 24/11/2025) | no 2025-2026 posts for X01; X02 is not a subset of X01 | X01 ⊇ X02, both with 20+ recent posts |
| X03 / X04 (1005/2024 vs 1005) | the "Quyết định số 1005/2024" post appears for X03, not for X04 | it appears for both |
| X05 (2026-2027) | only posts that write it without spaces | posts with both numbers anywhere |
| X06 / X07 (ĐHQG-HCM vs đhqghcm) | same count | X07 = 0 |
| X08 / X09 / X10 (đ vs d) | đ=d: all equal. đ≠d: X08 far below X10 | all equal |
| X11 (wrong accents) | same as "học bổng" | same |
| X12 / X13 (case; order) | same list; top 5 in window: 2019-12 BHYT guide, 2026-01, 2025-12, 2025-01, 2026-07 | newest first |
| X14 (lễ) | error, no results | many |
| X15 (stopwords only) | many | many (S0s: 0) |
| X16 / X17 (OR vs or) | X16 = toeic ∪ ielts; X17 about 0 | both 0 |
| X18 (-khuyến) | học bổng posts without khuyến (123 in window) | posts with khuyến (44) |
| X19 / X20 (phrase, reversed) | X19 < unquoted, X20 about 0 | both = unquoted |
| X21 (lowercase and) | = unquoted query (39) | 0 |
| X22 / X23 (prefix, hyphen) | about 0 / about 0 | about 0 / many |
| X24 / X25 (PDF-only words) | the 2025-03 "Bệnh Sởi" / 2026-02 NVIDIA posts absent | absent (present only if attachments are indexed) |
| X26 (long exact title, 2026-11-19) | found (fresh index) | found |
| X27 (sinh viên) | site count / listing size = index coverage | |
| X28 / X29 (daa) | stale daa index: X28 finds no 2026 announcement; X29 finds the 2014 page | |
| X30 (single rare body word) | whole-word matches only | same |

After filling, `python -m lumen.eval.site_search --docs ... --obs data/eval/site_search_protocol.tsv` scores the
plain-word rows the same way as section 3. Read the operator rows (X14, X16 to X21) by eye.

## 8. Open questions

- Is `đ` = `d` on the site (X08)? This decides whether S0 should fold đ.
- Does the site rank by relevance only, or with sticky/promote? X13's order will show it, and P01 is only one query.
- Why does daa search show no announcements: stale index or a content type that is not indexed?
- Is ctsv's index complete? X27 vs the size of the listings.
- If the hand test confirms D7, should S0 use the D7 relevance order? The S0 scores in our nDCG tables would change.

## References

- PR #22, `docs/research_search_approaches.md` (branch `w1-c-research-notes`): D7 `search_simplify`, query parser,
  `node_ranking`, cron indexing, with api.drupal.org sources.
- `docs/s0_site_check.md`: the first S0 vs site comparison and the 20 observations.
- Code: `src/lumen/eval/site_search.py`; test: `tests/test_site_search.py`.
