from __future__ import annotations

import re

import pdfplumber

from ..schema import BookMetadata, Location, ParseResult, VisualElement
from .base import CONTEXT_WINDOW, BaseParser

# Strict chapter detection: short standalone line starting with a known
# chapter marker in EN / ET / RU / DE / FR / ES, followed by a number
# (arabic or roman). Avoids false positives from large-font body text.
_CHAPTER_RE = re.compile(
    r"^\s*(chapter|peatükk|глава|kapitel|capítulo|chapitre|capitolo)\s+"
    r"([\divxlcm]+|[a-zäöüõ]+)\b.*$",
    re.IGNORECASE,
)
# Front-matter style sections that appear once.
_NAMED_SECTION_RE = re.compile(
    r"^\s*(prologue|epilogue|preface|foreword|introduction|"
    r"prolog|epiloog|eessõna|sissejuhatus|"
    r"пролог|эпилог|предисловие|введение)\s*$",
    re.IGNORECASE,
)


def _is_chapter_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 80:
        return False
    return bool(_CHAPTER_RE.match(s) or _NAMED_SECTION_RE.match(s))


class PdfParser(BaseParser):
    file_format = "pdf"
    offset_reliability = "approximate"

    def parse(self) -> ParseResult:
        running_text: list[str] = []
        offset = 0
        chapters: list[str] = []
        current_chapter = "(Whole Book)"
        para_idx = 0
        elements: list[VisualElement] = []
        img_id = tbl_id = 0
        total_paragraphs = 0
        total_images = total_tables = 0
        total_pages = 0

        with pdfplumber.open(str(self.path)) as pdf:
            total_pages = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, start=1):
                # Tables
                try:
                    tables = page.find_tables()
                except Exception:
                    tables = []
                for t in tables:
                    tbl_id += 1
                    total_tables += 1
                    extracted = t.extract() or []
                    rows = len(extracted)
                    cols = max((len(r) for r in extracted), default=0)
                    flat = " | ".join(
                        " ".join(str(c) for c in r if c) for r in extracted
                    )
                    ctx_before = "".join(running_text)[-CONTEXT_WINDOW:]
                    elements.append(
                        VisualElement(
                            element_type="table",
                            id=tbl_id,
                            global_character_offset=offset,
                            location=Location(
                                chapter=current_chapter,
                                paragraph_index=para_idx,
                                page=page_num,
                            ),
                            context_before=ctx_before,
                            context_after=flat[:CONTEXT_WINDOW],
                            rows=rows,
                            cols=cols,
                        )
                    )

                # Images
                for _ in page.images:
                    img_id += 1
                    total_images += 1
                    ctx_before = "".join(running_text)[-CONTEXT_WINDOW:]
                    elements.append(
                        VisualElement(
                            element_type="image",
                            id=img_id,
                            global_character_offset=offset,
                            location=Location(
                                chapter=current_chapter,
                                paragraph_index=para_idx,
                                page=page_num,
                            ),
                            context_before=ctx_before,
                            context_after="",
                        )
                    )

                # Text → chapter detect + paragraphs
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    if _is_chapter_line(line):
                        title = line.strip()
                        if title != current_chapter:
                            current_chapter = title
                            if current_chapter not in chapters:
                                chapters.append(current_chapter)

                for para in text.split("\n\n"):
                    para = para.strip()
                    if not para:
                        continue
                    running_text.append(para + "\n")
                    offset += len(para) + 1
                    para_idx += 1
                    total_paragraphs += 1

        full_text = "".join(running_text)
        meta = BookMetadata(
            file_name=self.path.name,
            file_format=self.file_format,
            raw_character_count=len(full_text),
            body_character_count=self.body_chars(full_text),
            total_paragraphs=total_paragraphs,
            total_chapters=len(chapters),
            total_images=total_images,
            total_tables=total_tables,
            total_charts=0,
            offset_reliability=self.offset_reliability,
            total_pages=total_pages,
        )
        return ParseResult(book_metadata=meta, chapters=chapters, visual_elements=elements)
