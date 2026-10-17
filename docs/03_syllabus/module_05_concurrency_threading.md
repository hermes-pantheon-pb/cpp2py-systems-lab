# Module 5 — Concurrency Fundamentals & The Python Threading Model

> **Context.** The learner has never written multi-threaded C/C++. This module therefore teaches
> concurrency **from first principles**, using the learner's systems knowledge (address spaces,
> stacks, registers, the scheduler) as the foundation, and only then specializes to CPython.

**Learning outcomes.**

1. Define thread, process, scheduling, preemption, critical section, race condition, data race, atomicity, deadlock, and liveness — and recognize each in code.
2. Prove (by reproduction under a stress harness) that a given piece of code is racy, then fix it.
3. Use `Lock`, `RLock`, `Condition`, `Semaphore`, `Event`, `Barrier`, `queue.Queue`, and `concurrent.futures` idiomatically.
4. Explain what the GIL protects, how it is handed off, and predict whether threads will speed up a given workload.
5. Write thread-safe code that remains correct on the free-threaded build (`python3.14t`).

---

## (a) Core Mental Model

```text
Process (one address space: heap, globals, code, open fds)
├── Thread A: own stack + registers + instruction pointer ─┐
├── Thread B: own stack + registers + instruction pointer ─┼── all share the SAME heap objects
└── Thread C: own stack + registers + instruction pointer ─┘

The OS scheduler may pause any thread between ANY two machine instructions.
The CPython GIL additionally ensures only one thread runs BYTECODE at a time,
but may switch threads between ANY two bytecodes at its checkpoints.
```

**One-liner:** *Concurrency bugs come from **shared mutable state + interleaving**. A lock does not protect data; it protects an **invariant** across a sequence of operations. The GIL protects the interpreter's invariants, never yours.*

## (b) Systems Deep-Dive

### Part 1 — First principles (language-agnostic, ~4 h)

#### 1.1 Threads vs processes
| | Process | Thread |
|:---|:---|:---|
| Address space | Private (copy-on-write after `fork`) | Shared with siblings |
| Creation cost | High (page tables, fds) | Lower (stack + kernel task) |
| Communication | IPC: pipes, sockets, shared memory | Direct memory access — *the source of both speed and bugs* |
| Failure isolation | Crash is contained | A crash kills the whole process |
| Linux reality | `clone()` with different sharing flags — both are kernel tasks | — |

#### 1.2 Interleaving and the race condition
- A **race condition** = correctness depends on the relative timing of threads.
- A **data race** (C++ term) = unsynchronized concurrent access with ≥1 write → UB in C++. Python has no UB here, but logical races remain.
- **Read-modify-write** (`x += 1`) and **check-then-act** (`if k not in d: d[k] = v`) are the two canonical shapes. Walk through interleaving tables by hand:

```text
balance = 100                 T1: withdraw 70           T2: withdraw 70
t0  T1 reads balance → 100
t1                            T2 reads balance → 100
t2  T1 checks 100 ≥ 70 ✓ writes 30
t3                            T2 checks 100 ≥ 70 ✓ writes 30     ⇒ 140 withdrawn, balance 30
```

#### 1.3 Critical sections and mutual exclusion
- A **mutex** makes a sequence of operations appear atomic to other threads that also use the mutex. Locks are *cooperative*: unlocked access elsewhere voids the guarantee.
- Granularity trade-off: coarse (simple, serializes) vs fine (parallel, deadlock-prone). Lock striping / per-key locks.
- **Memory visibility:** synchronization points (lock acquire/release, thread start/join, queue put/get, `Event.set`/`wait`) establish *happens-before* edges. CPython doesn't publish a formal memory model; **treat those primitives as the only sanctioned way to publish state between threads** — this keeps code correct on the free-threaded build.

#### 1.4 Coordination: waiting for a condition
- Busy-waiting (`while not ready: pass`) burns CPU and, under the GIL, steals time from the thread you're waiting for.
- **Condition variable** = lock + wait queue. `wait()` atomically releases the lock and sleeps; on wake it re-acquires. Always wait **in a loop on a predicate** (spurious and stolen wakeups): `cond.wait_for(lambda: len(buf) > 0)`.
- Semaphores (counting permits), Events (one-shot latch), Barriers (rendezvous).

#### 1.5 Liveness failures
- **Deadlock** — Coffman conditions: mutual exclusion, hold-and-wait, no preemption, circular wait. Break circular wait with a **global lock order** (e.g. by account id) or `acquire(timeout=…)`.
- **Livelock**, **starvation**, **priority inversion**; **lock convoys**.
- Diagnosing a hung process: `faulthandler.dump_traceback_later(timeout)`, `py-spy dump --pid`, `sys._current_frames()`.

#### 1.6 Designing to avoid shared state
Ranked by preference:
1. **Confinement** — state owned by exactly one thread; others communicate via `queue.Queue` (actor / CSP style).
2. **Immutability** — share frozen data freely (`tuple`, `frozenset`, frozen dataclasses).
3. **Synchronization** — locks around invariants, as small and as few as possible.

Amdahl's law: speedup ≤ 1 / ((1 − p) + p/N) — the serial fraction (including lock-held time) caps scaling.

### Part 2 — Python's threading toolkit (~4 h)

| Need | Primitive | Notes |
|:---|:---|:---|
| Run work concurrently | `concurrent.futures.ThreadPoolExecutor` | Prefer over raw `Thread`; `with` ensures `shutdown(wait=True)`; `cancel_futures=True` (3.9+) |
| Mutual exclusion | `threading.Lock` | Always `with lock:`; non-reentrant |
| Re-entrant locking | `threading.RLock` | Usually signals tangled call graphs |
| Wait for predicate | `threading.Condition` | `wait_for(pred, timeout)`; `notify` vs `notify_all` |
| Bounded resource | `threading.BoundedSemaphore` | Connection pools, rate limiting |
| One-shot signal / shutdown flag | `threading.Event` | Cooperative cancellation: workers poll `stop.is_set()` / `stop.wait(t)` |
| Rendezvous | `threading.Barrier` | Also the harness's stampede tool |
| Thread-safe handoff | `queue.Queue(maxsize=N)` | Backpressure via `maxsize`; `Queue.shutdown()` (3.13+) for clean termination |
| Per-thread state | `threading.local` | Use `contextvars` if code may also run in asyncio |
| Uncaught exceptions in threads | `threading.excepthook`; `Future.result()` re-raises | Raw `Thread` exceptions are only printed |

- **Threads cannot be killed.** Design cancellation cooperatively (Events, sentinels, `Queue.shutdown`). Daemon threads are abandoned at exit mid-operation — never use them for work that must complete (flushes, commits).
- Futures: `as_completed`, `wait(FIRST_EXCEPTION)`, exception propagation, timeouts.

### Part 3 — The GIL dissected (~3 h)

#### 3.1 Why it exists
Non-atomic `ob_refcnt` updates, pymalloc, and unsynchronized internal structures in every container. One global lock made the interpreter and C extensions memory-safe with near-zero single-thread overhead. (See [Translation Matrix §2.5](../01_translation_matrix.md#25-the-gil-memory-safety-vs-multi-core-scaling).)

#### 3.2 Hand-off mechanics (`Python/ceval_gil.c`)
- Waiting thread times out after `sys.getswitchinterval()` (5 ms) → sets `gil_drop_request` in the holder's eval breaker.
- Holder checks the breaker at function entries and backward jumps (not every bytecode since 3.10) → drops the GIL → forced switch ensures the waiter actually gets it (avoids the old "re-acquire immediately" unfairness).
- Blocking syscalls and GIL-releasing C code (`Py_BEGIN_ALLOW_THREADS`) hand off immediately.
- **Lab consequence:** naive races like `counter += 1` in a tight loop are *rarely* observed on 3.10+, which gives false confidence. The harness amplifies interleavings with `sys.setswitchinterval(1e-6)` and stampedes behind a `Barrier`, and the labs use realistic I/O-yielding critical sections.

#### 3.3 Atomicity you can (and can't) rely on
| Operation | Under GIL | Rely on it? |
|:---|:---|:---|
| `lst.append(x)`, `d[k] = v`, `d.get(k)`, `q.put(x)` | Atomic (single C call) | Yes for container integrity (also internally locked on free-threaded builds) |
| `x += 1`, `d[k] += 1`, `d[k] = d.get(k, 0) + 1` | **Not atomic** | Never |
| `if k not in d: d[k] = make()` | **Not atomic** | Never |
| Iterating a dict/list another thread mutates | `RuntimeError` or skipped items | Never — copy under a lock or confine |
| `next(itertools.count())` | Atomic in practice | Acceptable for id generation; document it |

#### 3.4 When threads give real speedups
- **I/O-bound** (RPC fan-out, DB queries, file I/O): near-linear until the server, network, or pool saturates.
- **CPU-bound pure Python:** ~1×; use `ProcessPoolExecutor` (pickling cost, `fork` vs `spawn`/`forkserver` — `forkserver` is the Linux default from 3.14), `InterpreterPoolExecutor` (3.14), or native code.
- **Free-threaded build:** CPU-bound threads scale, at a single-thread cost of a few percent to ~10–20% depending on the version; C extensions must opt in (`Py_mod_gil`) or the GIL is re-enabled at import (`PYTHON_GIL=0` forces it off). Verify with `sys._is_gil_enabled()`.

## (c) Key Idioms & Gotchas

| Idiom ✅ | Anti-pattern ❌ | FE |
|:---|:---|:---|
| `with lock:` around the *entire* invariant | Lock around each individual read/write | FE-5 |
| `queue.Queue(maxsize=N)` between producer/consumer | Shared list + `time.sleep` polling | — |
| `cond.wait_for(predicate)` | `if not ready: cond.wait()` | — |
| Global lock ordering (`sorted((a, b), key=id)`) | Acquire in argument order | — |
| Per-key `Future`/lock for single-flight | Global lock held during slow I/O (serializes everything) | FE-5 |
| `executor.submit(fn, arg)` | `executor.submit(lambda: fn(arg))` in a loop | FE-9 |
| `ProcessPoolExecutor` for CPU-bound | `ThreadPoolExecutor` for CPU-bound | FE-4 |
| `Event`-based cooperative stop + `join()` | `daemon=True` to "make exit work" | — |
| Snapshot under lock, then iterate outside | Iterate a shared dict while others write | FE-5 |

## (d) Interactive Lab Specification

| ID | Title | C++ anchor | Naive Python | Refactor criteria | Probes |
|:---|:---|:---|:---|:---|:---|
| **M5-L01** ✅ | Single-Flight Cache (check-then-act) | `std::mutex` + `std::shared_future` per key | `if key not in cache: cache[key] = loader(key)` | C1 correctness; C2 exactly one load per key under a 32-thread stampede; C3 distinct keys load in parallel (no global lock during I/O); C4 failures propagate to all waiters and are not cached | `run_concurrently` + `Barrier`, `aggressive_switching`, wall-clock bounds |
| M5-L02 | Ledger: Lost Updates & Deadlock-Free Transfers | `std::scoped_lock(a.m, b.m)` | Unlocked `balance -= amt` with audit I/O in between; locks taken in argument order | Conservation of money under 10k concurrent transfers; no deadlock within timeout under opposing transfers | Invariant check, `faulthandler` watchdog, join timeouts |
| M5-L03 | Bounded Buffer from First Principles | `std::condition_variable` producer/consumer | `while len(buf) >= cap: time.sleep(0.001)` | Implement with `Lock`+2×`Condition`; no busy-wait (CPU time ≪ wall time); FIFO; clean shutdown; then show equivalence with `queue.Queue` | `time.thread_time()` vs wall, ordering checks |
| M5-L04 | GIL Scaling Laboratory | N `std::thread`s on N cores | `ThreadPoolExecutor` for CPU-bound hashing in Python | Measure speedup curves for threads/processes on CPU vs I/O workloads; choose executor per workload to hit target speedups; skip/adjust on free-threaded builds | `measure_speedup`, `is_free_threaded()` |
| M5-L05 | Worker Pool with Graceful Shutdown | `std::jthread` + `std::stop_token` | Daemon threads, no join, swallowed exceptions | In-flight tasks complete on shutdown; new submissions rejected; worker exceptions surfaced; no thread leaks (`threading.active_count()` restored) | Thread census, exception capture |

### Exit criteria
- Learner can produce an interleaving table proving a race for any naive lab.
- All M5 labs green under `--repeat` stress (5 runs) and, if available, on `python3.14t`.
- Translation note: *"What the GIL guarantees, what it doesn't, and why my code must not care."*
