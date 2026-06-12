from __future__ import annotations

import json
from pathlib import Path

from .schema import ParseResult


def write_json(result: ParseResult, out_path: Path) -> None:
    out_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_summary(result: ParseResult) -> None:
    m = result.book_metadata
    print(f"File:              {m.file_name}  ({m.file_format})")
    print(f"Body chars:        {m.body_character_count:,}")
    print(f"Raw chars:         {m.raw_character_count:,}")
    print(f"Paragraphs:        {m.total_paragraphs:,}")
    if m.total_pages:
        print(f"Pages:             {m.total_pages}")
    print(f"Chapters:          {m.total_chapters}")
    print(f"Images:            {m.total_images}")
    print(f"Tables:            {m.total_tables}")
    print(f"Offset reliability:{m.offset_reliability}")
    if result.visual_elements:
        print("\nVisual elements:")
        body = max(m.body_character_count, 1)
        for ve in result.visual_elements:
            loc = ve.location
            if loc.page and m.total_pages:
                where = f"page {loc.page}/{m.total_pages} ({loc.page / m.total_pages * 100:.0f}%)"
            elif loc.page:
                where = f"page {loc.page}"
            else:
                where = f"{ve.global_character_offset / body * 100:.0f}% through"
            print(
                f"  [{ve.element_type:5}] #{ve.id:<3} {where:<22} "
                f"| {loc.chapter[:40]}"
            )


def verify_placements(result: ParseResult, sample: int = 5) -> None:
    """Print context windows around N elements for human spot-check."""
    if not result.visual_elements:
        print("(no visual elements to verify)")
        return
    step = max(1, len(result.visual_elements) // sample)
    print(f"\nPlacement verification (every {step}th element):")
    for ve in result.visual_elements[::step]:
        print(f"\n--- {ve.element_type} #{ve.id} @ offset {ve.global_character_offset} ---")
        print(f"chapter:        {ve.location.chapter}")
        print(f"paragraph_idx:  {ve.location.paragraph_index}")
        if ve.element_type == "image":
            print(f"alt_text:       {ve.alt_text!r}")
            print(f"dimensions:     {ve.width}x{ve.height}")
        elif ve.element_type == "table":
            print(f"size:           {ve.rows} rows x {ve.cols} cols")
        print(f"context before: ...{ve.context_before!r}")
        print(f"context after:  {ve.context_after!r}...")


def plan(result_path: Path) -> None:
    data = json.loads(result_path.read_text(encoding="utf-8"))
    body = data["book_metadata"]["body_character_count"]
    raw = data["book_metadata"]["raw_character_count"]
    print(f"Loaded: {data['book_metadata']['file_name']}")
    print(f"Body characters: {body:,}  (raw: {raw:,})")
    print(f"Images: {data['book_metadata']['total_images']}, "
          f"Tables: {data['book_metadata']['total_tables']}")
    raw_input_val = input("\nEnter planning constant (chars per unit/hour): ").strip()
    try:
        constant = float(raw_input_val)
    except ValueError:
        print("Invalid number.")
        return
    if constant <= 0:
        print("Constant must be > 0.")
        return
    estimate = body / constant
    print(f"\nEstimated planning allocation: {estimate:.2f} units")
