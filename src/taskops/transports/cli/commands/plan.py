"""`taskops plan` — create tasks from a JSON file or stdin.

JSON rather than flags: a plan is a nested structure with dependencies in it, and every
attempt to express one in shell arguments turns into a worse JSON. `-` reads stdin, which is
what makes `... | taskops plan -` work from a script.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, cast

from ...._errors import BadRequest
from ....render import render_plan
from ....usecases import plan as create
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("plan", help="create tasks from JSON (a file, or - for stdin)")
    add_target(parser)
    parser.add_argument("source", help="path to a JSON array of tasks, or - for stdin")
    parser.add_argument("--actor", default="", help="who is calling")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    return render_plan(create(repo_of(args), _entries(str(args.source)),
                              actor=str(args.actor)))


def _entries(source: str) -> list[dict[str, Any]]:
    raw = sys.stdin.read() if source == "-" else open(source, encoding="utf-8").read()
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError as bad:
        raise BadRequest(f"{source} is not valid JSON: {bad}") from bad
    if isinstance(parsed, dict):
        parsed = [cast("object", parsed)]
    if not isinstance(parsed, list):
        raise BadRequest("expected a JSON array of {title, spec, after?} objects")
    items = cast("list[object]", parsed)
    return [cast("dict[str, Any]", item) for item in items if isinstance(item, dict)]
