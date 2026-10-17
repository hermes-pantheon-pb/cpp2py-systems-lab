# M5-L01 · Single-Flight Cache: check-then-act & Thundering Herd

## Problem

In microservices and high-throughput systems, caching is essential to shield databases and upstream
services. However, when a popular cache key expires or a cold service starts, dozens of concurrent
requests for the same key arrive simultaneously. This is the **thundering herd** or **cache stampede**.

Your task is to build a thread-safe `SingleFlightCache[K, V]` that guarantees:
1. For any given key, **at most one** execution of `loader(key)` is in-flight at any time.
2. Concurrent requests for that same key wait on the single in-flight operation and receive the result.
3. Requests for **different** keys proceed completely in parallel without blocking each other.
4. If the loader fails, all waiting threads for that key receive the exception, and the key is not permanently poisoned in the cache.

### Required API

| Member | Semantics |
|:---|:---|
| `SingleFlightCache(loader: Callable[[K], V])` | Initialize cache with an upstream loader function |
| `get(key: K) -> V` | Return cached value or load it via `loader` thread-safely |

## The C++ Mental Model

In [reference.cpp](./reference.cpp), C++ developers use a `std::mutex` protecting an in-flight
map of `std::shared_future<V>` (or condition variables).
The mutex is held only for brief map lookups/insertions; the actual slow I/O runs *outside* the mutex,
allowing multiple distinct keys to load concurrently on different threads.

## The Naive Translation

In [naive.py](./naive.py), a C++ programmer new to Python might think:
*"The GIL serializes bytecodes, and dict lookups are atomic in CPython, so I don't need locks."*

```python
if key not in self.cache:       # Check
    self.cache[key] = loader()  # Act (loader does I/O, releasing the GIL!)
```

This is the canonical **check-then-act** race condition. When 32 threads request `key="profile:42"`
simultaneously, all 32 threads observe `key not in self.cache`, and all 32 threads invoke the
expensive loader!

If the developer attempts a naive fix by wrapping `get()` in a single coarse `threading.Lock`:
```python
with self.lock:
    if key not in self.cache:
        self.cache[key] = loader()
```
They create a severe concurrency bottleneck: `loader()` holds the lock during network I/O,
serializing **all** keys across the entire application and violating C3!

## Your Task

Refactor [solution.py](./solution.py) to implement a true single-flight pattern:
- Use a lock to protect internal tracking data structures.
- Elect the first arriving thread as the *leader* to run `loader(key)`.
- Enqueue subsequent concurrent arrivals as *followers* awaiting a `concurrent.futures.Future`.
- Crucial: Ensure `loader(key)` executes **outside** the lock so distinct keys load concurrently.

## Verification

```bash
./lab.py test M5-L01                    # your solution
./lab.py test M5-L01 --target naive     # see naive fail C2–C4
./lab.py verify M5-L01                  # meta-verify criteria sensitivity
```
