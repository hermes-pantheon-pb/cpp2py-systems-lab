"""M6-L01 · IDIOMATIC reference (spoiler).

Uses `asyncio.TaskGroup` for structured concurrency. If any task raises,
all sibling tasks are cancelled and awaited before exiting.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


async def fanout_pipeline(
    inputs: list[Any],
    worker: Callable[[Any], Awaitable[Any]],
) -> list[Any]:
    results: list[Any] = [None] * len(inputs)

    async def indexed_runner(idx: int, val: Any) -> None:
        results[idx] = await worker(val)

    async with asyncio.TaskGroup() as tg:
        for i, item in enumerate(inputs):
            tg.create_task(indexed_runner(i, item))

    return results


async def sample_delay_worker(item: int) -> int:
    # Idiomatic non-blocking coroutine
    await asyncio.sleep(0.05)
    return item * 2
