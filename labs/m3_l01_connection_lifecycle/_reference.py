"""M3-L01 · IDIOMATIC reference (spoiler).

Implements the context manager protocol (__enter__ and __exit__) for deterministic
cleanup. Cleanup runs reliably on normal scope exit or exception exit, regardless
of reference cycles or GC state.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any, Self


class ManagedConnection:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.is_closed = False
        self._buffer: list[str] = []
        self._callback: Callable[[], Any] | None = None

    def register_listener(self, cb: Callable[[], Any]) -> None:
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
        if not self.is_closed:
            self.is_closed = True
            self._buffer.clear()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # Deterministically clean up resources; falsy return ensures exceptions propagate
        self.close()
