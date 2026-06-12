"""Sum total duration of audio files in a folder (recursive)."""

from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile

AUDIO_EXTS = {
    ".mp3", ".wav", ".flac", ".m4a", ".aac",
    ".ogg", ".opus", ".wma", ".mp4", ".aiff", ".aif",
}


def scan_folder(folder: Path) -> tuple[float, int, list[str]]:
    """Return (total_seconds, file_count, errors)."""
    total = 0.0
    count = 0
    errors: list[str] = []
    for p in folder.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
            continue
        try:
            mf = MutagenFile(str(p))
            if mf is None or not getattr(mf, "info", None):
                errors.append(f"{p.name}: unreadable")
                continue
            length = float(mf.info.length)
            if length <= 0:
                errors.append(f"{p.name}: zero length")
                continue
            total += length
            count += 1
        except Exception as e:
            errors.append(f"{p.name}: {type(e).__name__}: {e}")
    return total, count, errors
