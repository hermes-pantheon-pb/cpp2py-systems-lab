"""M2-L01 · Student Solution Workspace.

Your task: Refactor Tick and export_columnar to pass all criteria.
"""

from __future__ import annotations


class Tick:
    def __init__(self, ts: int, px: float, qty: int) -> None:
        self.ts = ts
        self.px = px
        self.qty = qty

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tick):
            return NotImplemented
        return (self.ts, self.px, self.qty) == (other.ts, other.px, other.qty)

    def __hash__(self) -> int:
        return hash((self.ts, self.px, self.qty))


def export_columnar(ticks: list[Tick]):
    return [t.ts for t in ticks], [t.px for t in ticks], [t.qty for t in ticks]
