# Deliverable 2 — The 10 Critical False Equivalences

Each entry follows the same anatomy:

- **C++ belief** — the intuition you bring.
- **Python reality** — what CPython actually does.
- **Failure** — minimal reproduction.
- **Idiom** — the correct pattern.
- **Detected by** — the lab/probe that catches it automatically.

---

## FE-1 · "Assignment and slicing copy values"

**C++ belief.** `T b = a;` invokes a copy constructor; containers deep-copy their elements.

**Python reality.** `b = a` binds a second name to the same object. Copies are explicit and **shallow by default**: `a[:]`, `list(a)`, `dict(d)`, `copy.copy(x)` duplicate the outer container but share every element.

```python
grid = [[0] * 3] * 3      # three references to ONE row
grid[0][0] = 1
grid                       # [[1, 0, 0], [1, 0, 0], [1, 0, 0]]

cfg2 = dict(cfg)           # shallow
cfg2["limits"]["rps"] = 0  # mutates cfg["limits"] too
```

**Idiom.** `[[0] * 3 for _ in range(3)]`; `copy.deepcopy` for nested mutable state (or better: immutable value objects — `@dataclass(frozen=True)`, `tuple`, `frozenset`, `types.MappingProxyType`).

**Detected by.** M1-L02 — tests assert `x is not y` and identity disjointness of nested elements via `id()` sets.

---

## FE-2 · "Default arguments are evaluated at every call"

**C++ belief.** `void f(std::vector<int> v = {})` constructs a fresh default at each call site.

**Python reality.** Default values are evaluated **once**, when `def` executes, and stored in `f.__defaults__`. A mutable default is shared state across all calls — and across threads.

```python
def enqueue(item, queue=[]):
    queue.append(item)
    return queue

enqueue(1)  # [1]
enqueue(2)  # [1, 2]   ← state leaks between calls
```

**Idiom.** `None` sentinel (`queue: list[int] | None = None` → `if queue is None: queue = []`); for dataclasses, `field(default_factory=list)` (a mutable default there raises `ValueError`).

**Detected by.** M1-L03 — calls the function twice and asserts the results are disjoint objects; inspects `fn.__defaults__` for mutable types.

---

## FE-3 · "`__del__` is a destructor, so RAII works"

**C++ belief.** Destructors run deterministically at scope exit, in reverse construction order, and may release locks, files, sockets.

**Python reality.** `__del__` runs when the refcount reaches zero — **if** it does. Objects in reference cycles are finalized only when the cyclic GC runs (timing unspecified, order unspecified). Finalizers are not guaranteed at interpreter shutdown; exceptions raised inside `__del__` are printed and swallowed; the object can be resurrected; PyPy has no refcounting at all. Also, block scope does not exist: leaving an `if`/`for` block doesn't drop anything.

```python
class Conn:
    def __init__(self): self.sock = socket.create_connection(addr)
    def __del__(self):  self.sock.close()   # "RAII"

c = Conn(); c.self_ref = c   # one cycle → socket stays open until a GC pass
```

**Idiom.** Context managers (`__enter__`/`__exit__`, `@contextmanager`, `ExitStack`) for deterministic release; `weakref.finalize` as a *safety net* only.

**Detected by.** M3-L01 — runs with `gc.disable()`, asserts the resource is closed immediately after the `with` block, and that no `ResourceWarning` is emitted.

---

## FE-4 · "`threading.Thread` uses multiple cores for compute"

**C++ belief.** N `std::thread`s on N cores ≈ N× throughput for CPU-bound work.

**Python reality.** On the default (GIL) build only one thread executes Python bytecode at a time. CPU-bound pure-Python work on 8 threads runs at ~1× (often *slower*, due to GIL hand-off contention). Threads accelerate **I/O-bound** work and C code that releases the GIL.

```python
with ThreadPoolExecutor(8) as ex:          # 8 threads
    list(ex.map(sha_loop_in_pure_python, chunks))   # ≈ single-core wall time
```

**Idiom.** `ProcessPoolExecutor` (or `InterpreterPoolExecutor`, 3.14) for CPU-bound Python; NumPy/hashlib/zlib for GIL-releasing kernels; threads/asyncio for I/O; free-threaded `python3.14t` when all dependencies support it. Measure, don't assume.

**Detected by.** M5-L04 — a scaling harness that measures speedup curves for threads vs processes and asserts the learner's chosen executor reaches a target speedup (skips the thread assertion on free-threaded builds).

---

## FE-5 · "The GIL makes my code thread-safe" / "built-in ops are atomic, so my compound ops are"

**C++ belief (inverted).** Coming from "data races are UB", a C++ developer hears "the GIL serializes everything" and concludes Python code needs no locks.

**Python reality.** The GIL makes *individual* bytecodes and C-implemented methods (`list.append`, `dict.__setitem__`) appear atomic. It says nothing about *sequences* of them. Read-modify-write and check-then-act are races. Iterating a dict while another thread inserts raises `RuntimeError: dictionary changed size during iteration`. On the free-threaded build, even the "accidental" atomicity guarantees are implemented differently (per-object locks), and anything that worked by luck becomes visible.

```python
# Lost update
self.stats[key] = self.stats.get(key, 0) + 1   # LOAD … BINARY_OP … STORE

# Check-then-act (thundering herd)
if key not in cache:            # T1 and T2 both see a miss
    cache[key] = load(key)      # load() does I/O → GIL released → both load
```

**Idiom.** Protect invariants, not variables: one `threading.Lock` per invariant, held across the whole compound operation; prefer **ownership confinement** (one thread owns the state, others send messages via `queue.Queue`); per-key locks or futures for single-flight caching.

**Detected by.** M5-L01 (single-flight cache) and M5-L02 (lost-update bank ledger) — `threading.Barrier`-synchronized stampedes with an I/O-yielding loader, plus `sys.setswitchinterval(1e-6)` to amplify interleavings.

---

## FE-6 · "`==` vs `is` is value-compare vs pointer-compare, and `is` is the fast one for small values"

**C++ belief.** Comparing pointers is a cheap identity check; for "small things" identity and equality coincide.

**Python reality.** `is` compares object identity (`id`). It *appears* to work for small ints (−5…256 are cached singletons) and some strings (interning), then silently fails for larger values or computed strings — and behaviour differs between REPL, scripts, and constant folding.

```python
a = 256; b = 256;   a is b    # True  (cached)
a = 1000; b = int("1000"); a is b   # False
"svc-" + name is "svc-a"           # False (and a SyntaxWarning)
```

**Idiom.** `==` for values. `is` only for singletons and sentinels: `None`, `True/False`, `Ellipsis`, `NotImplemented`, module-level `_MISSING = object()`, enum members.

**Detected by.** M1 static check (ruff `F632`) + runtime tests feeding non-cached values.

---

## FE-7 · "`int` is a machine integer"

**C++ belief.** `uint32_t` wraps modulo 2³², signed overflow is UB, `/` and `%` truncate toward zero, ints are unboxed and cheap.

**Python reality.**

- `int` is arbitrary precision (`PyLongObject`, 30-bit digits). There is **no wrap-around**: hash functions, checksums and PRNGs ported from C silently produce huge numbers.
- `//` and `%` use **floor** semantics: `-7 // 2 == -4`, `-7 % 2 == 1` (C/C++: `-3` and `-1`).
- `>>` on negatives is arithmetic with infinite sign extension; `~x == -x - 1`.
- Every int outside the small-int cache is a heap object (≥28 B).

```python
def fnv1a_32(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h = (h ^ b) * 0x01000193       # grows unbounded — not FNV-1a anymore
    return h
```

**Idiom.** Mask explicitly (`& 0xFFFF_FFFF`); `math.trunc(a / b)` or `int(a / b)` only when you truly need C semantics (beware float precision), or `divmod` with explicit sign handling; `struct`/`int.to_bytes(4, "little", signed=False)` at boundaries; `numpy.uint32` when you want wrap-around semantics in bulk.

**Detected by.** M2-L03 — property-based tests (Hypothesis) compare against reference C outputs captured as fixtures; M7-L01 (varint/zigzag encoder) exercises negative-number encoding.

---

## FE-8 · "A `list` is a `std::vector<T>` and an object is a `struct`"

**C++ belief.** Containers store values contiguously; an object's fields are laid out inline at fixed offsets.

**Python reality.** A `list` is a `std::vector<PyObject*>` — contiguous **pointers** to individually heap-allocated, boxed elements. A plain class instance stores attributes through a dict-like structure (3.11+ inline values with shared keys, but still pointers to boxed values). Memory footprint is often 4–10× the C++ equivalent, and every access is pointer-chasing.

```python
pts = [Point(x, y) for x, y in coords]   # 1M points: tens of MB
xs  = [p.x for p in pts]                 # per-element attribute lookup + box
```

**Idiom.** `__slots__` / `@dataclass(slots=True)` for many small records; `array.array`, `bytes`/`bytearray`/`memoryview`, `struct` for binary data; NumPy structured arrays or columnar layouts for numeric bulk data. Measure with `tracemalloc`, not `sys.getsizeof` (which is shallow).

**Detected by.** M2-L01 — `tracemalloc` footprint budget per instance; asserts `not hasattr(obj, "__dict__")`.

---

## FE-9 · "Variables are block-scoped and lambdas capture by value"

**C++ belief.** `for (int i…) { auto f = [=]{ return i; }; }` captures the current `i`; variables die at the closing brace.

**Python reality.** Scope is **function-level** (LEGB: Local, Enclosing, Global, Builtins). Loop variables outlive the loop. Closures capture **variables (cells)**, not values — equivalent to C++ `[&]` on a variable that keeps changing. Callbacks registered in a loop all see the final value.

```python
handlers = [lambda: i for i in range(3)]
[h() for h in handlers]            # [2, 2, 2]

for task_id in ids:
    executor.submit(lambda: process(task_id))   # races with the loop variable
```

**Idiom.** Bind at creation time: `functools.partial(process, task_id)`, `executor.submit(process, task_id)`, or `lambda i=i: i`. Assigning to a name anywhere in a function makes it local everywhere in that function (`UnboundLocalError`); use `nonlocal`/`global` deliberately.

**Detected by.** M4-L03 / M5 labs — callbacks submitted to executors are checked for receiving distinct arguments.

---

## FE-10 · "Check first, then act (LBYL); exceptions are for exceptional cases"

**C++ belief.** Exceptions are expensive and banned in hot paths (`-fno-exceptions`); validate with `if` before acting; return error codes.

**Python reality.** EAFP is idiomatic *and* safer. Since 3.11, `try` blocks are "zero-cost" on the happy path (exception tables instead of setup opcodes). LBYL across a system boundary is a **TOCTOU race**: the state can change between the check and the act — the same bug class as FE-5, but against the filesystem, network, or another process.

```python
if os.path.exists(path):          # check
    with open(path) as f: ...     # act — file may be gone by now

if key in d:                      # two hash lookups, racy if d is shared
    v = d[key]
```

**Idiom.** `try: … except FileNotFoundError:`; `d.get(key)`, `d.setdefault`; `os.open(path, O_CREAT | O_EXCL)` for atomic creation; catch **specific** exceptions, never bare `except:` (which also traps `KeyboardInterrupt`, `SystemExit`, and in asyncio code must never swallow `CancelledError`); use `raise … from err` to preserve causal chains.

**Detected by.** M3-L03 — fault-injection tests delete files / close sockets between operations; asserts specific exception types and preserved `__cause__`.

---

## Honorable Mentions (covered inside modules)

| Trap | Module |
|:---|:---|
| `sys.getsizeof` is shallow; it excludes referenced objects | M2 |
| Generators/iterators are single-pass (`map`, `zip`, file objects) — unlike re-iterable C++ ranges over containers | M2 |
| Defining `__eq__` sets `__hash__ = None` — instances become unhashable | M4 |
| `from module import name` copies the binding; monkeypatching `module.name` later isn't seen | M4 |
| `Condition.wait()` without a predicate loop | M5 |
| Python threads cannot be killed; daemon threads die mid-operation at exit | M5 |
| `time.sleep()` / blocking I/O inside `async def` freezes the whole event loop | M6 |
| `asyncio.create_task()` result not referenced → task may be garbage-collected mid-flight | M6 |
| Swallowing `asyncio.CancelledError` breaks timeouts and `TaskGroup` | M6 |
| Proto3 scalar fields can't distinguish "unset" from default without `optional` | M7 |
| Assigning a message to a Protobuf submessage field raises; use `CopyFrom`/`MergeFrom` | M7 |
| A sync gRPC server with streaming RPCs exhausts its `ThreadPoolExecutor` | M8 |
| No client deadline ⇒ RPCs can hang forever | M8 |
