# Decision log

| Date | Decision | Options considered | Reason | Owner |
|---|---|---|---|---|
| 2026-11-22 | Evaluate retrieval (ranked post links) only; no answer generation | RAG with generated answers vs. retrieval | Course rule: RAG topics focus on retrieval | Team |
| 2026-11-22 | Site search is baseline S0 (Boolean AND, sorted by date) | — | Probes: "học bổng" returns results, "học bổng glao" returns none | Team |
| 2026-11-22 | Listing crawl uses the menu sections in `configs/default.yaml` (/thong-bao ~165 p, /quyet-dinh ~40 p, /van-ban/thong-bao ~29 p, plus small sections); /van-ban is an empty landing page and is skipped | /node (front page, only 2 pages); the 'Bài viết liên quan' pager | Menu sections cover all post types; ~250 requests ≈ 45 min at 10 s | A |
| | Corpus window | last 2 years / all | pending W1-A1 | A |
| | OCR engine | Tesseract / PaddleOCR / VietOCR / vision LLM | pending W1-A4 | A |
| | Dense model | bge-m3 / multilingual-e5 / Vietnamese bi-encoder | pending W2 | C |
| | Lecturer approval of scope | — | pending | Team |
| 2026-11-25 | Add daa.uit.edu.vn (Office of Undergraduate Studies) as a second source; do not index forum.uit.edu.vn | DAA / www.uit.edu.vn / forum | 30 real student questions: about a third are academic-affairs topics (credits, transfers, exam dates, holidays) that ctsv does not cover. DAA has the same Drupal setup and `Crawl-delay: 10`. The forum is user content with personal data and is where queries come from | Team |
