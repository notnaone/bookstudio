from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from book_analyzer.parsers import get_parser


@dataclass
class ParsedBook:
    format: str
    body_chars: int
    raw_chars: int
    total_paragraphs: int
    total_chapters: int
    total_images: int
    total_tables: int
    total_charts: int
    total_pages: int | None
    offset_reliability: str

    @property
    def chars_per_page(self) -> int:
        if not self.total_pages or self.total_pages == 0:
            return 0
        return self.body_chars // self.total_pages


def parse_book(source_path: Path) -> ParsedBook:
    """Run book_analyzer over `source_path` and return a flat result."""
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    try:
        parser = get_parser(source_path)
    except Exception as exc:
        raise ValueError(f"Unsupported format: {source_path.suffix}") from exc
    result = parser.parse()
    m = result.book_metadata
    return ParsedBook(
        format=m.file_format,
        body_chars=m.body_character_count,
        raw_chars=m.raw_character_count,
        total_paragraphs=m.total_paragraphs,
        total_chapters=m.total_chapters,
        total_images=m.total_images,
        total_tables=m.total_tables,
        total_charts=m.total_charts,
        total_pages=m.total_pages,
        offset_reliability=m.offset_reliability,
    )
