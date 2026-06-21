"""Simple rate limiter for the IBI/511 platform (10 calls / 60 seconds)."""
from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    def __init__(self, max_calls: int = 10, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.period:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            sleep_for = self.period - (now - self._calls[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
            self.acquire()
            return
        self._calls.append(time.monotonic())
