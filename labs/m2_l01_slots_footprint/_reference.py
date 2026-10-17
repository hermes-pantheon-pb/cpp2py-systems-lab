"""M2-L01 · IDIOMATIC reference (spoiler).

Uses `@dataclass(frozen=True, slots=True)` to produce fixed member descriptors
without a per-instance `__dict__`, enforces immutability, and exports to contiguous
typed `array.array` buffers.
"""

from __future__ import annotations

import array
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tick:
    ts: int
    px: float
    qty: int


def export_columnar(ticks: list[Tick]) -> tuple[array.array, array.array, array.array]:
    ts_arr = array.array("I", (t.ts for t in ticks))
    px_arr = array.array("d", (t.px for t in ticks))
    qty_arr = array.array("I", (t.qty for t in ticks))
    return ts_arr, px_arr, qty_arr
