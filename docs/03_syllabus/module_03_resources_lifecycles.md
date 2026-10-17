# Module 3 — Resource Management & Lifecycles

**Learning outcomes.**

1. Translate any RAII type (file, socket, lock guard, transaction, scope guard) into a context manager.
2. Implement context managers as classes and as generators, with correct exception semantics.
3. Compose dynamic sets of resources with `ExitStack` / `AsyncExitStack`, including rollback on partial acquisition.
4. Design exception hierarchies for services: chaining, notes, groups, and mapping to RPC status codes (prepares M8).

---

## (a) Core Mental Model

```text
C++                                      Python
─────────────────────────────            ──────────────────────────────────────────
{                                        with Resource() as r:      # __enter__
  Resource r;          // ctor               use(r)
  use(r);                                # __exit__(exc_type, exc, tb) — ALWAYS runs
}                      // ~Resource()   # (normal exit, return, break, continue, raise)

std::lock_guard g(m);                    with m:
absl::Cleanup c = [&]{...};              stack.callback(fn)          # ExitStack
std::unique_ptr<T, Deleter>              @contextmanager + try/finally
```

**One-liner:** *Lifetime (when memory is freed) and scope (when cleanup must happen) are decoupled in Python. RAII's cleanup guarantee is reattached to **syntax** (`with`), not to object destruction.*

## (b) Systems Deep-Dive

### 1. The `with` protocol, precisely
```python
mgr   = EXPR
enter = type(mgr).__enter__      # looked up on the TYPE (like a vtable slot)
exit_ = type(mgr).__exit__
value = enter(mgr)
try:
    TARGET = value
    BODY
except BaseException as e:
    if not exit_(mgr, type(e), e, e.__traceback__):
        raise                    # falsy return → re-raise
else:
    exit_(mgr, None, None, None)
```
- `__exit__` returning truthy **suppresses** the exception — almost always a bug outside `contextlib.suppress`.
- Bytecode: `BEFORE_WITH` / exception-table entries (3.11+ zero-cost: no runtime setup on the happy path).
- Parenthesized multi-manager form (3.10+): `with (open(a) as fa, open(b) as fb):` — exits in reverse order, like C++ destructors.

### 2. Generator-based managers
- `@contextmanager`: code before `yield` = acquire; after = release. Exceptions from the body are **thrown into** the generator at the `yield` → you need `try/finally` (or `try/except/else`) or cleanup is skipped.
- `@asynccontextmanager` for `async with` (M6/M8: channels, sessions).

### 3. `ExitStack`: the dynamic scope guard
- LIFO stack of callbacks; `enter_context(cm)`, `callback(fn, *args)`, `push(exit_fn)`, `pop_all()` to *transfer ownership* out of the scope (Python's analogue of `std::move` of a guard / `release()`).
- Pattern: acquire N resources atomically — if acquisition k fails, resources 0..k−1 are released.

### 4. Finalization as a safety net
- `__del__`: semantics per [FE-3](../02_false_equivalences.md#fe-3--__del__-is-a-destructor-so-raii-works).
- `weakref.finalize(obj, release, handle)`: runs once at collection **or** interpreter exit; can be `detach()`ed after explicit close. Use it to emit `ResourceWarning` for leaked resources (as `socket` and `subprocess` do).
- `python -X dev` / `-W error::ResourceWarning` in tests to turn leaks into failures.

### 5. Exceptions as the error channel
- Hierarchy: `BaseException` ⟶ {`SystemExit`, `KeyboardInterrupt`, `GeneratorExit`, `asyncio.CancelledError`, `Exception` ⟶ …}.
- Chaining: `raise X from err` (`__cause__`, explicit) vs implicit `__context__`; `raise X from None` to hide internals.
- `err.add_note()` (3.11) to annotate without wrapping; `ExceptionGroup` / `except*` for concurrent failures (TaskGroup, M6).
- Service design: a domain hierarchy (`ServiceError` → `NotFound`, `Conflict`, `Unavailable`) that maps 1:1 to gRPC `StatusCode`s in an interceptor (M8).
- `traceback` frames hold references to locals → caught exceptions stored long-term can keep large objects alive (`e.__traceback__ = None` or `traceback.clear_frames`).

## (c) Key Idioms & Gotchas

| Idiom ✅ | Anti-pattern ❌ | FE |
|:---|:---|:---|
| `with lock:` | `lock.acquire(); work(); lock.release()` (leaks on exception) | — |
| `try: yield res` / `finally: res.close()` in `@contextmanager` | Bare `yield` then cleanup | — |
| `ExitStack` + `pop_all()` for all-or-nothing acquisition | Nested `try` pyramids | — |
| `except FileNotFoundError:` (EAFP) | `if os.path.exists(...)` (TOCTOU) | FE-10 |
| `raise ConfigError(...) from err` | `raise ConfigError(str(err))` (loses chain) | — |
| `weakref.finalize` + `ResourceWarning` as leak detector | `__del__` closing sockets | FE-3 |
| `except Exception:` at task boundaries | `except:` / `except BaseException:` that swallows cancellation | FE-10 |

## (d) Interactive Lab Specification

| ID | Title | C++ anchor | Naive Python | Refactor criteria | Probes |
|:---|:---|:---|:---|:---|:---|
| M3-L01 | Deterministic Connection Release | RAII `Connection` with dtor closing fd | `__del__` closes socket; cycles from callbacks | Closed exactly at `with` exit, even on exception, with `gc.disable()`; no `ResourceWarning` | `gc_disabled`, `warnings.catch_warnings(record=True)`, fd count via `/proc/self/fd` |
| M3-L02 | All-or-Nothing Multi-Resource Acquire | Vector of `unique_ptr` guards with rollback | Sequential acquire, leaks on k-th failure | Fault-inject failure at each k; all 0..k−1 released in reverse order | Fault injector, release-order log |
| M3-L03 | Fault-Tolerant File Pipeline | `std::filesystem` + error codes | LBYL checks, broad `except`, string-wrapped errors | TOCTOU-free; specific exceptions; `__cause__` preserved; `KeyboardInterrupt` propagates | Race injector deleting files between steps |
| M3-L04 | Transaction Scope Guard | `TransactionGuard` committing in dtor unless dismissed | Generator manager without `try/finally` | Commit on success, rollback on exception, `pop_all` transfers ownership | State-machine assertions |
| M3-L05 | Domain Exception Hierarchy | `std::error_code` categories | Raising `Exception("not found")` | Hierarchy maps to status codes table; notes attached; `ExceptionGroup` handled with `except*` | Table-driven tests |

### Exit criteria
- Every resource in later modules (locks, executors, channels, servers) is managed via `with`/`async with`.
- Translation note: *"Why `__exit__` receives the exception and C++ destructors don't — and why that's an advantage."*
