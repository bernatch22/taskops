"""`pre-tool-use · post-tool-use · session-start · stop` — the Claude Code hook protocol.

The whole integration in four subcommands. A hook receives a JSON object on stdin and may
answer with one on stdout; this is the wire, and `events` is what each event means. The names
are the EVENTS themselves, because that is what the person wiring `hooks.json` is holding —
not a verb taskops happens to call it internally.

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

from ..._errors import TaskopsError
from . import _door as door
from . import events
from ._sweeplaunch import launch_sweep

__all__ = ["register", "HANDLERS", "session_start"]


def session_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Inject the brief, and kick the daily sweep off on the way past.

    The launch lives HERE and not in `events` because it answers nothing: `events` is what an
    event MEANS, and a detached process is not part of the reply. It runs first and returns in
    microseconds — see `_sweeplaunch` — so the brief the session actually reads is never made
    to wait on a report it is not going to see.

    It used to publish the project's specialists into `.claude/agents/` as well. That step is
    gone with the registry that needed it: the specialists ARE Claude Code subagents now, in
    the directory Claude Code already reads.
    """
    where = events.cwd(payload)
    launch_sweep(where)
    return events.session_start(payload)


HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "pre-tool-use": events.pre_tool_use,
    "post-tool-use": events.post_tool_use,
    "session-start": session_start,
    "subagent-stop": door.subagent_stop,
    "stop": events.stop,
}


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """One parser per event, flat. A `hook <event>` group would put a word in every line of
    `hooks.json` that carries no information — the module name already said "hook"."""
    for name in sorted(HANDLERS):
        parser = sub.add_parser(name, help=f"the Claude Code {name} hook (stdin JSON)")
        parser.set_defaults(run=run, event=name)


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

    A hook run by hand has no stdin at all, so the tty check comes first — without it, running
    `stop` in a terminal would block forever waiting for input nobody is going to send.
    """
    if sys.stdin.isatty():
        return {}
    try:
        parsed: object = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return {}
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}
