"""Create tasks from a JSON file or stdin — reached as `taskops tasks plan`.

JSON rather than flags: a plan is a nested structure with dependencies in it, and every
attempt to express one in shell arguments turns into a worse JSON. `-` reads stdin, which is
what makes `... | taskops tasks plan -` work from a script.

The top-level `taskops plan` was the agent's, and agents have `taskops_plan`. The subparser
went; the function is still the only creator of a card, which is what keeps a hand-typed card
carrying the same event body a planned one does.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, cast

from ...._errors import BadRequest
from ....render import render_plan
from ....usecases import plan as create
from ._shared import repo_of

__all__ = ["run"]


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
