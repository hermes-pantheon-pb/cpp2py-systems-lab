"""M6-L01 · Verification harness for structured concurrency and task cancellation.

Run:  ./lab.py test M6-L01 [--target naive|solution|reference]
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import ModuleType

import pytest


# --------------------------------------------------------------------------- C1
@pytest.mark.criterion("C1")
def test_fanout_order(impl: ModuleType) -> None:
    async def main() -> list[int]:
        async def square(x: int) -> int:
            await asyncio.sleep(0.001)
            return x * x

        return await impl.fanout_pipeline([1, 2, 3, 4, 5], square)

    res = asyncio.run(main())
    assert res == [1, 4, 9, 16, 25]


# --------------------------------------------------------------------------- C2
@pytest.mark.criterion("C2")
def test_single_threaded_concurrency(impl: ModuleType) -> None:
    threads: set[int] = set()

    async def worker(x: int) -> int:
        threads.add(threading.get_ident())
        await asyncio.sleep(0.001)
        return x

    res = asyncio.run(impl.fanout_pipeline([1, 2, 3], worker))
    assert res == [1, 2, 3]
    assert len(threads) == 1, "async tasks should run on a single event loop thread"


# --------------------------------------------------------------------------- C3
@pytest.mark.criterion("C3")
def test_cancellation_and_zero_leaks(impl: ModuleType) -> None:
    long_task_completed = False

    async def buggy_worker(x: int) -> int:
        nonlocal long_task_completed
        if x == 1:
            await asyncio.sleep(0.01)
            raise RuntimeError("task 1 failed")
        else:
            try:
                await asyncio.sleep(0.15)
                long_task_completed = True
            except asyncio.CancelledError:
                raise
            return x

    async def run() -> list[asyncio.Task[object]]:
        try:
            await impl.fanout_pipeline([1, 2], buggy_worker)
        except (RuntimeError, ExceptionGroup):
            pass
        # Give a moment for any cancellation cleanup
        await asyncio.sleep(0.02)
        active = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        return active

    active_tasks = asyncio.run(run())
    assert not long_task_completed, "Sibling long task was not cancelled!"
    assert len(active_tasks) == 0, (
        f"Leaked {len(active_tasks)} orphan background tasks after pipeline returned! "
        "Use `asyncio.TaskGroup` to guarantee structured lifetime boundaries."
    )


# --------------------------------------------------------------------------- C4
@pytest.mark.criterion("C4")
def test_nonblocking_latency(impl: ModuleType) -> None:
    async def run() -> float:
        t0 = time.perf_counter()
        await impl.fanout_pipeline([1, 2, 3, 4], impl.sample_delay_worker)
        return time.perf_counter() - t0

    elapsed = asyncio.run(run())
    assert elapsed < 0.12, (
        f"Pipeline took {elapsed:.3f}s (budget is < 0.12s). "
        "Coroutines are using blocking calls (e.g. time.sleep) or running sequentially."
    )
