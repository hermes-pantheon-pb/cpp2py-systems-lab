"""M5-L01 · NAIVE translation — check-then-act race condition without synchronization.

DO NOT EDIT: the test-suite must keep failing on this file (see `lab.py verify`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class SingleFlightCache:
    def __init__(self, loader: Callable[[Any], Any]) -> None:
        self.loader = loader
        self.cache: dict[Any, Any] = {}

    def get(self, key: Any) -> Any:
        # Check-then-act race: between check and store, multiple threads call loader
        if key not in self.cache:
            self.cache[key] = self.loader(key)
        return self.cache[key]
