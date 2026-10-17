"""M6-L01 · NAIVE translation — fire-and-forget tasks without structured cleanup.

DO NOT EDIT: the test-suite must keep failing on this file (see `lab.py verify`).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


async def fanout_pipeline(
    inputs: list[Any],
    worker: Callable[[Any], Awaitable[Any]],
) -> list[Any]:
    # Naive anti-pattern 1: fire-and-forget tasks without structured group
    tasks = [asyncio.create_task(worker(item)) for item in inputs]
    results = []
    # If one task raises, siblings continue running as orphan zombies!
    for task in tasks:
        results.append(await task)
    return results


async def sample_delay_worker(item: int) -> int:
    # Naive anti-pattern 2: blocking time.sleep freezes the event loop!
    time.sleep(0.05)
    return item * 2
