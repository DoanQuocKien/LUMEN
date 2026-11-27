from lumen.ocr.detect import analyze_pdf, extract_text_layer


def test_detect_routes(text_pdf, scanned_pdf, mixed_pdf):
    assert analyze_pdf(text_pdf)["route"] == "text"
    s = analyze_pdf(scanned_pdf)
    assert s["route"] == "ocr" and s["scanned_pages"] == [0]
    m = analyze_pdf(mixed_pdf)
    assert m["route"] == "mixed" and m["text_pages"] == [0] and m["scanned_pages"] == [1]
    assert "hoc bong" in extract_text_layer(text_pdf)[0]


def test_detect_bad_file(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_bytes(b"not a pdf")
    assert analyze_pdf(bad)["route"] == "error"
