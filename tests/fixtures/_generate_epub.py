"""Generate a tiny EPUB fixture. Run once; commit the output."""
from __future__ import annotations

from pathlib import Path

from ebooklib import epub

out = Path(__file__).parent / "tiny.epub"
book = epub.EpubBook()
book.set_identifier("tiny-epub-fixture")
book.set_title("Tiny EPUB")
book.set_language("en")
chapter = epub.EpubHtml(title="Chapter 1", file_name="chap.xhtml", lang="en")
chapter.content = "<h1>Chapter 1</h1><p>Hello from the tiny EPUB fixture.</p>"
book.add_item(chapter)
book.toc = (chapter,)
book.spine = ["nav", chapter]
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())
epub.write_epub(str(out), book)
print(f"wrote {out} ({out.stat().st_size} bytes)")
