"""M4-L01 · IDIOMATIC reference (spoiler).

Uses `typing.Protocol` with `@runtime_checkable` to enable structural subtyping.
Any object that provides `get(key)` and `put(key, val)` is valid, without nominal inheritance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    def get(self, key: str) -> bytes: ...
    def put(self, key: str, val: bytes) -> None: ...


class StorageService:
    def __init__(self, backend: object) -> None:
        if not isinstance(backend, StorageBackend):
            raise TypeError(f"{backend!r} does not satisfy StorageBackend protocol")
        self.backend: StorageBackend = backend

    def read(self, key: str) -> bytes:
        return self.backend.get(key)

    def write(self, key: str, val: bytes) -> None:
        self.backend.put(key, val)
