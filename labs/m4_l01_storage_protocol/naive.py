"""M4-L01 · NAIVE translation — nominal base class requiring inheritance.

DO NOT EDIT: the test-suite must keep failing on this file (see `lab.py verify`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def put(self, key: str, val: bytes) -> None:
        raise NotImplementedError


class StorageService:
    def __init__(self, backend: object) -> None:
        # Naive: enforces nominal subclassing, rejecting valid duck-typed objects!
        if not isinstance(backend, StorageBackend):
            raise TypeError("backend must inherit from StorageBackend")
        self.backend: StorageBackend = backend

    def read(self, key: str) -> bytes:
        return self.backend.get(key)

    def write(self, key: str, val: bytes) -> None:
        self.backend.put(key, val)
