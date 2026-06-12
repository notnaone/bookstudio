from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..schema import ParseResult

CONTEXT_WINDOW = 80  # chars before/after each element for placement verification


class BaseParser(ABC):
    file_format: str = ""
    offset_reliability: str = "exact"

    def __init__(self, path: Path) -> None:
        self.path = path

    @abstractmethod
    def parse(self) -> ParseResult:
        ...

    @staticmethod
    def body_chars(text: str) -> int:
        """Count visible body chars: strip whitespace."""
        return sum(1 for c in text if not c.isspace())
