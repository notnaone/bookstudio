from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

ElementType = Literal["table", "image", "chart"]
OffsetReliability = Literal["exact", "approximate"]


@dataclass
class Location:
    chapter: str
    paragraph_index: int
    page: int | None = None


@dataclass
class VisualElement:
    element_type: ElementType
    id: int
    global_character_offset: int
    location: Location
    # Verification context — surrounding text for placement check.
    context_before: str = ""
    context_after: str = ""
    # Image-specific
    alt_text: str | None = None
    width: int | None = None
    height: int | None = None
    # Table-specific
    rows: int | None = None
    cols: int | None = None


@dataclass
class BookMetadata:
    file_name: str
    file_format: str
    raw_character_count: int
    body_character_count: int
    total_paragraphs: int
    total_chapters: int
    total_images: int
    total_tables: int
    total_charts: int
    offset_reliability: OffsetReliability
    total_pages: int | None = None
    book_id: str = ""


@dataclass
class Progress:
    current_page: int = 0
    current_paragraph: int = 0
    audio_hours: float = 0.0
    narrator: str = ""
    completed: bool = False
    final_chars_per_hour: float = 0.0
    audio_folder: str = ""
    auto_scan: bool = False
    updated_at: str = ""


@dataclass
class ParseResult:
    book_metadata: BookMetadata
    visual_elements: list[VisualElement] = field(default_factory=list)
    chapters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "book_metadata": asdict(self.book_metadata),
            "chapters": self.chapters,
            "visual_elements": [asdict(v) for v in self.visual_elements],
        }
