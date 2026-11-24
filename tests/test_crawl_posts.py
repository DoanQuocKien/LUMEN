import json

from lumen.crawl.listing import ListingItem
from lumen.crawl.posts import attachment_links, crawl_posts, select_posts
from test_crawl_listing import BASE, FakeResp, make_fetcher

POST = """<html><body><div id="block-system-main">
<a href="/sites/default/files/uploads/files/202611/qd-1487.pdf">QĐ</a>
<a href="/sites/default/files/uploads/files/202611/qd-1487.pdf?x=1">again</a>
<a href="https://drive.google.com/file/d/abc/view">external</a>
<a href="/bai-viet/other">other post</a></div>
<a href="/sidebar.pdf">sidebar</a></body></html>"""


def item(slug, date, *sections, title=None):
    return ListingItem(f"{BASE}/bai-viet/{slug}", title or slug, date, set(sections))


def test_select_order_and_rules():
    idx = {i.url: i for i in [
        item("old", "2020-01-01", "/thong-bao"),
        item("new1", "2026-05-01", "/thong-bao"),
        item("new2", "2026-09-01", "/thong-bao"),
        item("qd26", None, "/quyet-dinh", title="Quyết định số 12/2026"),
        item("qd19", None, "/quyet-dinh", title="Quyết định số 12/2019"),
        item("ref", "2018-01-01", "/quy-che-quy-dinh"),
        item("skip", "2026-09-02", "/thong-bao", title="Thông báo học bù"),
    ]}
    rules = {"since": "2024-11-22", "undated_title_regex": "202[56]",
             "reference_sections": ["/quy-che-quy-dinh"], "exclude_title_regex": "học bù"}
    got = [i.url.rsplit("/", 1)[-1] for i in select_posts(idx, rules)]
    assert got == ["new2", "new1", "qd26", "ref"]          # newest first, then undated, then reference


def test_attachment_links():
    assert attachment_links(POST, f"{BASE}/bai-viet/x") == [f"{BASE}/sites/default/files/uploads/files/202611/qd-1487.pdf"]


def test_crawl_posts_fetches_attachments_and_resumes(tmp_path):
    pdf = f"{BASE}/sites/default/files/uploads/files/202611/qd-1487.pdf"
    f, _ = make_fetcher(tmp_path, {f"{BASE}/bai-viet/x": POST, pdf: "%PDF",
                                   f"{BASE}/bai-viet/gone": [FakeResp(404, "")]})
    status = tmp_path / "post_status.jsonl"
    items = [item("x", "2026-01-01"), item("gone", "2026-01-01")]
    stats = crawl_posts(f, items, status)
    assert stats["posts"] == 1 and stats["failed"] == 1 and stats["attachments"] == 1
    rows = [json.loads(l) for l in status.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["attachments"][0]["bytes"] == 4
    again = crawl_posts(f, items, status)                  # 200s are skipped; the 404 is retried
    assert again["skipped"] == 1 and f.session.calls.count(f"{BASE}/bai-viet/x") == 1
