import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont


@pytest.fixture
def text_pdf(tmp_path):
    p = tmp_path / "text.pdf"
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_text((72, 100), "Thong bao ve hoc bong khuyen khich hoc tap hoc ky 1 nam hoc 2024-2025. " * 3)
    doc.save(p)
    return p


def _scan_png(text: str, path):
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 42)
    except OSError:
        font = ImageFont.load_default()
    img = Image.new("RGB", (1240, 400), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(text.split("|")):
        d.text((40, 40 + i * 80), line, fill="black", font=font)
    img.save(path)


@pytest.fixture
def scanned_pdf(tmp_path):
    """A PDF whose only content is a picture of text (no text layer)."""
    png = tmp_path / "scan.png"
    _scan_png("Scholarship notice for students|Academic year 2024 registration", png)
    p = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=620, height=200)
    page.insert_image(page.rect, filename=str(png))
    doc.save(p)
    return p


@pytest.fixture
def mixed_pdf(tmp_path, text_pdf, scanned_pdf):
    p = tmp_path / "mixed.pdf"
    out = pymupdf.open()
    out.insert_pdf(pymupdf.open(text_pdf), from_page=0, to_page=0)
    out.insert_pdf(pymupdf.open(scanned_pdf))
    out.save(p)
    return p
