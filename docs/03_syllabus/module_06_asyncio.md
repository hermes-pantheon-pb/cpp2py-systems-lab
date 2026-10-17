# Module 6 — Asynchronous I/O & Event-Driven Architecture

**Learning outcomes.**

1. Explain readiness-based I/O (`epoll`) and build a minimal callback event loop with `selectors`.
2. Describe how a coroutine is suspended and resumed by `asyncio.Task`, down to `send()` and `Future.__await__`.
3. Write structured-concurrency code with `TaskGroup`, `asyncio.timeout`, bounded queues, and semaphores.
4. Handle cancellation correctly and bridge blocking code with `asyncio.to_thread`.
5. Decide between threads, asyncio, and processes for a given service.

---

## (a) Core Mental Model

```text
Threads (M5)                               asyncio
───────────────────────────────            ─────────────────────────────────────────────
N OS threads, preemptive                   1 OS thread, cooperative
Switch: anywhere (GIL checkpoints)         Switch: ONLY at `await` (explicit yield points)
Stack per thread (~8 MB virtual)           Stackless coroutine frame per task (~KBs)
Shared state needs locks                   State between awaits is implicitly atomic
Blocking call blocks one thread            Blocking call blocks EVERYTHING

C++ analogue: Boost.Asio io_context / C++20 stackless coroutines (co_await) / libuv
```

**One-liner:** *An event loop is a `while True:` around `epoll_wait()` that resumes whichever coroutine's I/O became ready; `await` is the only place your code can be interrupted — which is both the superpower and the trap.*

## (b) Systems Deep-Dive

### 1. Readiness I/O from the OS up
- Blocking vs non-blocking sockets (`O_NONBLOCK`, `EAGAIN`/`BlockingIOError`).
- `select`/`poll` (O(n) per call) → `epoll` (Linux, O(ready)) / `kqueue` (BSD/macOS) / IOCP (Windows, completion-based → `ProactorEventLoop`).
- Level- vs edge-triggered; `selectors.DefaultSelector` → `EpollSelector` on Linux (level-triggered).
- **Lab M6-L01** builds a ~100-line echo server on raw `selectors` with callbacks, then refactors to generators, deriving `asyncio`'s design.

### 2. Inside the asyncio loop (`Lib/asyncio/base_events.py: _run_once`)
1. Compute timeout = time until the earliest scheduled `TimerHandle` (heap), or 0 if `_ready` is non-empty.
2. `events = selector.select(timeout)` → register ready callbacks into `_ready` deque.
3. Move expired timers from the heap into `_ready`.
4. Run every callback currently in `_ready` (one "tick").

### 3. Coroutines and Tasks
- `async def` produces a **coroutine object** (a stackless state machine, like a C++20 coroutine frame). Calling it does nothing until driven.
- `await fut` → `Future.__await__` *yields the future itself* up the chain to the `Task`.
- `Task.__step()` calls `coro.send(None)`; on receiving a pending future it adds `__wakeup` as a done-callback; when the future resolves, the loop schedules `__step` again.
- Eager task factory (3.12, `asyncio.eager_task_factory`) runs a task synchronously until its first real suspension.
- `asyncio.create_task` returns a task the loop references **weakly** → keep a strong reference (or use `TaskGroup`).

### 4. Structured concurrency
- `asyncio.TaskGroup` (3.11): children cannot outlive the block; first failure cancels siblings; errors surface as an `ExceptionGroup` (`except*`).
- `asyncio.timeout(s)` / `timeout_at` (3.11) replace `wait_for` in most code.
- Cancellation = `CancelledError` thrown *into* the coroutine at its current `await`. It is a `BaseException`: **never swallow it**; clean up in `finally`, then re-raise. `Task.uncancel()` exists for frameworks.
- `asyncio.shield` for must-complete operations (rarely correct; document why).

### 5. Flow control & backpressure
- Unbounded `create_task` per request = unbounded memory. Use `asyncio.Semaphore(N)` or a fixed worker pool over `asyncio.Queue(maxsize=N)` (`Queue.shutdown()` in 3.13+).
- Streams: `writer.write()` buffers; `await writer.drain()` applies backpressure.

### 6. Bridging worlds
- Blocking or CPU-bound calls: `await asyncio.to_thread(fn, *args)` / `loop.run_in_executor(pool, fn)`.
- From threads into the loop: `asyncio.run_coroutine_threadsafe(coro, loop)`, `loop.call_soon_threadsafe(cb)`. All other loop APIs are **not** thread-safe.
- `contextvars` propagate per task (request ids, deadlines) — `threading.local` does not.

### 7. Debugging & operability
- `asyncio.run(main(), debug=True)` / `PYTHONASYNCIODEBUG=1`: logs callbacks slower than `loop.slow_callback_duration` (100 ms) and never-awaited coroutines.
- 3.14: `python -m asyncio ps <pid>` / `pstree` for live task introspection.
- `uvloop` as a drop-in faster loop (libuv); `asyncio.Runner` for embedding.

### 8. Choosing a model

| Workload | Choice |
|:---|:---|
| Many concurrent, mostly-idle connections (10k sockets, streaming RPCs) | asyncio |
| Moderate concurrency, blocking libraries (DB drivers without async support) | Threads |
| CPU-bound | Processes / native code / free-threaded build |
| Mixed | asyncio front + `to_thread` / process pool back |

## (c) Key Idioms & Gotchas

| Idiom ✅ | Anti-pattern ❌ |
|:---|:---|
| `async with asyncio.TaskGroup() as tg: tg.create_task(...)` | Fire-and-forget `asyncio.create_task(...)` without a reference |
| `async with asyncio.timeout(2):` | No timeouts on network awaits |
| `await asyncio.sleep(x)` / `await asyncio.to_thread(blocking)` | `time.sleep(x)`, `requests.get(...)` inside `async def` |
| `try: … finally: cleanup()` then let `CancelledError` propagate | `except Exception:` *plus* `except asyncio.CancelledError: pass` |
| `Semaphore`/bounded `Queue` for fan-out | `gather(*[fetch(u) for u in million_urls])` |
| `asyncio.Lock` when an invariant spans an `await` | Assuming "single-threaded ⇒ no races" across `await`s |
| `contextvars.ContextVar` for request-scoped data | `threading.local` in async code |

## (d) Interactive Lab Specification

| ID | Title | C++ anchor | Naive Python | Refactor criteria | Probes |
|:---|:---|:---|:---|:---|:---|
| M6-L01 | Build an Event Loop | Raw `epoll_wait` loop in C | Thread-per-connection echo server | `selectors`-based server handles 500 concurrent clients on 1 thread; timer heap support | Thread census = 1, client stress |
| M6-L02 | Sync → Async Port with Structured Concurrency | `std::async` fan-out + `wait_for` | `gather` without timeouts; leaked tasks on error | `TaskGroup` + `timeout`; on one failure, siblings cancelled and cleaned up | Task census (`asyncio.all_tasks()`), cleanup log |
| M6-L03 | Bounded Fan-Out with Backpressure | Bounded MPMC queue + worker pool | One task per item, unbounded memory | Peak concurrency ≤ N; memory bounded; throughput floor | Concurrency high-water mark, `tracemalloc` |
| M6-L04 | Hunting Loop Blockers | Blocking `recv` on the I/O thread | `time.sleep`/`hashlib` on large data in handlers | Loop lag p99 < 10 ms under load; blocking work moved to `to_thread` | Loop-lag sampler task, debug-mode log capture |
| M6-L05 | Cancellation Correctness | `stop_token` cooperative cancellation | Swallowed `CancelledError`, missing `finally` | Timeout cancels within ε; resources released; cancellation propagates | Resource ledger, timing bounds |
| M6-L06 | Races Across `await` | Unlocked check-then-act | `if k not in cache: cache[k] = await load(k)` | Single-flight with `asyncio.Future` per key (async twin of M5-L01) | Load-count assertions |

### Exit criteria
- Can explain, with a diagram, what happens between `await reader.read()` and the bytes arriving.
- Translation note: *"Why `asyncio` doesn't need locks for `x += 1` but does need them across an `await`."*
