from lumen.parse.html import parse_post

HTML = """<html><head><title>Thông báo học bổng | CTSV</title>
<meta property="article:published_time" content="2025-03-14T08:00:00+07:00"></head>
<body><header><a href="http://spam.example/buy">cheap pills</a><ul class="menu"><li>Trang chủ</li></ul></header>
<div class="breadcrumb">Trang chủ » Thông báo</div>
<div id="content"><h1 id="page-title">Thông báo số 2 về học bổng HK1 năm học 2024-2025</h1>
<div class="field-name-body"><div class="field-item">
<p>Sinh viên nộp hồ sơ trước ngày 20/03/2025.</p>
<p>Biểu mẫu: <a href="https://forms.example/abc">Google Form</a></p>
<p><a href="/sites/default/files/uploads/files/202503/tb2.pdf">Thông báo.pdf</a></p>
</div></div>
<div class="block"><h2>Bài viết liên quan</h2><div class="content"><ul>
<li><a href="/bai-viet/thong-bao-so-1-ve-hoc-bong">Thông báo số 1</a></li></ul></div></div>
</div><div class="pager">1 2 3</div><footer>Copyright UIT</footer></body></html>"""


def test_parse_post():
    p = parse_post(HTML, "https://ctsv.uit.edu.vn/bai-viet/thong-bao-so-2")
    assert p["title"].startswith("Thông báo số 2")
    assert p["date"] == "2025-03-14"
    assert "nộp hồ sơ" in p["body_text"]
    for junk in ("cheap pills", "Copyright", "Trang chủ", "Bài viết liên quan", "Thông báo số 1"):
        assert junk not in p["body_text"], junk
    assert [a["ext"] for a in p["attachments"]] == ["pdf"]
    assert p["attachments"][0]["url"] == "https://ctsv.uit.edu.vn/sites/default/files/uploads/files/202503/tb2.pdf"
    assert p["related"] == [{"url": "https://ctsv.uit.edu.vn/bai-viet/thong-bao-so-1-ve-hoc-bong", "title": "Thông báo số 1"}]
    assert p["external_links"] == ["https://forms.example/abc"]


def test_parse_pdf_only_post_has_short_body():
    html = '<div class="field-name-body"><div class="field-item"><a href="/sites/default/files/a.pdf">a.pdf</a></div></div>'
    p = parse_post(f"<html><body><h1>QĐ khen thưởng</h1>{html}</body></html>", "https://ctsv.uit.edu.vn/bai-viet/x")
    assert p["attachments"][0]["ext"] == "pdf" and len(p["body_text"]) < 20


REAL_CTSV = """<html><body><div id="main"><div id="content">
<h1 class="title" id="page-title"> Hướng dẫn về qui định Học bổng </h1>
<div id="block-system-main" class="block block-system"><div class="content">
<article id="node-1" class="node node-baiviet">
 <div class="submitted"><span property="dc:date dc:created" content="2026-07-08T09:51:55+07:00">Wed, 08/07/2026 - 09:51</span></div>
 <div class="content">
  <div class="field field-name-body"><div class="field-items"><div class="field-item even" property="content:encoded">
   <p>Ngày 07/07/2026, trường đã ban hành <a href="https://ctsv.uit.edu.vn/sites/default/files/uploads/files/202607/804.pdf">Quy định 804</a>.</p></div></div></div>
  <div class="field field-name-field-file-dinh-kem"><div class="field-label">File đính kèm:</div>
   <span class="file"><a href="https://ctsv.uit.edu.vn/sites/default/files/uploads/files/202607/804.pdf">804.pdf</a></span>
   <span class="file"><a href="/sites/default/files/uploads/files/202607/phu-luc.docx">phu-luc.docx</a></span></div>
 </div>
 <ul class="links inline"><li class="addtoany">Share</li></ul>
</article></div></div>
<div class="region region-content-lower"><div id="block-views-content-views-block-1" class="block block-views related">
 <h2>Bài viết liên quan</h2><div class="content"><ul><li class="views-row"><a href="/bai-viet/tb-so-2">TB số 2</a><span class="date">(19-11-2026)</span></li></ul></div></div></div>
</div></div></body></html>"""


def test_parse_real_ctsv_layout():
    p = parse_post(REAL_CTSV, "https://ctsv.uit.edu.vn/bai-viet/huong-dan")
    assert p["date"] == "2026-07-08"
    assert p["title"] == "Hướng dẫn về qui định Học bổng"
    assert "Quy định 804" in p["body_text"] and "Bài viết liên quan" not in p["body_text"]
    assert "File đính kèm" not in p["body_text"] and "Share" not in p["body_text"]
    assert [a["name"] for a in p["attachments"]] == ["Quy định 804", "phu-luc.docx"]  # dedup by url
    assert p["related"] == [{"url": "https://ctsv.uit.edu.vn/bai-viet/tb-so-2", "title": "TB số 2"}]
