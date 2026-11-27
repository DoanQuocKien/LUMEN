"""Offline tests for the listing crawler. The HTML mirrors the real site's markup (22/11/2026)."""
from lumen.crawl.http import DisallowedError, PoliteFetcher
from lumen.crawl.listing import crawl_sections, load_index, parse_listing

BASE = "https://ctsv.uit.edu.vn"

TEASER_PAGE = """<html><body><div id="content">
<div id="block-system-main" class="block block-system"><div class="content">
 <article class="node node-baiviet node-teaser">
  <h2><a href="/bai-viet/thong-bao-so-2-hb-kkht">Thông báo số 2 về HB KKHT</a></h2>
  <div class="submitted"><span property="dc:date dc:created" content="2026-11-19T15:02:02+07:00">Thu, 19/11/2026 - 15:02</span></div>
  <ul class="links"><li class="node-readmore"><a href="/bai-viet/thong-bao-so-2-hb-kkht">Read more</a></li></ul>
 </article>
 <article class="node node-baiviet node-teaser">
  <h2><a href="/bai-viet/thong-bao-so-1-hb-kkht?x=1#top">Thông báo số 1 về HB KKHT</a></h2>
  <div class="submitted"><span content="2026-11-03T09:00:00+07:00">x</span></div>
 </article>
 <h2 class="element-invisible">Pages</h2>
 <ul class="pager"><li class="pager-next"><a href="/thong-bao?page=1">next ›</a></li></ul>
</div></div>
<div class="block block-views"><a href="/bai-viet/sidebar-post">Sidebar post</a></div>
</div></body></html>"""

LIST_PAGE = """<html><body><div id="block-system-main"><div class="view"><ul>
 <li class="views-row"><span class="field-content"><a href="/bai-viet/quyet-dinh-so-1487-2026">Quyết định số 1487/2026</a></span></li>
 <li class="views-row"><a href="/bai-viet/quyet-dinh-so-1484-2026">Quyết định số 1484/2026</a> <span class="date">(16-11-2026)</span></li>
 <li class="views-row"><a href="https://other.site/bai-viet/x">External</a></li>
</ul></div></div></body></html>"""


def test_parse_teasers():
    items, nxt = parse_listing(TEASER_PAGE, f"{BASE}/thong-bao")
    assert [i.url for i in items] == [f"{BASE}/bai-viet/thong-bao-so-2-hb-kkht",
                                      f"{BASE}/bai-viet/thong-bao-so-1-hb-kkht"]
    assert items[0].title == "Thông báo số 2 về HB KKHT"
    assert items[0].date == "2026-11-19T15:02:02+07:00"
    assert nxt == f"{BASE}/thong-bao?page=1"


def test_parse_title_list_dates_and_filters():
    items, nxt = parse_listing(LIST_PAGE, f"{BASE}/quyet-dinh?page=39")
    assert [i.title for i in items] == ["Quyết định số 1487/2026", "Quyết định số 1484/2026"]
    assert items[0].date is None and items[1].date == "2026-11-16"
    assert nxt is None


class FakeResp:
    def __init__(self, status, body, headers=None):
        self.status_code, self.content, self.headers = status, body.encode(), headers or {}


class FakeSession:
    def __init__(self, pages):
        self.pages, self.calls, self.headers = pages, [], {}

    def get(self, url, timeout=None):
        self.calls.append(url)
        val = self.pages[url]
        if isinstance(val, list):        # a sequence of responses for retries
            return val.pop(0)
        return FakeResp(200, val)


class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def sleep(self, s):
        self.slept.append(s)
        self.t += s

    def __call__(self):
        return self.t


ROBOTS = "User-agent: *\nCrawl-delay: 10\nDisallow: /search/\n"


def make_fetcher(tmp_path, pages, delay=1.0):
    pages = {f"{BASE}/robots.txt": ROBOTS, **pages}
    clock = Clock()
    f = PoliteFetcher(BASE, tmp_path / "cache", "test-agent", delay_s=delay,
                      session=FakeSession(pages), sleep=clock.sleep, clock=clock)
    return f, clock


def test_fetcher_delay_cache_and_robots(tmp_path):
    f, clock = make_fetcher(tmp_path, {f"{BASE}/a": "A", f"{BASE}/b": "B"})
    assert f.delay_s == 10.0                      # robots Crawl-delay overrides 1 s
    f.get(f"{BASE}/a")
    f.get(f"{BASE}/b")
    assert clock.slept == [10.0, 10.0]            # waited before each request after robots.txt
    again = f.get(f"{BASE}/a")
    assert again.from_cache and again.text == "A"
    assert f.session.calls.count(f"{BASE}/a") == 1
    try:
        f.get(f"{BASE}/search/node/hoc")
        raise AssertionError("expected DisallowedError")
    except DisallowedError:
        pass


def test_fetcher_retries_5xx(tmp_path):
    url = f"{BASE}/flaky"
    f, _ = make_fetcher(tmp_path, {url: [FakeResp(503, ""), FakeResp(200, "ok")]})
    assert f.get(url).text == "ok"


def test_crawl_sections_paginates_and_dedupes(tmp_path):
    page2 = LIST_PAGE.replace("1487", "1400")
    pages = {
        f"{BASE}/thong-bao": TEASER_PAGE,
        f"{BASE}/thong-bao?page=1": page2,
        f"{BASE}/quyet-dinh": LIST_PAGE,
    }
    f, _ = make_fetcher(tmp_path, pages)
    out = tmp_path / "posts_index.csv"
    index = crawl_sections(f, ["/thong-bao", "/quyet-dinh"], out)
    assert len(index) == 5
    shared = index[f"{BASE}/bai-viet/quyet-dinh-so-1484-2026"]
    assert shared.sections == {"/thong-bao", "/quyet-dinh"}
    reloaded = load_index(out)
    assert set(reloaded) == set(index)
    first_row = out.read_text(encoding="utf-8").splitlines()[1]
    assert "2026-11-19" in first_row               # newest dated post first
