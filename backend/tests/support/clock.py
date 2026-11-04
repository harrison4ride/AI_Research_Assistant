"""A clock that tests control, for the app's time-based rules.

The `clock` fixture (conftest.py) puts it in place of time.monotonic() and
asyncio.sleep() in the modules that pace or expire things: the arXiv client (3 s
between calls, cooldowns) and the search cache (10 minutes). Waiting is instant
and recorded, so these rules run with their real values and no test is slowed.
"""

import asyncio
from types import SimpleNamespace

_real_sleep = asyncio.sleep


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []  # every wait the app asked for, in seconds

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += max(seconds, 0.0)
        await _real_sleep(0)  # still let other tasks run, as a real sleep would

    def as_time_module(self) -> SimpleNamespace:
        """Stands in for the `time` module inside an app module."""
        return SimpleNamespace(monotonic=self.monotonic)

    def as_asyncio_module(self) -> SimpleNamespace:
        """Stands in for the `asyncio` module inside an app module that only sleeps and locks."""
        return SimpleNamespace(sleep=self.sleep, Lock=asyncio.Lock)
