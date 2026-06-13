from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from studio_app.pagination import paginate_docx, paginate_html_to_pages, paginate_txt

FIXTURES = Path(__file__).parent / "fixtures"


def test_paginate_txt_short_fits_one_page():
    pages = paginate_txt("para1\n\npara2", chars_per_page=500)
    assert len(pages) == 1
    assert "para1" in pages[0]
    assert "para2" in pages[0]


def test_paginate_txt_splits_at_paragraph_boundaries():
    paras = [f"Paragraph {i} with enough text to count." for i in range(6)]
    text = "\n\n".join(paras)
    pages = paginate_txt(text, chars_per_page=40)
    assert len(pages) >= 2
    for page in pages:
        soup = BeautifulSoup(page, "html.parser")
        assert soup.find("body") is not None
        # No unclosed <p> at page boundary — each page is valid HTML
        assert str(soup).count("<p>") == str(soup).count("</p>")


def test_paginate_html_preserves_structure():
    html = "<p>Alpha</p><p>Beta</p><p>Gamma</p>"
    pages = paginate_html_to_pages(html, chars_per_page=10)
    assert len(pages) >= 2
    combined = "".join(pages)
    assert "Alpha" in combined
    assert "Gamma" in combined


def test_paginate_docx_fixture(tmp_path):
    docx = FIXTURES / "tiny.docx"
    pages = paginate_docx(docx, chars_per_page=80)
    assert len(pages) >= 1
    assert "paragraph" in pages[0].lower()


def test_paginate_html_empty_returns_one_blank_page():
    pages = paginate_html_to_pages("", chars_per_page=100)
    assert len(pages) == 1


def test_paginate_txt_escapes_html_in_paragraphs():
    pages = paginate_txt("<script>alert(1)</script>\n\n<b>bold</b>", chars_per_page=500)
    assert len(pages) == 1
    assert "<script>" not in pages[0]
    assert "&lt;script&gt;" in pages[0]
    assert "<b>bold</b>" in pages[0] or "&lt;b&gt;" in pages[0]
