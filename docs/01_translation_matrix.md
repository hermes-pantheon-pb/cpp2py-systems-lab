# Deliverable 1 — Comparative Mental-Model Translation Matrix

> **Thesis.** In C++, a variable is *a named region of storage with a static type*.
> In CPython, a variable is *a name, bound in a namespace, to a `PyObject*`* that points to a
> heap-allocated, self-describing, reference-counted object. Almost every trap in this curriculum
> comes from forgetting that one sentence.

Target runtime: **CPython 3.12+** (examples verified against 3.13; 3.14 notes are called out).

---

## 1. The Translation Matrix

Columns: **C/C++ construct** → **Python mechanism** → **What CPython actually does** → **Translation hazard**.

### 1.1 Memory & Object Model

| C/C++ | Python | Under the hood (CPython) | Hazard |
|:---|:---|:---|:---|
| `int x = 5;` (stack storage holding bits) | `x = 5` | Name `x` in the frame's fast-locals array now holds a `PyObject*` to the cached small-int object `5` (cache: −5…256, immortal since 3.12) | `x` *is not* storage; there is nothing to "overwrite" |
| `T* p = &obj;` | every name | All names are pointers. There is no non-pointer variable in Python | Aliasing is the default, not the exception |
| `T a = b;` (copy ctor) | `a = b` | `LOAD_FAST b` → `STORE_FAST a`: one `Py_INCREF`, one pointer store. **No copy** | Mutating `a` mutates `b` |
| `T a = std::move(b);` | `a = b; del b` | `del` unbinds the name and `Py_DECREF`s; the object lives while any reference exists | There is no "moved-from" state |
| `new T` / `delete p` | `T()` / (nothing) | `tp_alloc` via pymalloc (≤512 B objects, arena/pool/block allocator) or the system allocator; freed when `ob_refcnt` hits 0 | You never free; you *drop references* |
| `std::shared_ptr<T>` | every reference | `ob_refcnt` is an intrusive, non-atomic refcount (GIL build) — like `shared_ptr` without the control block | Cycles leak until the cyclic GC runs |
| `std::weak_ptr<T>` | `weakref.ref(obj)` / `WeakValueDictionary` | Weakref list hangs off the object (`tp_weaklistoffset`); callback fires on dealloc | Not all types are weak-referenceable (`int`, `tuple`, `__slots__` without `__weakref__`) |
| `std::unique_ptr<T>` | *(no equivalent)* | Ownership is never exclusive at the language level | Model unique ownership by convention + context managers |
| `sizeof(T)` | `sys.getsizeof(o)` | Returns the object's **own** allocation only (+ GC header if tracked) | Shallow: a list's size excludes its elements |
| `const T&` | *(no equivalent)*; `typing.Final`, `tuple`, `frozenset`, `@dataclass(frozen=True)` | Immutability is a property of the **type**, not the binding | `t = ([],)` — the tuple is immutable, the list inside isn't |
| `volatile` / `std::atomic<int>` | *(nothing at language level)* | The GIL serializes bytecodes, but compound operations are not atomic | `counter += 1` is a read-modify-write race |
| Static storage / globals | module attributes | A module is an object; globals live in `module.__dict__` | `from m import x` copies the *binding*, later rebinding of `m.x` isn't seen |

### 1.2 Types, Dispatch & Polymorphism

| C/C++ | Python | Under the hood | Hazard |
|:---|:---|:---|:---|
| `struct`/`class` with fixed layout | `class` | Instance attributes in a per-instance dict (3.11+: "inline values" with a shared-key layout, dict materialized lazily) | Typos create new attributes silently |
| Fixed-layout POD struct | `__slots__`, `@dataclass(slots=True)` | Member descriptors at fixed offsets in the instance; no `__dict__` | Lose dynamic attrs and (unless declared) weakrefs |
| vtable / `virtual` | every method call | `LOAD_ATTR` → type MRO lookup (cached per type version tag; specialized inline caches since 3.11) | Every call is "virtual" — there is no `final` devirtualization |
| `PyTypeObject` ≈ vtable + RTTI | `type(obj)` | `ob_type` → `PyTypeObject` with C slots `tp_hash`, `tp_richcompare`, `tp_iter`, `nb_add`, … | Dunder methods *are* the slots; define `__eq__` ⇒ `__hash__` becomes `None` |
| Templates / C++20 concepts | Duck typing; `typing.Protocol` | Structural check is static (mypy/pyright); at runtime nothing is checked unless `@runtime_checkable` | No monomorphization: generics are erased |
| Abstract base class (pure virtual) | `abc.ABC` + `@abstractmethod` | `ABCMeta` blocks instantiation if abstract methods remain | Nominal: requires inheritance or `register()` |
| Overloading | `functools.singledispatch`, `typing.overload` (static only) | Single runtime dispatch on first arg type | `@overload` generates no runtime dispatch |
| `operator+` | `__add__` / `__radd__` / `__iadd__` | `BINARY_OP` tries left `nb_add`, then reflected right; `NotImplemented` signals fallback | `+=` mutates lists in place but rebinds ints/tuples |
| `static_cast` / `reinterpret_cast` | `int(x)`, `struct.unpack`, `memoryview.cast` | Conversions create **new** objects | No reinterpretation of object memory |
| Compile-time type errors | `mypy --strict` / `pyright` | Annotations are stored (lazily since 3.14, PEP 649) but not enforced | Types are a *verification layer*, not a layout |

### 1.3 Containers & Data Layout

| C/C++ | Python | Layout | Hazard |
|:---|:---|:---|:---|
| `std::vector<double>` (8 B/elem, contiguous) | `list[float]` | `PyObject**` array (8 B/slot) → each `float` is a separate 24 B heap object | ~4× memory, pointer-chasing per element |
| `std::vector<double>` (true equivalent) | `array.array('d')`, `numpy.ndarray`, `bytearray` | Contiguous raw buffer, exposes the buffer protocol | Element access boxes a new `float` each time |
| `std::array<T,N>` | `tuple` | Inline `PyObject*` array, fixed size, immutable | Still pointers, not values |
| `std::unordered_map` | `dict` | Compact, insertion-ordered: sparse index table + dense entries array; open addressing with perturbed probing | Ordered ⇒ iteration order is insertion order (guaranteed since 3.7) |
| `std::unordered_set` | `set` / `frozenset` | Open addressing, linear-probe runs + perturbation, no ordering | Do not rely on iteration order |
| `std::deque` | `collections.deque` | Doubly linked list of 64-slot blocks | `deque[i]` is O(n) in the middle |
| `std::priority_queue` | `heapq` on a `list` | Binary min-heap over a list | Min-heap only; negate keys or wrap |
| `std::string` (mutable bytes) | `str` (immutable, PEP 393 flexible 1/2/4 B per code point), `bytes`, `bytearray` | `str` is immutable and may be interned | `s += x` in a loop is O(n²) in general |
| `std::span<T>` / `string_view` | `memoryview` | Zero-copy view over a buffer-protocol object | Slicing `bytes` copies; slicing `memoryview` doesn't |
| `#pragma pack` / `struct` I/O | `struct.pack`, `ctypes.Structure` | Explicit byte layout with format chars (`<I`, `!H`) | Default alignment mode `@` = native; use `<`/`>`/`!` for wire formats |

### 1.4 Resource Lifetimes & Error Handling

| C/C++ | Python | Mechanism | Hazard |
|:---|:---|:---|:---|
| RAII destructor at scope exit | `with` statement | `__enter__` / `__exit__(exc_type, exc, tb)`; `__exit__` runs on normal exit, `return`, `break`, and exceptions | Scope ≠ lifetime; a block (`if`, `for`) does not end a lifetime |
| Destructor `~T()` | `__del__` | Called when refcount → 0 *if* that happens; in cycles at GC time (PEP 442); not guaranteed at shutdown; exceptions are swallowed | **Never** use for correctness-critical release |
| `std::lock_guard` | `with lock:` | `Lock.__enter__` = `acquire()` | — |
| Scope guard / `absl::Cleanup` | `contextlib.ExitStack`, `try/finally` | LIFO callback stack | — |
| Factory returning RAII object | `@contextlib.contextmanager` | Generator: code before `yield` = ctor, after = dtor (wrap in `try/finally`) | Forgetting `try/finally` skips cleanup on exceptions |
| Custom deleter | `weakref.finalize(obj, fn, *args)` | Runs at dealloc *or* at interpreter exit (atexit) | `fn` must not reference `obj` (keeps it alive) |
| Error codes / `std::expected` | Exceptions (EAFP) | "Zero-cost" `try` since 3.11: no setup cost on the happy path | LBYL (`if exists: open`) introduces TOCTOU races |
| `noexcept` | *(no equivalent)* | Anything can raise (`MemoryError`, `KeyboardInterrupt`) | Bare `except:` catches `KeyboardInterrupt`/`SystemExit` |
| Exception hierarchy | `BaseException` → `Exception` → … | `asyncio.CancelledError` derives from `BaseException` (3.8+) | `except Exception` correctly *won't* swallow cancellation — keep it that way |
| Multiple simultaneous failures | `ExceptionGroup` + `except*` (3.11+) | Raised by `asyncio.TaskGroup` | Plain `except` won't match members of a group |

### 1.5 Compilation & Execution Model

| C/C++ | Python | Mechanism |
|:---|:---|:---|
| Translation unit → object file → link | Module → bytecode (`__pycache__/*.pyc`) → executed top-to-bottom on import | `import` *executes* the module once, then caches in `sys.modules` |
| Header + include guards | `import` + `sys.modules` cache | Circular imports see partially-initialized modules |
| Static/dynamic linking | Import system finders/loaders, `sys.path` | Extension modules (`.so`) are `dlopen`ed |
| `-O2` optimizer | Specializing adaptive interpreter (PEP 659, 3.11+), experimental JIT (3.13+, `--enable-experimental-jit`) | Bytecodes are rewritten in place into type-specialized variants after warm-up |
| `constexpr` / compile-time | Import-time execution | Decorators and class bodies *run* at import |
| Preprocessor macros | Decorators, metaclasses, `__init_subclass__`, descriptors | Runtime metaprogramming |
| ABI / `extern "C"` | CPython C API, Limited API / Stable ABI (`abi3`), `ctypes`, `cffi`, Cython, pybind11/nanobind | Native code can release the GIL |

### 1.6 Concurrency

| C/C++ | Python | Mechanism | Hazard |
|:---|:---|:---|:---|
| `std::thread` | `threading.Thread` | Real OS thread (pthread) | Under the GIL, only one thread executes bytecode at a time |
| Multi-core compute via threads | `ProcessPoolExecutor`, native extensions that release the GIL, free-threaded build (3.13t/3.14t), subinterpreters (`concurrent.interpreters`, 3.14) | Separate GILs or no GIL | Processes require pickling; IPC cost |
| `std::mutex` / `lock_guard` | `threading.Lock` / `with lock:` | Non-reentrant | Re-acquiring in the same thread deadlocks |
| `std::recursive_mutex` | `threading.RLock` | Owner + count | Often a design smell |
| `std::condition_variable` | `threading.Condition` | Wait releases the lock; must re-check predicate (`wait_for(pred)`) | Spurious/stolen wakeups |
| `std::counting_semaphore` | `threading.Semaphore`, `BoundedSemaphore` | — | Prefer `BoundedSemaphore` to catch over-release |
| `std::latch` / `std::barrier` | `threading.Barrier`, `threading.Event` | — | — |
| `std::atomic<T>` | *(none)*; use `Lock`, `queue.Queue`, `itertools.count()` (atomic `next` under GIL in practice) | — | Don't build lock-free algorithms in Python |
| `thread_local` | `threading.local()`; `contextvars.ContextVar` (async-aware) | — | `threading.local` leaks across tasks in asyncio |
| `std::future` / `std::async` | `concurrent.futures.Future`, `Executor.submit` | Thread/process pools | Exceptions are stored and re-raised at `.result()` |
| Lock-free MPMC queue | `queue.Queue` (blocking, bounded) / `queue.SimpleQueue` | Lock + Conditions internally | The default inter-thread communication primitive |
| `epoll` loop / Boost.Asio `io_context` | `asyncio` event loop | `selectors.EpollSelector` (Linux) + ready-callback deque + timer heap | One blocking call stalls *every* task |
| C++20 coroutines | `async def` / `await` | Coroutine objects driven by `Task.__step()` via `send()` | Un-awaited coroutine never runs |
| `std::jthread` + `stop_token` | `asyncio.TaskGroup` + cancellation, `threading.Event` | Cooperative cancellation | Python threads cannot be killed |

---

## 2. Under the Hood

### 2.1 The `PyObject` header

Every Python object starts with this header (default, GIL-enabled build, 64-bit, 3.12+, simplified from `Include/object.h`):

```c
typedef struct _object {
    union {
        Py_ssize_t ob_refcnt;          /* 8 bytes: reference count            */
        uint32_t   ob_refcnt_split[2]; /* 3.12+: low half used for immortality */
    };
    PyTypeObject *ob_type;             /* 8 bytes: pointer to the "vtable+RTTI" */
} PyObject;                            /* 16 bytes total                        */

typedef struct {
    PyObject   ob_base;
    Py_ssize_t ob_size;                /* number of items for var-sized objects */
} PyVarObject;
```

Consequences a C++ developer should internalize:

| Fact | Consequence |
|:---|:---|
| Every object carries 16 B of header before any payload | A `float` is 24 B (header + `double`); an `int` is ≥28 B |
| GC-tracked containers (list, dict, class instances) carry an extra pre-header for the cyclic GC (`PyGC_Head`, 16 B) | `[]` costs more than it looks |
| `ob_type` points to a `PyTypeObject` whose C slots (`tp_hash`, `tp_iter`, `nb_add`, `sq_item`, `tp_getattro`, …) are the dispatch table | `a + b` is a function-pointer call through `ob_type`, not an `ADD` instruction |
| `type(x)` is just `x->ob_type` | Types are themselves objects (instances of `type`) |
| `id(x)` is the object address in CPython | Addresses can be reused after deallocation — `id()` is not a stable identity across lifetimes |
| Immortal objects (PEP 683, 3.12): `None`, `True`, small ints, interned strings have a saturated refcount that `Py_INCREF`/`Py_DECREF` don't modify | `sys.getrefcount(None)` returns a huge sentinel; measure **deltas** on non-immortal objects only |

**Free-threaded build (PEP 703; `python3.13t`, officially supported in 3.14t):** the header grows to hold an owning thread id (`ob_tid`), a per-object mutex, and a **split refcount** — `ob_ref_local` (non-atomic, owner thread) and `ob_ref_shared` (atomic, other threads), i.e. *biased reference counting*. This is what makes removing the GIL possible without making every `Py_INCREF` an atomic RMW.

### 2.2 Reference counting vs RAII

```c
/* What Py_DECREF does, conceptually (GIL build): */
static inline void Py_DECREF(PyObject *op) {
    if (_Py_IsImmortal(op)) return;
    if (--op->ob_refcnt == 0)
        _Py_Dealloc(op);   /* -> Py_TYPE(op)->tp_dealloc(op) -> may call __del__ */
}
```

- **Deterministic in the acyclic case**: when the last reference disappears, `tp_dealloc` runs *immediately* — this is the closest thing to RAII and why `open(...).read()` "usually works" in CPython.
- **Non-deterministic in cycles**: `a.peer = b; b.peer = a` keeps both at refcount ≥1 forever; only the **cyclic GC** (`Python/gc.c`) frees them, by traversing container objects (`tp_traverse`), subtracting internal references, and finding groups unreachable from outside. Collection is triggered by allocation thresholds (`gc.get_threshold()`), not scope exit. 3.14 makes the collector incremental (young/old generations) to cut pause times.
- **Implementation-defined**: PyPy and GraalPy have no refcounting. Code that relies on refcount timing is CPython-specific.

> **Rule:** Refcounting is a *memory* strategy, not a *resource* strategy. Use `with` for files, sockets, locks, transactions, and channels.

### 2.3 Assignment is name binding, not memory copying

```python
a = [1, 2, 3]
b = a          # bind second name to SAME list object
b.append(4)    # mutate the object
a              # [1, 2, 3, 4]
b = [9]        # REBIND b; a is untouched
```

Bytecode (`dis.dis`) for `b = a`:

```
LOAD_FAST   a      # push PyObject* (Py_INCREF)
STORE_FAST  b      # store into fast-locals slot (Py_XDECREF old value)
```

C-equivalent semantics:

```c
PyObject *a = PyList_New(...);
PyObject *b = a; Py_INCREF(b);   /* alias — never a memcpy */
```

Three operations you must keep distinct:

| Operation | Python syntax | Effect |
|:---|:---|:---|
| **Rebind** a name | `x = y`, `x = x + 1` (int) | Changes which object the name points to |
| **Mutate** an object | `x.append(1)`, `x[0] = 1`, `x.attr = 1`, `x += [1]` (list) | Changes the object; visible through every alias |
| **Copy** an object | `copy.copy(x)`, `x[:]`, `list(x)`, `dict(x)`, `copy.deepcopy(x)` | Explicit, and shallow unless `deepcopy` |

**Argument passing** is "call by sharing": the callee receives copies of the *pointers* (like passing `PyObject*` by value). The callee can mutate the caller's object but cannot rebind the caller's name.

### 2.4 Pointer indirection costs

Summing one million floats:

| Representation | Memory | Per-element work in the hot loop |
|:---|:---|:---|
| `std::vector<double>` | 8 MB contiguous | 1 load, 1 `addsd`; vectorizable; HW prefetcher friendly |
| `list[float]` | 8 MB pointer array + 24 MB of `float` objects (≈32 MB), objects possibly scattered | Load pointer → load `ob_type` → type guard → load `ob_fval` → allocate **new** result float → decref old → dispatch next bytecode |
| `array.array('d')` | 8 MB contiguous | Contiguous storage, but each `a[i]` **boxes** a fresh `float` |
| `numpy.ndarray` / `math.fsum` / `sum()` builtin | 8 MB contiguous | The loop runs in C; no per-element bytecode dispatch |

The specializing interpreter (3.11+) removes much of the *dispatch* overhead (`BINARY_OP` → `BINARY_OP_ADD_FLOAT`, `LOAD_ATTR` → `LOAD_ATTR_INSTANCE_VALUE`), but cannot remove **boxing** or **indirection**. The systems lesson: *move loops into C* (builtins, `itertools`, `numpy`, `struct.iter_unpack`, `bytes.translate`) and *choose contiguous containers* for bulk numeric data.

### 2.5 The GIL: memory safety vs multi-core scaling

**What it is.** A per-interpreter mutex (`Python/ceval_gil.c`) that a thread must hold to execute bytecode or touch Python objects.

**Why it exists.** `ob_refcnt` increments are plain, non-atomic `++`/`--`. Without a global lock, two threads `Py_INCREF`ing the same object could lose an update → premature free → use-after-free. The GIL also makes the allocator (pymalloc) and every built-in container internally consistent, and made C extensions trivially safe to write. It is a coarse-grained lock that buys **interpreter memory safety**.

**How switching works.**

1. Thread B wants the GIL, waits up to `sys.getswitchinterval()` (default 5 ms).
2. On timeout, B sets a *drop request* in the holder's **eval breaker**.
3. Thread A checks the eval breaker at specific points (function entry, backward jumps — since 3.10 not after every bytecode), releases the GIL, and B is scheduled.
4. Blocking I/O and many C functions release the GIL explicitly (`Py_BEGIN_ALLOW_THREADS`): `socket.recv`, `time.sleep`, `file.read`, `select`, `hashlib`/`zlib` on large buffers, NumPy kernels, gRPC's C core.

**What it does NOT give you.** Atomicity of *your* invariants. `self.balance -= amount` compiles to `LOAD_ATTR`, `BINARY_OP`, `STORE_ATTR` — a thread switch between load and store loses updates. Check-then-act (`if k not in d: d[k] = make()`) is a race whenever `make()` can release the GIL (I/O, or simply a long enough function).

**Scaling consequences.**

| Workload | Threads under the GIL | Correct tool |
|:---|:---|:---|
| I/O-bound (network, disk, RPC) | ✅ Real speedup: waiting threads don't hold the GIL | `ThreadPoolExecutor`, `asyncio` |
| CPU-bound pure Python | ❌ ~1 core total, plus contention overhead | `ProcessPoolExecutor`, native code, free-threaded build |
| CPU-bound in GIL-releasing C (NumPy, hashlib, zlib) | ✅ Parallel inside C sections | Threads are fine |
| Mixed CPU + I/O in one process | ⚠️ "Convoy effect": CPU thread delays I/O thread wakeups | Separate processes, or move CPU work out |

**The escape hatches in 3.12+:**

- **Per-interpreter GIL** (PEP 684, 3.12) and `concurrent.interpreters` / `InterpreterPoolExecutor` (PEP 734, 3.14): isolated interpreters in one process, each with its own GIL.
- **Free-threaded CPython** (PEP 703, PEP 779): `python3.14t`; `sys._is_gil_enabled()` reports status. Built-ins use per-object locks; extensions must declare support or the GIL is re-enabled at import.

> **Curriculum principle:** Every concurrent lab must pass on the GIL build **and be correct by construction on a free-threaded build.** Correctness may never depend on the GIL; the GIL is a performance characteristic, not a synchronization primitive.
