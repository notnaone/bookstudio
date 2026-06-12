from __future__ import annotations

from pathlib import Path

from .base import BaseParser
from .docx_parser import DocxParser
from .epub_parser import EpubParser
from .pdf_parser import PdfParser
from .txt_parser import TxtParser

_REGISTRY: dict[str, type[BaseParser]] = {
    ".txt": TxtParser,
    ".docx": DocxParser,
    ".epub": EpubParser,
    ".pdf": PdfParser,
}


def get_parser(path: Path) -> BaseParser:
    ext = path.suffix.lower()
    cls = _REGISTRY.get(ext)
    if cls is None:
        raise ValueError(f"Unsupported file format: {ext}")
    return cls(path)


__all__ = ["BaseParser", "get_parser"]
