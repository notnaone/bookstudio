"""Download book source files from HTTP(S) URLs and Google Drive share links."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import gdown
import requests

SUPPORTED_EXTS = {".txt", ".docx", ".epub", ".pdf"}
_DRIVE_HOSTS = {"drive.google.com", "docs.google.com"}
_DRIVE_ID_RE = re.compile(
    r"/(?:file/d|document/d|presentation/d|spreadsheets/d)/([\w-]{20,})"
)


def extract_drive_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc not in _DRIVE_HOSTS:
        return None
    match = _DRIVE_ID_RE.search(parsed.path)
    if match:
        return match.group(1)
    query = parse_qs(parsed.query)
    if "id" in query:
        return query["id"][0]
    return None


def download_source(url: str) -> Path:
    """Download a supported book file from a URL or Google Drive link."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    drive_id = extract_drive_id(url)
    if drive_id:
        return _download_drive(drive_id)
    return _download_http(url)


def _download_drive(file_id: str) -> Path:
    out_dir = Path(tempfile.gettempdir()) / "studio_app_drive"
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in out_dir.iterdir():
        try:
            path.unlink()
        except OSError:
            pass
    result = gdown.download(id=file_id, output=str(out_dir) + "/", quiet=True)
    if not result:
        raise RuntimeError(
            "Google Drive download failed. Set sharing to 'Anyone with the link'."
        )
    path = Path(result)
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError(
            f"Downloaded file type {path.suffix!r} is not supported. "
            f"Use one of: {', '.join(sorted(SUPPORTED_EXTS))}"
        )
    return path


def _download_http(url: str) -> Path:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in SUPPORTED_EXTS:
        raise ValueError(
            f"URL must point to a supported file type "
            f"({', '.join(sorted(SUPPORTED_EXTS))}), got {suffix!r}"
        )
    tmp = Path(tempfile.gettempdir()) / f"studio_app_dl{suffix}"
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                handle.write(chunk)
    return tmp
