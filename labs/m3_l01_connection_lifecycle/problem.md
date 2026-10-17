# M3-L01 · Deterministic Connection Release

## Problem

Network socket descriptors and database handles must be released immediately when processing finishes.
In C++, RAII guarantees that when an object leaves scope, its destructor runs deterministically,
closing the underlying resource regardless of whether the scope exited normally or via an exception.

In this lab, you will implement a `ManagedConnection` that guarantees deterministic cleanup.

### Required API

| Member | Semantics |
|:---|:---|
| `ManagedConnection(endpoint: str)` | Initialize connection to endpoint |
| `send(msg: str) -> None` | Send message (raises `RuntimeError` if closed) |
| `recv() -> str` | Receive message (raises `RuntimeError` if closed) |
| `close() -> None` | Close connection immediately and set `is_closed = True` |
| `is_closed: bool` | Returns whether connection is closed |
| `__enter__() -> ManagedConnection` | Enter context |
| `__exit__(exc_type, exc_val, tb) -> None` | Exit context, always calling `close()` |

## The C++ Mental Model

In [reference.cpp](./reference.cpp), `Connection` implements a standard destructor `~Connection()`.
Because C++ variables have block scope and values reside on the stack, exiting a `{ ... }` block
immediately invokes the destructor, freeing the file descriptor with zero garbage collector latency.

## The Naive Translation

In [naive.py](./naive.py), a C++ developer writes a `__del__` method thinking it is identical to a destructor.
However:
1. In Python, objects do not die at block exit; they die when their reference count reaches zero.
2. In real-world systems, connections frequently register event callbacks or handlers, creating reference cycles (`conn -> callback -> conn`).
3. When a reference cycle exists, `__del__` is **not** called when the variable goes out of scope. It is delayed until the cyclic GC runs (which may be disabled in latency-critical microservices).
4. Furthermore, `naive.py` does not implement `__enter__` and `__exit__`, so using `with ManagedConnection(...)` fails with an `AttributeError`.

## Your Task

Refactor [solution.py](./solution.py) to implement the Python context manager protocol (`__enter__` and `__exit__`).
Ensure that exiting the `with` block closes the connection deterministically, even if cyclic callbacks are registered and the cyclic GC is disabled.

## Verification

```bash
./lab.py test M3-L01
./lab.py verify M3-L01
```
