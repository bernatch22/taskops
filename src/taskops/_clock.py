"""The only module that reads the clock.

`tests/test_architecture.py` pins this: `time.time`, `datetime.now`,
`time.monotonic`, `localtime` and `strftime` may not appear anywhere else
(except `core/hours.py`, which does calendar arithmetic and says so). v1 let a
stray `strftime` through and a report cut days in two timezones at once.

Tests freeze time through `set_now`; nothing else may.
"""

from __future__ import annotations

import time

_frozen: float | None = None


def now() -> float:
    """Wall-clock seconds. The single source of 'when'."""
    return _frozen if _frozen is not None else time.time()


def set_now(value: float | None) -> None:
    """Freeze (or unfreeze) the clock. Tests only — never called by the package."""
    global _frozen
    _frozen = value
