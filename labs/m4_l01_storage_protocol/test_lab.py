"""M4-L01 · Verification harness for Protocol and structural subtyping.

Run:  ./lab.py test M4-L01 [--target naive|solution|reference]
"""

from __future__ import annotations

from types import ModuleType

import pytest


# Standalone class that does NOT inherit from any framework base class
class UnrelatedMemoryStorage:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    def get(self, key: str) -> bytes:
        return self.data.get(key, b"")

    def put(self, key: str, val: bytes) -> None:
        self.data[key] = val


# Incompatible class missing `put`
class ReadOnlyStorage:
    def get(self, key: str) -> bytes:
        return b"data"


# --------------------------------------------------------------------------- C1
@pytest.mark.criterion("C1")
def test_storage_service_delegation(impl: ModuleType) -> None:
    # A formally conforming backend that subclasses StorageBackend (works for both ABC and Protocol)
    class ConformingBackend(impl.StorageBackend):
        def __init__(self) -> None:
            self.store: dict[str, bytes] = {}

        def get(self, key: str) -> bytes:
            return self.store.get(key, b"")

        def put(self, key: str, val: bytes) -> None:
            self.store[key] = val

    backend = ConformingBackend()
    service = impl.StorageService(backend)
    service.write("k1", b"v1")
    assert service.read("k1") == b"v1"


# --------------------------------------------------------------------------- C2
@pytest.mark.criterion("C2")
def test_protocol_isinstance_check(impl: ModuleType) -> None:
    backend = UnrelatedMemoryStorage()
    assert isinstance(backend, impl.StorageBackend), (
        "StorageBackend is not a `@runtime_checkable Protocol`. "
        "A standalone class providing `get` and `put` must satisfy `isinstance` "
        "without explicit inheritance."
    )


# --------------------------------------------------------------------------- C3
@pytest.mark.criterion("C3")
def test_accepts_duck_typed_backend(impl: ModuleType) -> None:
    backend = UnrelatedMemoryStorage()
    service = impl.StorageService(backend)
    service.write("session:1", b"token_123")
    assert service.read("session:1") == b"token_123"


# --------------------------------------------------------------------------- C4
@pytest.mark.criterion("C4")
def test_rejects_incompatible_backend(impl: ModuleType) -> None:
    with pytest.raises(TypeError):
        impl.StorageService(ReadOnlyStorage())
    with pytest.raises(TypeError):
        impl.StorageService("not-a-backend")
