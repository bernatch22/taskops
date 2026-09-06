"""GET /healthz — liveness for a host, IDENTITY for a window.

Split out of `handler.py` when the Editor's door arrived and the handler had
no line to give: this is the one GET whose body is a policy rather than a
route, and the policy carries its own post-mortem.

`taskops ui` must be able to tell "our window is up" from "something answered
that port" — reusing by liveness alone reopened tabs onto a four-day-old
binary (`cli/window.py`). So a WINDOW names its checkout and its version. A
board HOST keeps the terse answer: its healthz is public, and a server path in
it is a leak.
"""

from __future__ import annotations

from typing import Any

from .mounts import Mounts
from .._version import __version__


def answer(mounts: Mounts) -> dict[str, Any]:
    data: dict[str, Any] = {"boards": mounts.count()}
    if mounts.repo is not None:
        data["window"] = str(mounts.repo)
        data["version"] = __version__
    return data
