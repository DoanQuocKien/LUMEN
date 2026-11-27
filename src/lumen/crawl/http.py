"""Polite HTTP fetching with a disk cache. [W1-A1, W1-A2]

- At most one request every `delay_s` seconds (robots.txt asks for 10 s; a larger
  Crawl-delay in robots.txt wins).
- Every response is cached under `cache_dir`, so a second run, or a run that crashed
  halfway, replays from disk without touching the site.
- Retries 429/5xx and connection errors with exponential backoff.
- Refuses URLs that robots.txt disallows (e.g. /search/).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_BACKOFF_S = 120.0


class DisallowedError(RuntimeError):
    """The URL is disallowed by robots.txt."""


@dataclass
class FetchResult:
    url: str
    status: int
    content: bytes
    from_cache: bool

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class PoliteFetcher:
    def __init__(self, base_url: str, cache_dir: str | Path, user_agent: str,
                 delay_s: float = 10.0, timeout_s: float = 30.0, max_retries: int = 3,
                 check_robots: bool = True, session=None,
                 sleep=time.sleep, clock=time.monotonic):
        self.base_url = base_url.rstrip("/") + "/"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.delay_s = float(delay_s)
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.session = session if session is not None else requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._sleep, self._clock = sleep, clock
        self._last_request: float | None = None
        self.n_requests = 0
        self.robots: robotparser.RobotFileParser | None = None
        if check_robots:
            self._load_robots()

    # robots.txt ---------------------------------------------------------
    def _load_robots(self) -> None:
        robots_url = urljoin(self.base_url, "robots.txt")
        resp = self._request(robots_url)
        rp = robotparser.RobotFileParser()
        rp.parse(resp.content.decode("utf-8", errors="replace").splitlines())
        delay = rp.crawl_delay(self.user_agent) or rp.crawl_delay("*")
        if delay and float(delay) > self.delay_s:
            log.info("robots.txt Crawl-delay %s s > configured %s s; using robots value",
                     delay, self.delay_s)
            self.delay_s = float(delay)
        self.robots = rp

    def allowed(self, url: str) -> bool:
        return self.robots is None or self.robots.can_fetch(self.user_agent, url)

    # cache --------------------------------------------------------------
    def _paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.body", self.cache_dir / f"{key}.json"

    def cached(self, url: str) -> FetchResult | None:
        body_p, meta_p = self._paths(url)
        if not meta_p.exists():
            return None
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        content = body_p.read_bytes() if body_p.exists() else b""
        return FetchResult(url, meta["status"], content, from_cache=True)

    def _store(self, url: str, resp) -> None:
        body_p, meta_p = self._paths(url)
        body_p.write_bytes(resp.content)
        meta = {
            "url": url,
            "status": resp.status_code,
            "content_type": resp.headers.get("Content-Type"),
            "last_modified": resp.headers.get("Last-Modified"),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        meta_p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    # network ------------------------------------------------------------
    def _wait_turn(self) -> None:
        if self._last_request is not None:
            remaining = self.delay_s - (self._clock() - self._last_request)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request = self._clock()  # also stamped after each response, see _request

    def _request(self, url: str):
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._wait_turn()
            self.n_requests += 1
            try:
                resp = self.session.get(url, timeout=self.timeout_s)
                self._last_request = self._clock()  # the delay counts from the end of the response
            except requests.RequestException as exc:
                last_exc = exc
                log.warning("GET %s failed (%s), attempt %d", url, exc, attempt + 1)
            else:
                if resp.status_code not in RETRY_STATUS:
                    return resp
                last_exc = RuntimeError(f"HTTP {resp.status_code}")
                log.warning("GET %s -> %d, attempt %d", url, resp.status_code, attempt + 1)
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    self._sleep(min(float(retry_after), MAX_BACKOFF_S))
                    continue
            if attempt < self.max_retries:
                self._sleep(min(self.delay_s * 2 ** attempt, MAX_BACKOFF_S))
        raise RuntimeError(f"GET {url} failed after {self.max_retries + 1} attempts") from last_exc

    def get(self, url: str, refresh: bool = False) -> FetchResult:
        """Return the page, from cache unless `refresh` is set."""
        if not refresh:
            hit = self.cached(url)
            if hit is not None:
                return hit
        if not self.allowed(url):
            raise DisallowedError(url)
        resp = self._request(url)
        self._store(url, resp)
        return FetchResult(url, resp.status_code, resp.content, from_cache=False)
