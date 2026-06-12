from __future__ import annotations

import re
import unicodedata

MAX_LEN = 60


def slugify(title: str) -> str:
    """Return a filesystem- and URL-safe slug from `title`."""
    if not title or not title.strip():
        return "book"
    normalized = unicodedata.normalize("NFKD", title)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    s = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not s:
        return "book"
    return s[:MAX_LEN].rstrip("-") or "book"
