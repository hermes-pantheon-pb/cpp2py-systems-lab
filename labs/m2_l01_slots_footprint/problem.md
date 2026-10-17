# M2-L01 · Struct Layout: 100k Records Under Budget

## Problem

In financial market data systems, order-book feed handlers process millions of market ticks per second.
You are tasked with porting an ultra-compact tick record from C++ to Python:

```cpp
struct Tick {
    uint32_t ts;   // Unix timestamp (seconds)
    double   px;   // Price
    uint32_t qty;  // Volume
};
```

### Required API

| Member | Semantics |
|:---|:---|
| `Tick(ts: int, px: float, qty: int)` | Construct an immutable tick record |
| `ts`, `px`, `qty` | Read-only attributes |
| `__eq__`, `__hash__` | Value-based equality and hashability (usable as dict key or in sets) |
| `export_columnar(ticks: list[Tick])` | Returns `(ts_arr, px_arr, qty_arr)` as contiguous `array.array` (`'I'`, `'d'`, `'I'`) |

## The C++ Mental Model

In [reference.cpp](./reference.cpp), `sizeof(Tick) == 24` bytes (with alignment padding).
In a `std::vector<Tick>`, 100,000 records occupy **2.4 MB of contiguous memory**. The CPU prefetcher
streams the array with minimal cache misses, and zero pointer indirection is required.

## The Naive Translation

In [naive.py](./naive.py), a standard Python class without `__slots__` stores attributes dynamically.
Even with Python 3.11+ inline values, a standard class retains an internal dictionary-like structure,
boxes floats and integers into separate heap allocations, and permits arbitrary attribute assignments.
For 100,000 records, the memory consumption spikes above **10.4 MB** (~104 bytes per instance),
and instances remain mutable and non-hashable.

## Your Task

Refactor [solution.py](./solution.py) so that:

1. The class layout eliminates `__dict__` entirely by leveraging `__slots__` (e.g. via `@dataclass(frozen=True, slots=True)` or explicit `__slots__`).
2. Instances are strictly immutable.
3. 100,000 records consume $\le 70.0$ bytes per instance under `tracemalloc`.
4. Provide `export_columnar(ticks)` which dumps records into zero-copy, contiguous typed buffers (`array.array('I')`, `array.array('d')`, `array.array('I')`).

## Verification

```bash
./lab.py test M2-L01                    # your solution
./lab.py test M2-L01 --target naive     # observe naive failing C2–C5
./lab.py verify M2-L01                  # meta-verify criteria sensitivity
```
