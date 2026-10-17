# Module 2 — Memory Layout & Core Containers

**Learning outcomes.**

1. Compute the approximate footprint of `list`, `tuple`, `dict`, `set`, class instances, and slotted instances.
2. Explain list over-allocation, dict compact layout and probing, and the cost of each operation in C terms.
3. Choose between `list`, `tuple`, `array.array`, `bytes`/`bytearray`/`memoryview`, `deque`, and NumPy based on layout.
4. Reduce per-instance memory with `__slots__` and verify it with `tracemalloc`.
5. Port bit-twiddling C code correctly given arbitrary-precision `int` and floor division.

---

## (a) Core Mental Model

```text
std::vector<double> v(1'000'000);        list[float] (1M)
┌────────────────────────────┐           ┌────────────────────────────┐
│ 8 MB of doubles, contiguous│           │ 8 MB of PyObject* (pointers)│
└────────────────────────────┘           └──┬──────┬──────┬───────────┘
                                            ▼      ▼      ▼
                                          float  float  float   (24 B each, heap)

struct Point { double x, y; };           class Point:              # per-instance dict-ish
  16 B, inline                              def __init__(s,x,y): s.x=x; s.y=y
                                         @dataclass(slots=True)    # fixed offsets, no __dict__
```

**One-liner:** *Python containers store pointers to boxed objects; "contiguous" only exists in buffer-protocol types (`bytes`, `bytearray`, `array`, `memoryview`, NumPy).*

## (b) Systems Deep-Dive

### 1. `list` = `std::vector<PyObject*>`
- `PyListObject { PyObject_VAR_HEAD; PyObject **ob_item; Py_ssize_t allocated; }`.
- Growth policy (`Objects/listobject.c`, `list_resize`): `new_allocated = (newsize + (newsize >> 3) + 6) & ~3` — ~12.5% over-allocation, amortized O(1) `append`, vs `std::vector`'s typical 1.5×/2×.
- `insert(0, x)`/`pop(0)` are O(n) `memmove`s → use `collections.deque`.
- Sorting: Timsort (Powersort merge policy since 3.11) — stable, exploits runs; `key=` is computed once per element (decorate-sort-undecorate in C).

### 2. `tuple` = inline pointer array
- `PyTupleObject` stores items inline after the header (one allocation). Immutable, hashable if elements are. Free lists for small sizes. Tuples of atomic objects get untracked by the GC.

### 3. `dict` = compact ordered hash table
- `PyDictKeysObject`: a **sparse index array** (`int8/16/32/64` entries depending on capacity) + a **dense entries array** of `(hash, key, value)` in insertion order. Unicode-only-key tables drop the stored hash per entry (3.11+).
- Open addressing; probe sequence `i = (5*i + 1 + perturb) & mask; perturb >>= 5` so all hash bits eventually participate.
- Usable load ≤ 2/3 before resize. Deletions leave `DKIX_DUMMY` tombstones.
- `str`/`bytes` hashes are randomized per process (SipHash-1-3, `PYTHONHASHSEED`) to defeat collision DoS; `hash(int)` is (mostly) identity mod 2⁶¹−1 → adversarial int keys *can* collide.
- **Key-sharing / inline values** (PEP 412, 3.11+): instances of the same class share one keys table; values live inline in the object until something forces a real `__dict__`.
- Hash/eq contract: `a == b ⇒ hash(a) == hash(b)`. Defining `__eq__` without `__hash__` makes instances unhashable. Mutating a key's hashed state after insertion = lost entry.

### 4. `set`
- Open addressing with short linear-probe runs (`LINEAR_PROBES = 9`) before perturbation; stores `(key, hash)` only. Iteration order is arbitrary.

### 5. Contiguous types and the buffer protocol
- `bytes` (immutable), `bytearray` (mutable, over-allocates), `array.array(typecode)`, `memoryview` (zero-copy slicing, `.cast()`), `mmap`.
- The buffer protocol (PEP 3118) is Python's `std::span`: a C struct with pointer, shape, strides, format — consumed by `struct`, `socket.recv_into`, NumPy, `hashlib`, `zlib`, Protobuf.
- `struct.Struct('<IHd')` precompiled formats; `iter_unpack` for record streams; `socket.recv_into(memoryview(buf)[off:])` for zero-copy reads.

### 6. `__slots__`
- Replaces per-instance `__dict__` with **member descriptors** at fixed offsets — the closest thing to a C struct layout.
- Must be declared in *every* class in the hierarchy, or a parent re-introduces `__dict__`. Add `"__weakref__"` explicitly if weak references are needed.
- `@dataclass(slots=True)` (3.10+) generates it. Combine with `frozen=True` for hashable value objects.

### 7. Integer and float semantics
- `PyLongObject`: sign + array of 30-bit digits; no overflow, no wrap; `int.bit_length()`, `int.to_bytes`, `int.from_bytes`.
- Floor division/modulo vs C truncation; `math.fmod` gives C semantics for floats.
- `float` = IEEE-754 binary64 (same as `double`); `math.isclose`, `math.fsum` for exact summation.

## (c) Key Idioms & Gotchas

| Idiom ✅ | Anti-pattern ❌ | FE |
|:---|:---|:---|
| `@dataclass(slots=True, frozen=True)` for many small records | Plain classes for 10⁶ instances | FE-8 |
| `array('d')` / NumPy for bulk numerics | `list[float]` with Python-level loops | FE-8 |
| `b"".join(chunks)` / `io.BytesIO` | `buf += chunk` in a loop | — |
| `memoryview(buf)[a:b]` | `buf[a:b]` on large `bytes` in a hot path (copies) | — |
| `collections.deque` for FIFO | `list.pop(0)` | — |
| `h = (h * P) & 0xFFFF_FFFF` | Trusting implicit wrap-around | FE-7 |
| `tracemalloc` for footprint | `sys.getsizeof(container)` (shallow) | — |
| `dict.get` / `setdefault` / `defaultdict` | `if k in d: d[k]` (double lookup, racy when shared) | FE-10 |

## (d) Interactive Lab Specification

| ID | Title | C++ anchor | Naive Python | Refactor criteria | Probes |
|:---|:---|:---|:---|:---|:---|
| **M2-L01** ✅ | Struct Layout: 100k Records Under Budget | `struct Tick { uint32_t ts; double px; uint32_t qty; }` in a `std::vector` | Plain class, attributes in `__dict__` | C1 API/equality/hashability; C2 no `__dict__`; C3 ≤ budget bytes/instance; C4 immutability enforced; C5 columnar `array` export is contiguous & typed | `measure_alloc`, `hasattr`, `memoryview.format` |
| M2-L02 | Zero-Copy Frame Parser | `std::span<const uint8_t>` over a recv buffer | Repeated `bytes` slicing + `int.from_bytes` per field | Allocation count per frame ≤ N; uses `memoryview`/`struct.Struct.unpack_from` | `tracemalloc` block counts, throughput floor |
| M2-L03 | Porting FNV-1a / xorshift from C | `uint32_t` wrap-around arithmetic | Unmasked `int` arithmetic, `//` for signed division | Bit-exact vs C golden vectors; Hypothesis property tests over random inputs | Hypothesis, golden fixtures |
| M2-L04 | Hash Contract & Collision Attack | `std::hash` specialization + `operator==` | `__eq__` without `__hash__`; mutable key fields | Correct hash/eq contract; dict survives adversarial int keys within a time budget (key wrapping/salting) | Timing ratio assertions |
| M2-L05 | Container Selection Drill | `vector` / `deque` / `priority_queue` / `unordered_map` | `list` for everything | Asymptotic budget tests: operations scale linearly at 10× input | Ratio-based complexity check |

### Exit criteria
- Can estimate (±25%) the footprint of a 1M-element structure before measuring it.
- Translation note: *"Why `sys.getsizeof([0.0]*10**6)` reports ~8 MB but the program uses far more when the floats are distinct."*
