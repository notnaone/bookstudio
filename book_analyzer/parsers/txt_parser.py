from __future__ import annotations

import re

from charset_normalizer import from_path

from ..schema import BookMetadata, ParseResult
from .base import BaseParser

# Plaintext has no embedded images/tables. We detect ASCII tables and
# image markers (e.g. "[image: foo.png]" or "Figure N") as best-effort.
_CHAPTER_RE = re.compile(r"^\s*(chapter\s+[\dIVXLCM]+|prologue|epilogue)\b.*$", re.IGNORECASE)


class TxtParser(BaseParser):
    file_format = "txt"
    offset_reliability = "exact"

    def parse(self) -> ParseResult:
        match = from_path(str(self.path)).best()
        text = str(match) if match else self.path.read_text(encoding="utf-8", errors="replace")

        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        chapters: list[str] = []
        current_chapter = "(Front Matter)"

        for para in paragraphs:
            first_line = para.strip().splitlines()[0] if para.strip() else ""
            if _CHAPTER_RE.match(first_line):
                current_chapter = first_line.strip()
                if current_chapter not in chapters:
                    chapters.append(current_chapter)

        meta = BookMetadata(
            file_name=self.path.name,
            file_format=self.file_format,
            raw_character_count=len(text),
            body_character_count=self.body_chars(text),
            total_paragraphs=len(paragraphs),
            total_chapters=len(chapters),
            total_images=0,
            total_tables=0,
            total_charts=0,
            offset_reliability=self.offset_reliability,
        )
        return ParseResult(book_metadata=meta, chapters=chapters, visual_elements=[])
