"""Extract title, date, body text, attachment links and related posts from a post page. [W1-A3]

Strips the site template: header (including spam links), menus, sidebars, footer and the
pager. Selectors target a Drupal 7 theme; they are heuristics because the real page was
reachable from the shell; verified on one live ctsv post (node-baiviet) -> check 20 random posts by eye (W1-A3 'done when')
and add selectors to BODY_SELECTORS / STRIP_SELECTORS if something is off.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from lumen.text.dates import parse_date
from lumen.text.normalize import fold

BODY_SELECTORS = [
    "div.field-name-body div.field-item",
    "div.field-name-body",
    "div.node-content",
    "article .content",
    "div.node .content",
    "div.region-content",
    "div#content",
    "main",
]
STRIP_SELECTORS = [
    "script", "style", "noscript", "iframe", "nav", "header", "footer", "aside", "form",
    ".breadcrumb", ".pager", ".item-list .pager", ".tabs", ".menu", "#header", "#footer",
    "#navigation", ".region-sidebar-first", ".region-sidebar-second", ".region-header",
    ".region-footer", ".skip-link", ".social-share", ".addthis_toolbox", ".links.inline",
]
ATTACH_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "rar", "txt", "csv"}
_RELATED_KEY = "bai viet lien quan"
_WS = re.compile(r"[ \t ​﻿]+")


def _clean_text(el) -> str:
    text = el.get_text("\n")
    text = unicodedata.normalize("NFC", text)
    lines = [_WS.sub(" ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def _title(soup: BeautifulSoup) -> str:
    for sel in ("h1#page-title", "h1.title", "h1.page-title", "article h1", "h1"):
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return _WS.sub(" ", el.get_text(" ", strip=True))
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.split("|")[0].strip()
    return ""


def _date(soup: BeautifulSoup, body_text: str) -> str | None:
    # ctsv (Drupal 7 RDFa): <span property="dc:date dc:created" content="2026-07-08T09:51:55+07:00">
    for el in soup.find_all(attrs={"property": True, "content": True}):
        props = el.get("property", "")
        props = props.split() if isinstance(props, str) else list(props)
        if "dc:created" in props or "dc:date" in props:
            d = parse_date(el["content"][:10])
            if d:
                return d
    meta = soup.find("meta", property="article:published_time")
    if meta and meta.get("content"):
        d = parse_date(meta["content"][:10])
        if d:
            return d
    for t in soup.find_all("time"):
        d = parse_date(t.get("datetime", "")[:10]) or parse_date(t.get_text(" ", strip=True))
        if d:
            return d
    for sel in (".submitted", ".date-display-single", ".post-date", ".node-date", ".field-name-post-date"):
        el = soup.select_one(sel)
        if el:
            d = parse_date(el.get_text(" ", strip=True))
            if d:
                return d
    return None


def _pop_related_block(soup, base_url: str) -> list[dict]:
    """ctsv puts 'Bài viết liên quan' in its own views block (div.block.related), outside the node."""
    out: list[dict] = []
    for blk in soup.select("div.block.related, div.block-views.related"):
        for a in blk.select("li a[href]"):
            href = urldefrag(urljoin(base_url, a["href"]))[0]
            out.append({"url": href, "title": a.get_text(" ", strip=True)})
        blk.decompose()
    return out


def _pop_related(root, base_url: str) -> list[dict]:
    """Find the 'Bài viết liên quan' heading, return its links, and remove it from `root`."""
    related: list[dict] = []
    for h in root.find_all(["h2", "h3", "h4", "div", "span", "p", "strong"]):
        own = fold(h.get_text(" ", strip=True))
        # the element must be (almost) just the heading text, not a wrapper that contains the list
        if len(own) > len(_RELATED_KEY) + 8 or _RELATED_KEY not in own:
            continue
        sibs = list(h.find_next_siblings())
        links = [a for s in sibs for a in s.find_all("a", href=True) if "/bai-viet/" in a["href"]]
        if not links and h.parent is not None:
            sibs = list(h.parent.find_next_siblings())
            links = [a for s in sibs for a in s.find_all("a", href=True) if "/bai-viet/" in a["href"]]
        for a in links:
            related.append({"url": urldefrag(urljoin(base_url, a["href"]))[0], "title": a.get_text(" ", strip=True)})
        for s in sibs:
            s.decompose()
        h.decompose()
        break
    return related


def parse_post(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = _title(soup)
    page_date = _date(soup, "")  # before stripping (meta/time tags may sit in the header)

    related = _pop_related_block(soup, url)
    for sel in STRIP_SELECTORS:
        for el in soup.select(sel):
            el.decompose()

    node = soup.select_one("article.node, div.node")  # attachments sit in a sibling field of the body
    body_el = None
    for sel in BODY_SELECTORS:
        cand = soup.select_one(sel)
        if cand and len(cand.get_text(strip=True)) > 0:
            body_el = cand
            break
    if body_el is None:
        body_el = soup.body or soup

    if not related:
        related = _pop_related(body_el, url) or _pop_related(soup, url)

    host = urlparse(url).netloc
    attachments, external, seen = [], [], set()
    link_scope = node if node is not None else body_el
    for a in link_scope.find_all("a", href=True):
        href = urldefrag(urljoin(url, a["href"]))[0]
        if not href.startswith("http") or href in seen:
            continue
        seen.add(href)
        p = urlparse(href)
        ext = p.path.rsplit(".", 1)[-1].lower() if "." in p.path.rsplit("/", 1)[-1] else ""
        if ext in ATTACH_EXT or "/sites/default/files/" in p.path:
            attachments.append({"url": href, "name": a.get_text(" ", strip=True) or p.path.rsplit("/", 1)[-1], "ext": ext})
        elif p.netloc != host:
            external.append(href)

    body_text = _clean_text(body_el)
    if title and body_text.startswith(title):
        body_text = body_text[len(title):].lstrip()
    date = page_date or parse_date(body_text[:300])
    return {
        "url": url,
        "title": title,
        "date": date,
        "body_text": body_text,
        "attachments": attachments,
        "related": related,
        "external_links": external,
    }
