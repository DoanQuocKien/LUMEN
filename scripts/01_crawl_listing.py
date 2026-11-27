"""W1-A1: crawl every listing section into data/raw/posts_index.csv.

Run from the repository root:  python scripts/01_crawl_listing.py -v
All options: python -m lumen.crawl.listing --help
"""
import sys

from lumen.crawl.listing import main

if __name__ == "__main__":
    sys.exit(main())
