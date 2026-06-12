from __future__ import annotations

from docx import Document
from docx.document import Document as _Doc
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..schema import BookMetadata, Location, ParseResult, VisualElement
from .base import CONTEXT_WINDOW, BaseParser


def _iter_block_items(parent: _Doc):
    """Yield paragraphs and tables in document order."""
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _para_has_image(p: Paragraph) -> list[dict]:
    """Return list of image info dicts found in paragraph."""
    images = []
    for drawing in p._element.iter(qn("w:drawing")):
        alt = ""
        for doc_pr in drawing.iter(qn("wp:docPr")):
            alt = doc_pr.get("descr") or doc_pr.get("title") or ""
            break
        w = h = None
        for ext in drawing.iter(qn("wp:extent")):
            try:
                w = int(ext.get("cx", 0)) // 9525  # EMU → px approx
                h = int(ext.get("cy", 0)) // 9525
            except ValueError:
                pass
            break
        images.append({"alt": alt, "w": w, "h": h})
    return images


class DocxParser(BaseParser):
    file_format = "docx"
    offset_reliability = "exact"

    def parse(self) -> ParseResult:
        doc = Document(str(self.path))
        running_text: list[str] = []
        offset = 0
        chapters: list[str] = []
        current_chapter = "(Front Matter)"
        para_idx = 0
        elements: list[VisualElement] = []
        img_id = tbl_id = 0
        total_paragraphs = 0
        total_images = total_tables = 0

        for block in _iter_block_items(doc):
            if isinstance(block, Paragraph):
                style = (block.style.name or "").lower() if block.style else ""
                text = block.text
                if style.startswith("heading") and text.strip():
                    current_chapter = text.strip()
                    if current_chapter not in chapters:
                        chapters.append(current_chapter)

                # Images inside paragraph
                imgs = _para_has_image(block)
                for info in imgs:
                    img_id += 1
                    total_images += 1
                    ctx_before = "".join(running_text)[-CONTEXT_WINDOW:]
                    elements.append(
                        VisualElement(
                            element_type="image",
                            id=img_id,
                            global_character_offset=offset,
                            location=Location(chapter=current_chapter, paragraph_index=para_idx),
                            context_before=ctx_before,
                            context_after=text[:CONTEXT_WINDOW],
                            alt_text=info["alt"] or None,
                            width=info["w"],
                            height=info["h"],
                        )
                    )

                running_text.append(text + "\n")
                offset += len(text) + 1
                para_idx += 1
                total_paragraphs += 1

            elif isinstance(block, Table):
                tbl_id += 1
                total_tables += 1
                rows = len(block.rows)
                cols = len(block.columns)
                ctx_before = "".join(running_text)[-CONTEXT_WINDOW:]
                # Flatten table text for context_after + offset advance
                tbl_text_parts = []
                for row in block.rows:
                    for cell in row.cells:
                        tbl_text_parts.append(cell.text)
                tbl_text = " | ".join(tbl_text_parts)
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
