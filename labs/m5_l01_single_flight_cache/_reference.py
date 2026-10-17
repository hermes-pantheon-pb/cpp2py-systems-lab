"""M5-L01 · IDIOMATIC reference (spoiler).

Implements single-flight suppression using `threading.Lock` and `concurrent.futures.Future`.
The first thread to request a missing key executes `loader(key)` OUTSIDE the lock;
all other concurrent threads requesting the same key wait on the leader's Future.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any


class SingleFlightCache:
    def __init__(self, loader: Callable[[Any], Any]) -> None:
        self.loader = loader
        self.cache: dict[Any, Any] = {}
        self._in_flight: dict[Any, Future[Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any:
        with self._lock:
            if key in self.cache:
                return self.cache[key]

            if key in self._in_flight:
                fut = self._in_flight[key]
                is_leader = False
            else:
                fut = Future()
                self._in_flight[key] = fut
                is_leader = True

        if not is_leader:
            # Followers await the leader's future outside the lock
            return fut.result()

        # Leader executes loader outside the lock so other keys load in parallel
        try:
            val = self.loader(key)
            with self._lock:
                self.cache[key] = val
                self._in_flight.pop(key, None)
            fut.set_result(val)
            return val
        except BaseException as exc:
            with self._lock:
                self._in_flight.pop(key, None)
            fut.set_exception(exc)
            raise
