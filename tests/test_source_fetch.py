from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gdown.exceptions import FileURLRetrievalError

from studio_app.source_fetch import download_source, extract_drive_id


def test_extract_drive_id_from_share_link():
    url = "https://drive.google.com/file/d/1abcDEFghiJKLmnopQRstuVWXyz/view?usp=sharing"
    assert extract_drive_id(url) == "1abcDEFghiJKLmnopQRstuVWXyz"


def test_extract_drive_id_from_open_link():
    url = "https://drive.google.com/open?id=1abcDEFghiJKLmnopQRstuVWXyz"
    assert extract_drive_id(url) == "1abcDEFghiJKLmnopQRstuVWXyz"


def test_download_source_rejects_non_http():
    with pytest.raises(ValueError, match="http"):
        download_source("/local/path.pdf")


@patch("studio_app.source_fetch.requests.get")
def test_download_http_pdf(mock_get):
    mock_response = mock_get.return_value.__enter__.return_value
    mock_get.return_value.__enter__ = lambda self: mock_response
    mock_get.return_value.__exit__ = lambda *args: None
    mock_response.raise_for_status = lambda: None
    mock_response.iter_content = lambda chunk_size: [b"%PDF-1.4"]

    path = download_source("https://example.com/book.pdf")
    try:
        assert path.suffix == ".pdf"
        assert path.read_bytes() == b"%PDF-1.4"
    finally:
        path.unlink(missing_ok=True)


@patch("studio_app.source_fetch._download_drive_requests")
@patch("studio_app.source_fetch.gdown.download")
def test_download_drive_pdf(mock_gdown, mock_requests, tmp_path: Path):
    mock_gdown.side_effect = FileURLRetrievalError("blocked")
    out_file = tmp_path / "book.pdf"
    out_file.write_bytes(b"%PDF-1.4")
    mock_requests.return_value = out_file

    path = download_source(
        "https://drive.google.com/file/d/1abcDEFghiJKLmnopQRstuVWXyz/view"
    )
    assert path.suffix == ".pdf"
    mock_requests.assert_called_once()
