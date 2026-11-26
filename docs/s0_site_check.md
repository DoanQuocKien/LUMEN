# W1-C2: S0 vs the real site search (checked by hand, 2026-11-26)

Method: 20 pilot queries typed by hand into the search box of ctsv.uit.edu.vn and daa.uit.edu.vn (no scripted
use of `/search/`, which robots.txt disallows). S0 = every word must match, diacritics ignored, over our crawled
window (ctsv since 2024-11, daa since 2025). Counts differ when the site has older posts, so we compare
zero vs non-zero and the result sets.

## ctsv (site count / S0 count)

| qid | site | S0 | note |
|---|---|---|---|
| P01 | 6 | 6 | same 6 titles |
| P03, P08, P10, P13, P14, P81 | many | 2 to 56 | both non-zero |
| P09 | many | 12 | both non-zero; query had no diacritics, so the site is diacritic-insensitive |
| P07 | 9 | 7 | site extras are older than our window |
| P05 | 7 | 1 | the S0 hit is on the site's list; rest are older |
| P64 | 2 | 0 | site hits are 2012 and 2017 posts |
| P79 | many | 0 | site hits are 2014-2024 posts |
| P85 | 2 | 0 | site hits are from 2019 and 2024-08 |
| P88 | 1 | 0 | site hit is a 2020 post |
| P04, P71, P72, P89 | 0 | 0 | agree |
| P61 | 0 | 0 | agree |
| P77 | 1 (2023 BHYT post) | 3 (2025 posts) | **unexplained mismatch** |

Result: 15 of 16 comparable queries agree (excluding the 4 explained by our window); P77 is the exception.
A minimum word length of 3 (Drupal default) was tried and rejected: it made P77 return 60 and P04 return 3.

## Findings

- The site's order is **not newest first** (P01 mixes 2026-11, 2026-07, 2026-10, 2026-11, 2026-07, 2019). S0's date sort is our own choice; only result sets are comparable.
- Matching is diacritic-insensitive and roughly AND over title and body.
- **daa search** returns almost only static programme pages ("Cử nhân ngành ...", "Bảng tóm tắt môn học", "Một số quy trình dành cho sinh viên") and never announcements. Nothing to replicate; programme pages are not in our corpus (candidate for the W1-A2 scope).
- DAA hits not in our corpus: P61 (1), P05 (1), P85 (1), P03/P08/P10/P14/P64/P79/P81/P88 (many), all programme pages.
