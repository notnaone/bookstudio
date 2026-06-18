"""Download book source files from HTTP(S) URLs and Google Drive share links."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import gdown
import requests

try:
    from gdown.exceptions import FileURLRetrievalError
except ImportError:  # pragma: no cover - older gdown
    FileURLRetrievalError = RuntimeError

SUPPORTED_EXTS = {".txt", ".docx", ".epub", ".pdf"}
_DRIVE_HOSTS = {"drive.google.com", "docs.google.com"}
_DRIVE_ID_RE = re.compile(
    r"/(?:file/d|document/d|presentation/d|spreadsheets/d)/([\w-]{20,})"
)
_DRIVE_EXPORT_URL = "https://docs.google.com/uc?export=download"


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


def _drive_confirm_token(response: requests.Response) -> str | None:
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            return value
    match = re.search(r"confirm=([0-9A-Za-z_]+)", response.text[:2048])
    return match.group(1) if match else None


def _filename_from_response(response: requests.Response, fallback: str) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";\n]+)"?', disposition)
    if match:
        return match.group(1).strip()
    return fallback


def _validate_downloaded_path(path: Path) -> Path:
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError(
            f"Downloaded file type {path.suffix!r} is not supported. "
            f"Use one of: {', '.join(sorted(SUPPORTED_EXTS))}"
        )
    if path.stat().st_size == 0:
        raise RuntimeError("Downloaded file is empty.")
    return path


def _download_drive_requests(file_id: str) -> Path:
    session = requests.Session()
    response = session.get(
        _DRIVE_EXPORT_URL,
        params={"id": file_id},
        stream=True,
        timeout=120,
    )
    token = _drive_confirm_token(response)
    if token:
        response = session.get(
            _DRIVE_EXPORT_URL,
            params={"id": file_id, "confirm": token},
            stream=True,
            timeout=120,
        )
    response.raise_for_status()
    filename = _filename_from_response(response, f"drive-{file_id}")
    suffix = Path(filename).suffix.lower() or ".bin"
    tmp = Path(tempfile.gettempdir()) / f"studio_app_drive{suffix}"
    with tmp.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if chunk:
                handle.write(chunk)
    return _validate_downloaded_path(tmp)


def _download_drive(file_id: str) -> Path:
    out_dir = Path(tempfile.gettempdir()) / "studio_app_drive"
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in out_dir.iterdir():
        try:
            path.unlink()
        except OSError:
            pass

    drive_url = f"https://drive.google.com/uc?id={file_id}"
    try:
        result = gdown.download(
            url=drive_url,
            output=str(out_dir) + "/",
            quiet=True,
            fuzzy=True,
        )
        if result:
            return _validate_downloaded_path(Path(result))
    except FileURLRetrievalError:
        pass

    try:
        return _download_drive_requests(file_id)
    except requests.HTTPError as exc:
        raise RuntimeError(
            "Google Drive download failed. Share the file as "
            "'Anyone with the link' or upload the file directly instead of a URL."
        ) from exc
    except (ValueError, OSError) as exc:
        raise RuntimeError(
            "Google Drive download failed. Share the file as "
            "'Anyone with the link' or upload the file directly instead of a URL."
        ) from exc


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
    return _validate_downloaded_path(tmp)
