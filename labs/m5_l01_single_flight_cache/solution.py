"""M5-L01 · Student Solution Workspace.

Your task: Refactor SingleFlightCache to prevent duplicate loads under concurrent stampedes,
while allowing distinct keys to load concurrently.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class SingleFlightCache:
    def __init__(self, loader: Callable[[Any], Any]) -> None:
        self.loader = loader
        self.cache: dict[Any, Any] = {}

    def get(self, key: Any) -> Any:
        if key not in self.cache:
            self.cache[key] = self.loader(key)
        return self.cache[key]
