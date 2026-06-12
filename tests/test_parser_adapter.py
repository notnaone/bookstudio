from __future__ import annotations

from pathlib import Path

import pytest

from studio_app.parser_adapter import ParsedBook, parse_book

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_book_txt_returns_parsedbook():
    result = parse_book(FIXTURES / "sample.txt")
    assert isinstance(result, ParsedBook)
    assert result.format == "txt"
    assert result.body_chars > 0
    assert result.raw_chars >= result.body_chars


def test_parse_book_includes_chapters():
    result = parse_book(FIXTURES / "sample.txt")
    assert result.total_chapters >= 1


def test_parse_book_unknown_format_raises(tmp_path: Path):
    bad = tmp_path / "thing.xyz"
    bad.write_text("nope")
    with pytest.raises(ValueError):
        parse_book(bad)


def test_parse_book_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        parse_book(tmp_path / "nope.txt")


def test_chars_per_page_zero_when_no_pages():
    # TXT has no real pages → chars_per_page should be 0.
    result = parse_book(FIXTURES / "sample.txt")
    if result.total_pages is None or result.total_pages == 0:
        assert result.chars_per_page == 0
