from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def hold(lock: threading.Lock) -> Iterator[None]:
    """Acquire a DB write lock for the duration of the block."""
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
