"""Runtime probes for lab verification.

Every probe answers a *runtime property* question that a C/C++ developer would
normally answer with a debugger, valgrind, or TSan:

=====================  ===========================================  ==================
Probe                  Question                                      C/C++ analogue
=====================  ===========================================  ==================
gc_disabled            Is this freed by refcounting alone?           valgrind --leak-check
refcount_delta         Does this operation retain a strong ref?      shared_ptr::use_count
measure_alloc          How many bytes does this retain / peak at?    massif / heaptrack
aggressive_switching   Does this survive dense thread interleaving?  TSan / rr chaos mode
run_concurrently       Does this survive a synchronized stampede?    stress harness
measure_latency        What are p50/p95/p99 for this call?           google-benchmark
measure_speedup        Do N workers actually beat 1 worker?          perf / scaling plots
=====================  ===========================================  ==================
"""

from __future__ import annotations

import contextlib
import gc
import statistics
import sys
import sysconfig
import threading
import time
import tracemalloc
import traceback
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Executor
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AllocReport",
    "ConcurrentRun",
    "LatencyStats",
    "aggressive_switching",
    "gc_disabled",
    "is_free_threaded",
    "is_immortal",
    "measure_alloc",
    "measure_latency",
    "measure_speedup",
    "refcount_delta",
    "run_concurrently",
]


# --------------------------------------------------------------------------- #
# Interpreter introspection
# --------------------------------------------------------------------------- #
def is_free_threaded() -> bool:
    """True when running on a free-threaded build *with the GIL actually disabled*.

    A ``python3.13t``/``3.14t`` binary may still re-enable the GIL at runtime
    (e.g. when importing an extension that doesn't declare free-threading support).
    """
    if not sysconfig.get_config_var("Py_GIL_DISABLED"):
        return False
    gil_enabled = getattr(sys, "_is_gil_enabled", None)
    return gil_enabled is not None and not gil_enabled()


def is_immortal(obj: object) -> bool:
    """True for PEP 683 immortal objects (None, small ints, interned strings, ...)."""
    check = getattr(sys, "_is_immortal", None)  # 3.14+
    if check is not None:
        return bool(check(obj))
    return sys.getrefcount(obj) >= 2**30  # 3.12/3.13: saturated refcount heuristic


# --------------------------------------------------------------------------- #
# Memory / lifetime probes
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def gc_disabled() -> Iterator[None]:
    """Disable the cyclic GC so that only reference counting can free objects.

    On exit, the previous GC state is restored and a full collection is run so that
    cycles leaked by a *naive* implementation don't pollute subsequent tests.
    """
    was_enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()
        gc.collect()


def refcount_delta(obj: object, action: Callable[[], object]) -> int:
    """Return how many *persistent* strong references ``action()`` added to ``obj``.

    The return value of ``action`` is discarded before the second measurement, so
    only references stored somewhere (attributes, containers, closures) are counted.
    Absolute ``sys.getrefcount`` values are version-dependent (3.14 elides some
    stack increments); deltas are stable.
    """
    if is_immortal(obj):
        raise ValueError(f"cannot measure refcount deltas on immortal object {obj!r}")
    with gc_disabled():
        before = sys.getrefcount(obj)
        action()
        after = sys.getrefcount(obj)
    return after - before


@dataclass(frozen=True, slots=True)
class AllocReport:
    """Bytes as seen by tracemalloc (Python-level allocations, not RSS)."""

    net_bytes: int  # still allocated after fn() returned (result kept alive)
    peak_bytes: int  # high-water mark during fn(), relative to the baseline

    def per_item(self, n: int) -> float:
        return self.net_bytes / n


def measure_alloc[T](fn: Callable[[], T]) -> tuple[T, AllocReport]:
    """Run ``fn`` under tracemalloc and report retained and peak allocation.

    The result of ``fn`` is returned (and therefore still alive at measurement
    time), so ``net_bytes`` reflects what the result retains.
    """
    gc.collect()
    started_here = not tracemalloc.is_tracing()
    if started_here:
        tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        baseline, _ = tracemalloc.get_traced_memory()
        result = fn()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        if started_here:
            tracemalloc.stop()
    return result, AllocReport(net_bytes=current - baseline, peak_bytes=peak - baseline)


# --------------------------------------------------------------------------- #
# Concurrency probes
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def aggressive_switching(interval: float = 1e-6) -> Iterator[None]:
    """Shrink the GIL switch interval (default 5 ms) to force dense interleavings.

    This is the Python analogue of running under a chaos scheduler: races that
    would appear once a week in production appear within milliseconds.
    """
    previous = sys.getswitchinterval()
    sys.setswitchinterval(interval)
    try:
        yield
    finally:
        sys.setswitchinterval(previous)


@dataclass(slots=True)
class ConcurrentRun:
    results: list[Any]
    errors: list[BaseException] = field(default_factory=list)
    wall_s: float = 0.0


class DeadlockSuspected(TimeoutError):
    """Raised when worker threads fail to finish within the timeout."""


def _format_stacks(threads: Iterable[threading.Thread]) -> str:
    frames = sys._current_frames()
    chunks = []
    for t in threads:
        frame = frames.get(t.ident or -1)
        stack = "".join(traceback.format_stack(frame)) if frame else "  <no frame>\n"
        chunks.append(f"--- {t.name} ---\n{stack}")
    return "\n".join(chunks)


def run_concurrently(
    fn: Callable[[int], Any],
    n_threads: int,
    *,
    timeout: float = 10.0,
) -> ConcurrentRun:
    """Start ``n_threads`` threads that call ``fn(i)`` simultaneously.

    All threads block on a ``threading.Barrier`` and are released together to
    maximize contention (a *stampede*). Exceptions are collected, not lost. If
    threads are still alive after ``timeout`` seconds, ``DeadlockSuspected`` is
    raised with every stuck thread's stack.
    """
    barrier = threading.Barrier(n_threads)
    results: list[Any] = [None] * n_threads
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def worker(i: int) -> None:
        try:
            barrier.wait(timeout)
            results[i] = fn(i)
        except BaseException as exc:  # noqa: BLE001 — the harness must see everything
            with errors_lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(i,), name=f"lab-worker-{i}", daemon=True)
        for i in range(n_threads)
    ]
    start = time.perf_counter()
    for t in threads:
        t.start()
    deadline = start + timeout
    for t in threads:
        t.join(max(0.0, deadline - time.perf_counter()))
    wall = time.perf_counter() - start

    stuck = [t for t in threads if t.is_alive()]
    if stuck:
        raise DeadlockSuspected(
            f"{len(stuck)}/{n_threads} threads still running after {timeout}s "
            f"(deadlock or lost wakeup?)\n{_format_stacks(stuck)}"
        )
    return ConcurrentRun(results=results, errors=errors, wall_s=wall)


# --------------------------------------------------------------------------- #
# Performance probes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class LatencyStats:
    n: int
    mean_s: float
    p50_s: float
    p95_s: float
    p99_s: float
    max_s: float

    def __str__(self) -> str:
        ms = 1e3
        return (
            f"n={self.n} mean={self.mean_s * ms:.3f}ms p50={self.p50_s * ms:.3f}ms "
            f"p95={self.p95_s * ms:.3f}ms p99={self.p99_s * ms:.3f}ms max={self.max_s * ms:.3f}ms"
        )


def measure_latency(fn: Callable[[], object], *, n: int = 1000, warmup: int = 50) -> LatencyStats:
    """Call ``fn`` ``warmup + n`` times and report latency percentiles.

    Warm-up lets the specializing interpreter (PEP 659) quicken the hot bytecode
    and lets connections/caches settle, as you would in google-benchmark.
    """
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    clock = time.perf_counter
    for _ in range(n):
        t0 = clock()
        fn()
        samples.append(clock() - t0)
    q = statistics.quantiles(samples, n=100, method="inclusive")
    return LatencyStats(
        n=n,
        mean_s=statistics.fmean(samples),
        p50_s=q[49],
        p95_s=q[94],
        p99_s=q[98],
        max_s=max(samples),
    )


def measure_speedup[T](
    task: Callable[[T], object],
    inputs: list[T],
    executor_factory: Callable[[], Executor],
) -> float:
    """Return serial_wall_time / parallel_wall_time for ``task`` over ``inputs``."""
    t0 = time.perf_counter()
    for x in inputs:
        task(x)
    serial = time.perf_counter() - t0

    with executor_factory() as ex:
        t0 = time.perf_counter()
        list(ex.map(task, inputs))
        parallel = time.perf_counter() - t0
    return serial / parallel
