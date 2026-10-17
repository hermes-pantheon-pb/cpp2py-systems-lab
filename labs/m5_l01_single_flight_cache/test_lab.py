"""M5-L01 · Verification harness for single-flight cache and stampede suppression.

Run:  ./lab.py test M5-L01 [--target naive|solution|reference]
"""

from __future__ import annotations

import threading
import time
from types import ModuleType

import pytest

from harness import aggressive_switching, run_concurrently


# --------------------------------------------------------------------------- C1
@pytest.mark.criterion("C1")
def test_basic_get_caching(impl: ModuleType) -> None:
    calls = 0

    def loader(k: str) -> str:
        nonlocal calls
        calls += 1
        return f"val:{k}"

    cache = impl.SingleFlightCache(loader)
    assert cache.get("alpha") == "val:alpha"
    assert cache.get("alpha") == "val:alpha"
    assert calls == 1
    assert cache.get("beta") == "val:beta"
    assert calls == 2


# --------------------------------------------------------------------------- C2
@pytest.mark.criterion("C2")
def test_stampede_single_flight(impl: ModuleType) -> None:
    calls = 0
    calls_lock = threading.Lock()

    def slow_loader(k: str) -> str:
        nonlocal calls
        time.sleep(0.01)  # yield GIL during I/O
        with calls_lock:
            calls += 1
        return f"payload:{k}"

    cache = impl.SingleFlightCache(slow_loader)
    n_threads = 32

    with aggressive_switching(1e-6):
        run = run_concurrently(lambda i: cache.get("stampede_key"), n_threads=n_threads)

    assert not run.errors, f"Unexpected errors during stampede: {run.errors}"
    assert all(res == "payload:stampede_key" for res in run.results)
    assert calls == 1, (
        f"loader was invoked {calls} times for the same key during a {n_threads}-thread stampede! "
        "A proper single-flight cache must execute the loader exactly once."
    )


# --------------------------------------------------------------------------- C3
@pytest.mark.criterion("C3")
def test_distinct_keys_load_in_parallel(impl: ModuleType) -> None:
    def delay_loader(k: int) -> int:
        time.sleep(0.05)
        return k * 2

    cache = impl.SingleFlightCache(delay_loader)
    keys = [10, 20, 30, 40]

    t0 = time.perf_counter()
    run = run_concurrently(lambda i: cache.get(keys[i]), n_threads=len(keys))
    elapsed = time.perf_counter() - t0

    assert not run.errors
    assert run.results == [20, 40, 60, 80]
    assert elapsed < 0.14, (
        f"Loading 4 keys took {elapsed:.3f}s (budget is < 0.14s). "
        "A coarse lock is held during loader I/O, preventing distinct keys from loading in parallel."
    )


# --------------------------------------------------------------------------- C4
@pytest.mark.criterion("C4")
def test_failure_propagation_and_retry(impl: ModuleType) -> None:
    calls = 0
    calls_lock = threading.Lock()
    should_fail = True

    def flakey_loader(k: str) -> str:
        nonlocal calls
        time.sleep(0.01)
        with calls_lock:
            calls += 1
        if should_fail:
            raise RuntimeError(f"upstream down for {k}")
        return f"recovered:{k}"

    cache = impl.SingleFlightCache(flakey_loader)
    n_threads = 10

    with aggressive_switching(1e-6):
        run = run_concurrently(lambda i: cache.get("retry_key"), n_threads=n_threads)

    assert len(run.errors) == n_threads, (
        f"Expected all {n_threads} threads to receive the exception, got {len(run.errors)}"
    )
    assert all(isinstance(e, RuntimeError) for e in run.errors)
    assert calls == 1, (
        f"Failing loader was invoked {calls} times during a {n_threads}-thread stampede "
        f"(expected exactly 1 shared invocation)."
    )

    # Verify key was not permanently poisoned in cache
    should_fail = False
    val = cache.get("retry_key")
    assert val == "recovered:retry_key"
    assert calls == 2
