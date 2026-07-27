"""`taskops hook <event>` — the Claude Code hook protocol, on stdin and stdout.

The whole integration in one command. A hook receives a JSON object on stdin and may answer
with one on stdout; this is the wire, and `_events` is what each event means.

```
PreToolUse    permissionDecision: "deny"     refuse the tool call, with a reason
              updatedInput: {...}            REWRITE it — this is how the Task trailer
                                             gets into the agent's own `git commit`
SessionStart  additionalContext: "..."       inject what the session holds and its messages
PostToolUse   additionalContext: "..."       deliver a message another agent just wrote
```

Everything here FAILS OPEN with an empty object. A hook that raised would block the tool call
it was inspecting, and blocking a developer's commit because taskops had a bad day is how a
coordination tool gets uninstalled.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, cast

from ...._errors import TaskopsError
from . import _events

__all__ = ["register"]

HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "pre-tool-use": _events.pre_tool_use,
    "post-tool-use": _events.post_tool_use,
    "session-start": _events.session_start,
    "stop": _events.stop,
}


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("hook", help="the Claude Code hook protocol (stdin JSON)")
    parser.add_argument("event", choices=sorted(HANDLERS))
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    """Read the event, print the response, exit 0 ALWAYS.

    Zero even for a denial: the decision travels in the JSON, and a non-zero exit is ALSO read
    as a denial — so returning both would refuse the call twice, once without the reason
    attached, and the agent would see the version that tells it nothing.
    """
    handler = HANDLERS[str(args.event)]
    try:
        response = handler(_stdin())
    except (TaskopsError, OSError, ValueError):
        response = {}
    if response:
        print(json.dumps(response))
    return 0


def _stdin() -> dict[str, Any]:
    """The event payload, or {} for anything unreadable.

    A hook run by hand has no stdin at all, so the tty check comes first — without it, `taskops
    hook stop` in a terminal would block forever waiting for input nobody is going to send.
    """
    if sys.stdin.isatty():
        return {}
    try:
        parsed: object = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return {}
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}
