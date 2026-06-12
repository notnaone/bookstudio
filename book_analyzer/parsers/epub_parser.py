from __future__ import annotations

import ebooklib
from bs4 import BeautifulSoup, NavigableString, Tag
from ebooklib import epub

from ..schema import BookMetadata, Location, ParseResult, VisualElement
from .base import CONTEXT_WINDOW, BaseParser

_HEADING_TAGS = {"h1", "h2", "h3"}
_BLOCK_TAGS = {"p", "div", "li", "blockquote"}


class EpubParser(BaseParser):
    file_format = "epub"
    offset_reliability = "exact"

    def parse(self) -> ParseResult:
        book = epub.read_epub(str(self.path))

        running_text: list[str] = []
        offset = 0
        chapters: list[str] = []
        current_chapter = "(Front Matter)"
        para_idx = 0
        elements: list[VisualElement] = []
        img_id = tbl_id = 0
        total_paragraphs = 0
        total_images = total_tables = 0

        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "lxml")
            body = soup.body or soup
            for node in body.descendants:
                if not isinstance(node, Tag):
                    continue

                if node.name in _HEADING_TAGS:
                    title = node.get_text(" ", strip=True)
                    if title:
                        current_chapter = title
                        if current_chapter not in chapters:
                            chapters.append(current_chapter)
                    continue

                if node.name == "img":
                    img_id += 1
                    total_images += 1
                    alt = node.get("alt") or None
                    try:
                        w = int(node.get("width")) if node.get("width") else None
                    except ValueError:
                        w = None
                    try:
                        h = int(node.get("height")) if node.get("height") else None
                    except ValueError:
                        h = None
                    ctx_before = "".join(running_text)[-CONTEXT_WINDOW:]
                    ctx_after = ""
                    nxt = node.find_next(string=True)
                    if nxt:
                        ctx_after = str(nxt).strip()[:CONTEXT_WINDOW]
                    elements.append(
                        VisualElement(
                            element_type="image",
                            id=img_id,
                            global_character_offset=offset,
                            location=Location(chapter=current_chapter, paragraph_index=para_idx),
                            context_before=ctx_before,
                            context_after=ctx_after,
                            alt_text=alt,
                            width=w,
                            height=h,
                        )
                    )
                    continue

                if node.name == "table":
                    tbl_id += 1
                    total_tables += 1
                    rows_list = node.find_all("tr")
                    rows = len(rows_list)
                    cols = max((len(tr.find_all(["td", "th"])) for tr in rows_list), default=0)
                    tbl_text = node.get_text(" | ", strip=True)
                    ctx_before = "".join(running_text)[-CONTEXT_WINDOW:]
                    elements.append(
                        VisualElement(
                            element_type="table",
                            id=tbl_id,
                            global_character_offset=offset,
                            location=Location(chapter=current_chapter, paragraph_index=para_idx),
                            context_before=ctx_before,
                            context_after=tbl_text[:CONTEXT_WINDOW],
                            rows=rows,
                            cols=cols,
                        )
                    )
                    running_text.append(tbl_text + "\n")
                    offset += len(tbl_text) + 1
                    para_idx += 1
                    total_paragraphs += 1
                    continue

                if node.name in _BLOCK_TAGS:
                    # Get direct text, skip nested blocks (descendants iter will hit them).
                    direct = "".join(
                        str(c) for c in node.children if isinstance(c, NavigableString)
                    ).strip()
                    if direct:
                        running_text.append(direct + "\n")
                        offset += len(direct) + 1
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
        )
        return ParseResult(book_metadata=meta, chapters=chapters, visual_elements=elements)
