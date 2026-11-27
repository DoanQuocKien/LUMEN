"""W1-A2: fetch selected posts and their attachments.

Run from the repository root:  python scripts/02_crawl_posts.py --config configs/default.yaml -v
"""
import sys

from lumen.crawl.posts import main

if __name__ == "__main__":
    sys.exit(main())
