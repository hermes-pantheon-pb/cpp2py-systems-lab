# Module 1 — The CPython Runtime & Memory Model

**Learning outcomes.** By the end, the learner can:

1. Draw the object graph (names → `PyObject*` → objects) for any snippet, distinguishing rebind / mutate / copy.
2. Predict when an object is deallocated under refcounting and when only the cyclic GC can free it.
3. Measure reference-count deltas and allocation footprints with `sys`, `gc`, `weakref`, `tracemalloc`.
4. Translate C++ ownership graphs (`unique_ptr`/`shared_ptr`/`weak_ptr`/raw back-pointer) into leak-free Python.

---

## (a) Core Mental Model

```text
C++                                        CPython
───────────────────────────────            ──────────────────────────────────────────
int x = 5;      // x IS 4 bytes            x = 5        # x is a slot holding PyObject*
                                                       #   → immortal PyLongObject(5)
Widget w2 = w1; // copy ctor               w2 = w1      # Py_INCREF + pointer store
shared_ptr<W> p = make_shared<W>();        p = W()      # ob_refcnt = 1 (from the name)
weak_ptr<W>   q = p;                       q = weakref.ref(p)
~W() at '}'                                tp_dealloc when ob_refcnt → 0 (or at GC time
                                           if part of an unreachable cycle)
```

**One-liner:** *Every Python name is a `shared_ptr` with an intrusive, non-atomic count; there are no values, only references; and a cycle of `shared_ptr`s is reclaimed by a tracing collector, not by scope.*

## (b) Systems Deep-Dive

### 1. Object header and identity
- `PyObject { ob_refcnt; ob_type; }` (16 B) and `PyVarObject` (+`ob_size`). See [Translation Matrix §2.1](../01_translation_matrix.md#21-the-pyobject-header).
- `id(x)` = address; `is` = address equality; `type(x)` = `ob_type`.
- Immortal objects (PEP 683, 3.12): `None`, `True`, `False`, small ints (−5…256), interned/static strings. Their refcount is saturated and never reaches zero.

### 2. Frames and namespaces
- Function locals live in a fast-locals array inside `_PyInterpreterFrame` (allocated on a per-thread data stack since 3.11; a full `frame` object is only materialized for introspection/tracebacks).
- Module globals and class bodies use real dicts. `locals()` in a function is a snapshot (PEP 667 semantics in 3.13).
- `dis.dis()` to show `LOAD_FAST`/`STORE_FAST`/`LOAD_GLOBAL`/`STORE_ATTR` — the learner reads bytecode as they would read `-S` assembly.

### 3. Allocation
- **pymalloc** for small objects (≤512 B): arenas → pools → fixed-size blocks in 16-byte size classes; never returns memory to the OS until a whole arena is free (fragmentation explains "RSS doesn't go down").
- Free lists for hot types (floats, tuples, frames) recycle memory without hitting the allocator.
- Free-threaded build uses **mimalloc**.
- Diagnostic modes: `PYTHONMALLOC=debug`, `python -X dev`, `python -X tracemalloc=25`.

### 4. Reference counting
- `Py_INCREF`/`Py_DECREF` semantics; *new* vs *borrowed* references (vocabulary from the C API — read `Include/object.h`, `Include/refcount.h`).
- `sys.getrefcount(x)` reports one extra temporary reference for the argument; 3.14 may report *fewer* than expected because the interpreter avoids some increments for stack operands. **Always measure deltas, never absolute counts.**

### 5. The cyclic garbage collector
- Only *container* objects (lists, dicts, instances, closures…) are GC-tracked (`gc.is_tracked`). Atomic objects (ints, strs) aren't.
- Algorithm: for each tracked object, copy refcount → `gc_refs`; subtract references coming from other tracked objects (`tp_traverse`); anything with `gc_refs > 0` is externally reachable; propagate reachability; remainder is garbage. Then: handle weakrefs, call finalizers (PEP 442), `tp_clear` to break cycles.
- Generations and thresholds (`gc.get_threshold()`, `gc.get_count()`); 3.14 moves to an incremental young/old collector.
- Production knobs: `gc.freeze()` before `fork()` (copy-on-write friendliness), `gc.disable()` in latency-critical sections *only* if the code is cycle-free, `gc.callbacks` for pause telemetry.
- Source to read: `Python/gc.c` (3.13+, previously `Modules/gcmodule.c`), `Objects/object.c`.

### 6. Translating ownership graphs

| C++ ownership | Python translation |
|:---|:---|
| `unique_ptr<Child>` children, raw `Parent*` back-pointer | `self.children: list[Node]` + `self._parent: weakref.ref[Node]` |
| `shared_ptr` graph with `weak_ptr` cycle-breakers | Strong refs + `weakref.ref` / `WeakSet` / `WeakValueDictionary` |
| Observer list holding raw pointers | `weakref.WeakSet` or `weakref.WeakMethod` for bound-method callbacks |
| Intrusive cache keyed by object | `weakref.WeakKeyDictionary` |
| Arena / object pool | Usually unnecessary; free lists exist. Use `__slots__` + reuse only after profiling |

## (c) Key Idioms & Gotchas

| Idiom ✅ | Anti-pattern ❌ | FE |
|:---|:---|:---|
| `copy.deepcopy(cfg)` or immutable value objects | `cfg2 = cfg` then mutate | FE-1 |
| `def f(xs: list[int] \| None = None)` | `def f(xs=[])` | FE-2 |
| `x is None` | `x is 1000`, `s is "literal"` | FE-6 |
| Weak back-references for parent/observer links | Strong parent pointers creating cycles | — |
| Measure refcount *deltas* on non-immortal objects | Assert `sys.getrefcount(x) == 2` | — |
| `tracemalloc` snapshots diffed around an operation | Reading RSS from `ps` to judge leaks | — |
| `weakref.WeakMethod` for bound-method callbacks | `weakref.ref(obj.method)` (dies immediately: bound methods are temporaries) | — |

## (d) Interactive Lab Specification

| ID | Title | C++ anchor | Naive Python (anti-pattern) | Refactor criteria | Harness probes |
|:---|:---|:---|:---|:---|:---|
| **M1-L01** ✅ | Ownership Cycles: Tree with Parent Links | `unique_ptr` children + raw `Parent*` | Strong `self.parent = parent` | C1 API behaves; C2 dropping root frees *all* nodes with GC disabled; C3 `add_child` adds 0 refs to parent; C4 net retained memory ≈ 0; C5 dead parent reads as `None` | `gc_disabled`, `weakref` liveness, `refcount_delta`, `measure_alloc` |
| M1-L02 | Aliasing Forensics | Copy ctor of nested `std::vector<std::vector<int>>` | `[[0]*n]*n`, `dict(cfg)` | Rows/nested dicts are disjoint objects; caller state unchanged after call | `id()` disjointness, snapshot equality |
| M1-L03 | Default-Argument State Leak | Default-constructed parameter | `def add(x, bucket=[])` | Independent results across calls/threads; no mutable `__defaults__` | `__defaults__` inspection, repeated-call identity |
| M1-L04 | Observer Registry Without Leaks | `std::vector<Observer*>` + manual unsubscribe | Strong list of bound methods | Subscribers collectable while registered; dead callbacks pruned | `WeakMethod`, `gc_disabled`, `refcount_delta` |
| M1-L05 | Reading the Machine | `objdump -d` on a hot loop | — (exploration) | Explain `dis` output for rebind vs mutate; predict specialized opcodes after warm-up (`dis.dis(f, adaptive=True)`) | Golden-output assertions on `dis.get_instructions` |

### Exit criteria
- All M1 labs green; learner can whiteboard the GC's "subtract internal references" pass.
- Translation note: *"Why `open(p).read()` closes the file in CPython but is still a bug."*
