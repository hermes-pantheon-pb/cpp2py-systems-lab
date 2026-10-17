# M4-L01 · Pluggable Storage Protocol

## Problem

In enterprise systems and microservices, core business logic must depend on abstract interfaces
rather than concrete storage implementations (Dependency Inversion Principle).
In C++, this is achieved using abstract base classes with virtual destructors (`virtual void put(...) = 0;`)
or C++20 Concepts (`template<typename T> requires StorageBackend<T>`).

In this lab, you will define a pluggable storage interface using modern Python structural typing.

### Required API

| Member | Semantics |
|:---|:---|
| `StorageBackend(Protocol)` | Structural interface with `get(key: str) -> bytes` and `put(key: str, val: bytes) -> None` |
| `StorageService(backend: StorageBackend)` | Wraps a backend; validates conformance (raises `TypeError` on mismatch) |
| `StorageService.read(key: str) -> bytes` | Delegates to `backend.get(key)` |
| `StorageService.write(key: str, val: bytes)` | Delegates to `backend.put(key, val)` |

## The C++ Mental Model

In [reference.cpp](./reference.cpp), C++ uses either nominal virtual inheritance (`class IBackend`)
or template concepts. Virtual dispatch relies on vtable pointers (`_vptr`) populated at construction time.

## The Naive Translation

In [naive.py](./naive.py), a C++ developer relies on nominal inheritance (`class AbstractStorage`)
and checks `if not isinstance(backend, AbstractStorage): raise TypeError(...)`.
This breaks structural typing: any third-party backend (e.g. `ThirdPartyRedis`, a raw dict adapter,
or a testing fake) that implements `get` and `put` is rejected simply because it does not explicitly
subclass `AbstractStorage`.

## Your Task

Refactor [solution.py](./solution.py) to use `typing.Protocol` with `@runtime_checkable`.
Ensure that `StorageService` accepts any object satisfying the interface structurally,
while rejecting non-conforming objects with `TypeError`.

## Verification

```bash
./lab.py test M4-L01
./lab.py verify M4-L01
```
