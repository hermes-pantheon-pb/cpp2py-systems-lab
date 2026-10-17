"""M3-L01 · NAIVE translation — attempting to use __del__ as an RAII destructor.

DO NOT EDIT: the test-suite must keep failing on this file (see `lab.py verify`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ManagedConnection:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.is_closed = False
        self._buffer: list[str] = []
        self._callback: Callable[[], Any] | None = None

    def register_listener(self, cb: Callable[[], Any]) -> None:
        # Often creates a cycle: conn -> cb (holding conn)
        self._callback = cb

    def send(self, msg: str) -> None:
        if self.is_closed:
            raise RuntimeError("Connection closed")
        self._buffer.append(msg)

    def recv(self) -> str:
        if self.is_closed:
            raise RuntimeError("Connection closed")
        return self._buffer.pop(0) if self._buffer else ""

    def close(self) -> None:
        self.is_closed = True

    def __del__(self) -> None:
        # Naive: relying on __del__ as an RAII destructor
        self.close()
