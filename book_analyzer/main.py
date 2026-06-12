from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parsers import get_parser
from .reporter import plan, print_summary, verify_placements, write_json


def cmd_parse(args: argparse.Namespace) -> int:
    src = Path(args.file)
    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        return 1
    parser = get_parser(src)
    print(f"Parsing {src.name} ({parser.file_format})...")
    result = parser.parse()
    print_summary(result)
    if args.verify:
        verify_placements(result, sample=args.verify_sample)
    out = Path(args.output) if args.output else src.with_suffix(".metadata.json")
    write_json(result, out)
    print(f"\nMetadata written: {out}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    metadata = Path(args.metadata)
    if not metadata.exists():
        print(f"Metadata file not found: {metadata}", file=sys.stderr)
        return 1
    plan(metadata)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="book-analyzer", description="Offline book parser.")
    sub = p.add_subparsers(dest="command", required=True)

    pp = sub.add_parser("parse", help="Parse a book file and emit metadata JSON.")
    pp.add_argument("file", help="Path to .txt / .docx / .epub / .pdf")
    pp.add_argument("-o", "--output", help="Output JSON path (default: <input>.metadata.json)")
    pp.add_argument("--verify", action="store_true", help="Print placement verification context.")
    pp.add_argument("--verify-sample", type=int, default=5, help="Sample size for verification.")
    pp.set_defaults(func=cmd_parse)

    pl = sub.add_parser("plan", help="Load metadata JSON and compute planning estimate.")
    pl.add_argument("metadata", help="Path to metadata JSON produced by `parse`.")
    pl.set_defaults(func=cmd_plan)

    return p


def cli() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(cli())
