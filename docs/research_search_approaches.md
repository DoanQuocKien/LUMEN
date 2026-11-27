# Research notes: how others handle search like ours (W1-C)

Date: 2026-11-26. Web research on methods only; the UIT sites were not crawled or searched. Source tags: **[V]** = primary page read in full or the relevant part; **[S]** = only seen in a search snippet or abstract (treat as lead); **UNVERIFIED** = could not confirm.

## A. Drupal 7 core search: what can explain our observations

**Short answer.** The site behaviour we see is what stock `search.module` does. Queries are AND by default, results are capped at 10 per page, ranking has no recency unless the admin switches it on, and numbers/dates are glued into one token. That last point is a good candidate for P77.

| Question | Finding | Source |
|---|---|---|
| Query semantics | Terms are ANDed. Uppercase `OR` makes an OR group, lowercase `or` is a normal word, `"..."` is a phrase, `-word` excludes. `search_and_or_limit` (default 7) caps the number of AND/OR terms. | [V] api.drupal.org `SearchQuery::parseSearchExpression` 7.x: https://api.drupal.org/api/drupal/modules!search!search.extender.inc/function/SearchQuery%3A%3AparseSearchExpression/7.x |
| Min word size | Index side: words shorter than `minimum_word_size` (default 3) are not indexed; numbers are exempt. Query side: the parser page does not say. A search snippet of older reports says node search errors with "at least one positive keyword with 3 characters or more", so short query words are probably dropped too. Our own test (S0 with min length 3 made P77 return 60) shows it does not fit the site exactly. | [V] https://api.drupal.org/api/drupal/modules!search!search.module/function/search_index/7.x ; [V] https://api.drupal.org/api/drupal/modules!search!search.admin.inc/function/search_admin_settings/7.x ; query side [S] https://www.drupal.org/node/1063188 |
| Tokenising | `search_simplify()`: decode entities, lowercase, optional `hook_search_preprocess`, then **digit groups separated only by punctuation are merged**: `20/03/1984` and `20-03-1984` both become `20031984`. Dots, underscores, dashes are deleted (`a.b` becomes `ab`); other punctuation is a word boundary; words are cut at 50 chars. | [V] https://api.drupal.org/api/drupal/modules!search!search.module/function/search_simplify/7.x |
| Diacritics | `search_simplify()` does **not** remove accents in D7. Accent-insensitive matching came from the MySQL collation of the index table; core only made it collation-independent in Drupal 8. So the site's diacritic-insensitivity is a DB side effect and may not cover every Vietnamese letter or decomposed (NFD) text. Whether `đ` equals `d` under the site's collation is **UNVERIFIED**: test by hand ("diem" vs "điểm" in a word with đ). | [V] https://www.drupal.org/node/2447357 |
| Ranking | Each factor has an admin weight `node_rank_<name>`, default 0 meaning off. Factors: `relevance` (about 0.15 on average), `sticky`, `promote`, and `recent` (only when `node_cron_last` is non-zero): `2^((max(created,changed) - node_cron_last) * 6.43e-8)`, a 6-month half-life. Core D7 has no title boost beyond HTML tag weights at index time (headings highest). Which weights this site set is **UNVERIFIED** (the weights are admin settings we cannot see; infer from hand-tested result order, which was not newest-first). | [V] https://api.drupal.org/api/drupal/modules!node!node.module/function/node_ranking/7.x ; [V] https://api.drupal.org/api/drupal/modules!node!node.module/function/_node_rankings/7.x ; [V] search_index page above for tag weights |
| Index freshness | Nodes are indexed only by cron: those with no `search_dataset` row or `reindex` flag set, ordered by `reindex` then `nid`, `search_cron_limit` per run (default 100, admin choices 10 to 500). Only `status = 1` nodes and `node_access` rules apply at query time. If cron is rare or the batch is small, new posts are missing until a later run. | [V] https://api.drupal.org/api/drupal/modules!node!node.module/function/node_update_index/7.x ; [V] https://api.drupal.org/api/drupal/modules!node!node.module/function/node_search_execute/7.x |

**What this says about our two mysteries (hypotheses, not confirmed):**
- **P77** ("24/11"): a post that writes "24/11/2025" is indexed as `24112025`, which does not match query token `2411`. Only posts that contain "24/11" without a year (or "24-11") match. That would explain 1 old post versus our 3 recent ones. Other possible causes: stale index (cron lag), and short words "có", "lễ" dropped at query time. Test: type "24/11/2025" (with year) by hand and see if the 3 recent posts appear.
- **daa**: `node_search_execute` searches only nodes in the index. If daa announcements are not nodes of an indexed type, are unpublished/access-restricted, or are never reindexed, search shows only static programme pages. Content-type exclusion is not a core D7 setting (the `type` option exists only for advanced search), so the likely cause is a different entity type or indexing never run for them. **UNVERIFIED**.

Design consequence: our "S0" baseline is right to be AND + diacritic-folded; add the digit-merging rule only if we want fidelity, not for our own retrieval (we should do the opposite and keep dates as separate tokens plus a date field).

## B. Diacritics, slang, tokenisation

**Short answer.** Fold diacritics for recall but keep the original text in a second field for ranking; restore accents or expand slang on the query side; there is **no published head-to-head of syllable vs word-segmented BM25** for Vietnamese, so we must run it ourselves.

- Folding: Elastic documents the `asciifolding` filter and the multi-field pattern (original field plus `.folded` subfield) because folding loses exact matches. [V] https://www.elastic.co/guide/en/elasticsearch/reference/8.19/analysis-asciifolding-tokenfilter.html ; [S] duydo Vietnamese analyzer plugin example with `preserve_original`: https://github.com/duydo/elasticsearch-analysis-vietnamese ; [S] a Discourse thread argues folding Vietnamese causes false matches (many unrelated words differ only by marks): https://meta.discourse.org/t/do-not-strip-diacritics-for-search-in-vietnamese/96050 (page returned 403, snippet only).
- Accent restoration: seq2seq models exist, e.g. `nrl-ai/vn-diacritic-vit5-base` (226M, apache-2.0, ViT5 fine-tune; no accuracy figures read). [V] https://huggingface.co/nrl-ai/vn-diacritic-vit5-base ; transformer restoration paper IEEE Access 2023 [S] https://doaj.org/article/9171749cb1a84aa5a6c02605994dde70 ; hierarchical transformer for Vietnamese spelling [S] https://arxiv.org/abs/2105.13578. Restoration adds a model call and can hallucinate; folding is cheaper and deterministic.
- Slang/teencode: ViLexNorm (EACL 2024, UIT) has 10,467 comment pairs, CC BY-NC-SA 4.0; best system only reaches 57.74% error reduction over leave-as-is, so full learned normalisation is weak and a hand-built dictionary for our 30 to 50 student abbreviations is the realistic route. [V] https://aclanthology.org/2024.eacl-long.85 (via https://arxiv.org/abs/2401.16403).
- Tokenisation: the multi-stage Vietnamese legal paper ran BM25+ on VnCoreNLP-segmented text but did not report a syllable ablation for BM25; for neural models, word-level wins for PhoBERT-based and syllable-level for ViBERT. [V] https://ar5iv.labs.arxiv.org/html/2209.14494 . A 2026 UIT competition solution indexed BM25 on accent-folded **syllable bigrams** (no segmenter) with document numbers kept whole, getting Recall@5 85.8 / MRR 70.3 for BM25 alone. [V] https://github.com/monster1909/vietnamese-legal-retrieval . A 2025 system used Pyvi before BM25 and the bi-encoder. [V] https://arxiv.org/html/2507.14619v1 . AAAI 2025 argues word segmentation is not suited to Vietnamese text understanding (model-side, not IR). [S] https://ojs.aaai.org/index.php/AAAI/article/view/34581 . Segmenter tools: VnCoreNLP [V-abstract] https://arxiv.org/abs/1801.01331 .

## C. Baselines, models, benchmarks

**Short answer.** BM25 alone gets about 0.56 Recall@20 on a hard legal corpus and 0.86 Recall@5 on a smaller one; a fine-tuned or Vietnamese-adapted dense model plus a cross-encoder adds 5 to 20 points; for a tiny corpus like ours, zero-shot bge-m3 plus fusion is the sensible start.

Models (all from the Hub tools; sizes/licences from the Hub cards; Vietnamese scores only where stated):

| Model | Size | Licence | Note |
|---|---|---|---|
| `BAAI/bge-m3` | about 568M (xlm-roberta) | MIT | dense+sparse+multi-vector, 100+ languages, 8192 tokens; Vietnamese score not stated on pages read. https://huggingface.co/BAAI/bge-m3 ; paper https://arxiv.org/abs/2402.03216 |
| `AITeamVN/Vietnamese_Embedding` (and `_v2`) | 567.8M | apache-2.0 | fine-tuned from bge-m3 for Vietnamese; used as the first-stage encoder in the UIT 2026 solution above; its own benchmark numbers not read (UNVERIFIED). https://huggingface.co/AITeamVN/Vietnamese_Embedding |
| `bkai-foundation-models/vietnamese-bi-encoder` | 135M (PhoBERT-based) | apache-2.0 | cited as strong on Zalo legal data [S] https://arxiv.org/pdf/2409.13699 ; PhoBERT models expect word-segmented input (UNVERIFIED on this card). https://huggingface.co/bkai-foundation-models/vietnamese-bi-encoder |
| `Alibaba-NLP/gte-multilingual-base`, `intfloat/multilingual-e5-large` | 305M / 560M | apache-2.0 / MIT | multilingual alternatives that list `vi`. https://huggingface.co/Alibaba-NLP/gte-multilingual-base , https://huggingface.co/intfloat/multilingual-e5-large |
| `BAAI/bge-reranker-v2-m3` | 567.8M | apache-2.0 | multilingual cross-encoder. https://huggingface.co/BAAI/bge-reranker-v2-m3 |
| `AITeamVN/Vietnamese_Reranker` | 567.8M | apache-2.0 | bge-reranker-v2-m3 fine-tune for Vietnamese. https://huggingface.co/AITeamVN/Vietnamese_Reranker |
| `itdainb/PhoRanker` | 135M | apache-2.0 | small PhoBERT cross-encoder trained on mMARCO; reached 0.558 MRR@10 before fine-tuning in [V] https://arxiv.org/html/2507.14619v1 . https://huggingface.co/itdainb/PhoRanker |

Benchmarks and published numbers:
- Multi-stage legal IR (corpus 114,177 articles): BM25+ Recall@20 0.557, F2 0.221; best neural 0.954/0.727; BM25 x cosine fusion 0.970 / F2 0.741. [V] https://ar5iv.labs.arxiv.org/html/2209.14494
- SoICT 2024 legal retrieval (261k docs): BM25Okapi MRR@10 0.344, BM25Plus 0.363, pretrained bi-encoder 0.461, fine-tuned 0.622, with PhoRanker rerank about 0.79. [V] https://arxiv.org/html/2507.14619v1
- UIT 2026 legal task (about 8.5k docs): BM25 R@5 85.8, bi-encoder 92.4 to 93.4, RRF 94.7, plus reranker 96.4. [V] https://github.com/monster1909/vietnamese-legal-retrieval (README claims, not peer reviewed).
- ALQAC 2021 Task 1: BM25 alone F2 0.784, BM25 + neural reranker 0.806 (one team). [S] https://arxiv.org/abs/2204.10717 ; Zalo AI Legal Text Retrieval 2021 numbers: not found directly (UNVERIFIED).
- University regulations: ViRHE4QA, 9,758 QA pairs over 294 articles from 21 university regulatory documents; BM25 + fine-tuned bi-encoder (BM25 weight 0.1) best on 5 of 7 top-k; dense models without fine-tuning performed worst; licence not stated, "available for research". [V] https://arxiv.org/abs/2409.02840 . Also VNU student-affairs QA [S] https://arxiv.org/pdf/2501.15022 . No public Vietnamese university-announcement retrieval set was found, so our own qrels are the real evaluation.

## D. No-answer queries and an unreliable baseline

**Short answer.** A single raw-score threshold is fragile; use score-gap or rank-shape features, evaluate with labelled unanswerable queries, report false-abstain and unsafe-answer rates separately, and judge the site search by pooled judgments, never as ground truth.

- Abstention: practitioner and recent preprint evidence that fixed similarity cutoffs are not calibrated (score-gap AUROC .724 vs max-score .583 in one paper) and that thresholds must be re-tuned when the reranker or encoder changes. [S] https://arxiv.org/pdf/2609.15578 and [S] https://oneuptime.com/blog/post/2026-11-16-how-to-monitor-rag-relevance-gates-and-fallbacks-for-unanswerable-questions/markdown (preprint, blog: weak sources). UAEval4RAG defines unanswered-ratio and acceptable-ratio metrics over six unanswerable categories. [V-abstract] https://arxiv.org/abs/2412.12300
- Baseline with holes: Buckley and Voorhees show P@k/MAP treat unjudged documents as non-relevant and degrade with sparse judgments; `bpref` scores only judged documents; pooling bias grows with collection size. [S] https://www.nist.gov/publications/bias-and-limits-pooling-large-collections and NIST page for the 2004 paper https://www.nist.gov/node/761376 . Practical rule for us: pool the top-k of S1..S6 and the site's hits, have two students judge the pool blind to system, report unjudged@k, and also report bpref.

## E. Query rewriting and fusion

**Short answer.** For noisy student queries, a cheap rule-based rewrite (fold, expand abbreviations, normalise numbers/semester terms) is the first step; LLM rewriting helps but must be measured against rule-based with a "keep original as another query" guard. For fusion, RRF with k = 60 is the default and often not critical.

- Rewrite-Retrieve-Read: rewriting the user's query before retrieval helps RAG; shown on open-domain QA with Bing and ChatGPT, not Vietnamese. [V-abstract] https://aclanthology.org/2023.emnlp-main.322 (arXiv 2305.14283). HyDE is described as generating a hypothetical answer and embedding it [S, textbook chapter]; UAEval4RAG notes rewriting also changes how often systems reject unanswerable queries. https://arxiv.org/abs/2412.12300
- RRF: score = sum of 1/(k + rank); k = 60 was fixed in a pilot and "near-optimal, but the choice was not critical"; RRF beat Condorcet and CombMNZ on TREC data. [V] http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
- Vietnamese: a 2024 legal QA paper proposes a normalised RRF for keyword + vector search [S] https://arxiv.org/html/2409.13699v1 ; a VLSP 2025 system used a tuned weighted score sum instead of RRF [S] https://preview.aclanthology.org/anlp-naacl/2025.vlsp-1.20.pdf ; the UIT 2026 solution used weighted RRF (README above). ViRHE4QA tuned the BM25 weight to 0.1 for a dense+BM25 sum. So tune a weight on dev rather than assume equal fusion.

## Technique table

| Technique | Stage | Effort | Expected benefit | Source |
|---|---|---|---|---|
| Fold diacritics + keep original field | S1, S2 | low | large for no-accent queries; some false matches | Elastic asciifolding doc; Discourse thread |
| Syllable bigrams vs pyvi/VnCoreNLP tokens | S1, S2 | low | unknown; no published comparison, 1 to 5 points guess | monster1909 repo; 2209.14494; UNVERIFIED size |
| Keep document numbers and dates whole (and date field) | S1, S7 | low | fixes the P77 class of misses | Drupal search_simplify |
| Abbreviation/teencode dictionary on queries | S1 to S4 | low | high for hbkkht, ktmt, hk1 style queries | ViLexNorm (learned model too weak) |
| Accent restoration model (ViT5) on queries | S1 to S4 | medium | moderate; costs latency | nrl-ai model card |
| LSI/LSA | S3 | medium | none found for Vietnamese; likely small | no source found (UNVERIFIED) |
| Dense bge-m3 zero-shot | S4 | low | +5 to +10 R@5 over BM25 on UIT 2026 task | Hub card; UIT 2026 repo |
| Vietnamese-tuned encoder (Vietnamese_Embedding) | S4 | low | likely above bge-m3, unverified on our data | Hub card |
| Weighted RRF, k sweep | S5 | low | +1 to +2 R@5 over best single | Cormack 2009; UIT 2026 repo |
| Cross-encoder rerank (bge-reranker-v2-m3 / Vietnamese_Reranker / PhoRanker) | S6 | medium | +1.5 to +20 points MRR depending on baseline | UIT 2026 repo; 2507.14619 |
| Recency prior / metadata filter (type, year, unit) | S7 | low | high for "new" and date queries; Drupal off by default | node_ranking page |
| LLM query rewrite | S1 to S4 | medium | mixed, English-only evidence | 2305.14283 |
| Score-gap abstention | S5, S6 | low | needed for no-answer queries | 2609.15578 (weak) |
| Pooled judgments + bpref | eval | medium | makes the site baseline fair | NIST / Buckley and Voorhees |

## Five experiments, ranked by value per cost (3 students)

1. **Tokenisation and folding ablation for S1/S2** (one afternoon): BM25 over {syllable unigram, syllable uni+bigram, pyvi, VnCoreNLP} x {folded, original, both fields}, with dates and document numbers kept whole. Metric: Recall@5, MRR on dev qrels. Fills the gap no paper covers.
2. **Query normalisation layer** (one day): fold + abbreviation dictionary (collect 30 to 50 from our own pilot queries) + number/date normalisation; compare with ViT5 restoration and one LLM rewrite on the 20 pilot queries and the noisy subset. Keep original query as a second RRF input.
3. **Zero-shot dense model bake-off for S4** (one day, GPU or Colab): bge-m3, Vietnamese_Embedding, multilingual-e5-large, gte-multilingual-base, bkai bi-encoder on our dev set; then RRF with a k sweep (20, 60, 100) and a BM25 weight sweep.
4. **Reranker comparison for S6** (one day): bge-reranker-v2-m3, Vietnamese_Reranker, PhoRanker on the top-20 of the best fusion; report MRR@10, latency per query, and gain over no rerank.
5. **No-answer handling and fair baseline** (two days): add 20 to 30 unanswerable queries; calibrate a score-gap threshold on dev, report false-abstain and unsafe-answer rates; pool S1..S6 + site hits, judge blind, report unjudged@k and bpref so the site search is never ground truth. Also do the hand test of "24/11/2025" vs "24/11" and the "đ" vs "d" check to confirm the Drupal hypotheses.
