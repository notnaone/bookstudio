from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(data_root: Path) -> None:
    """Write app logs to data_root/app.log with rotation."""
    data_root.mkdir(parents=True, exist_ok=True)
    log_path = data_root / "app.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for handler in list(root.handlers):
        if getattr(handler, "_studio_app_handler", False):
            root.removeHandler(handler)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    file_handler._studio_app_handler = True  # type: ignore[attr-defined]

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s: %(message)s")
    )
    stream_handler._studio_app_handler = True  # type: ignore[attr-defined]

    root.addHandler(file_handler)
    root.addHandler(stream_handler)
