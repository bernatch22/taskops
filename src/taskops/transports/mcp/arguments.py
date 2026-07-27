"""Reading the arguments a model wrote.

Its own module because this is where values from outside become the arguments a use case is
called with, and every rule about that belongs where it can be read at once. The caller is
a language model, so the rules are stricter than for a typed client: a missing key, a
number where a string belongs, and a comma-separated list where an array was declared are
all ordinary Tuesday traffic, and none of them may reach the engine as a crash.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ..._errors import BadRequest

__all__ = ["Missing", "repo", "text", "optional", "flag", "csv", "count", "entries"]


class Missing(BadRequest):
    """An argument the caller left out. A subclass so one `except` covers both this and
    an argument that was present and meaningless."""

    code = "bad_request"


def repo(arguments: dict[str, Any]) -> Path:
    return Path(text(arguments, "repo_path"))


def text(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise Missing(f"`{name}` is required, as a non-empty string")
    return value.strip()


def optional(arguments: dict[str, Any], name: str) -> str:
    """A string the caller may leave out entirely. "" means "no opinion"."""
    value = arguments.get(name)
    return value.strip() if isinstance(value, str) else ""


def flag(arguments: dict[str, Any], name: str, *, default: bool = False) -> bool:
    """Present-and-false is the only way to turn a defaulted flag off; a missing key
    means the caller had no opinion, which is not the same thing."""
    value = arguments.get(name)
    return value if isinstance(value, bool) else default


def csv(arguments: dict[str, Any], name: str) -> tuple[str, ...]:
    """A comma-separated string, or a real list, into a tuple.

    Both accepted because the schema says string and models send lists anyway — and a
    `mentions` field that silently dropped a list would mean a message nobody received,
    which is the worst possible way for this to fail.
    """
    value: object = arguments.get(name)
    if isinstance(value, list):
        items = cast("list[object]", value)
        return tuple(str(item).strip() for item in items if str(item).strip())
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return ()


def count(arguments: dict[str, Any], name: str = "count") -> int:
    """A non-negative integer, or 0 for "no opinion".

    `bool` is excluded explicitly: `True == 1` in Python, so `count: true` would silently mean one
    worker. A string of digits is accepted because a model that has been told a field is a number
    still sends "3" often enough to matter.
    """
    value = arguments.get(name)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def entries(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    """The `plan` batch, however the caller packaged it.

    FIELD HABIT: a model sends `{tasks: "<json string>"}` — learned from tools whose
    arguments are stringly typed — and it would fail as a missing list. A single task sent
    unwrapped is accepted for the same reason: the caller said what it wanted, and
    rejecting it over a bracket teaches it nothing about the real requirement.
    """
    found: object = arguments.get("tasks")
    if isinstance(found, str) and found.strip():
        try:
            found = json.loads(found)
        except json.JSONDecodeError as bad:
            raise Missing(f"`tasks` is a string that is not JSON: {bad}") from bad
    if isinstance(found, dict):
        found = [cast("object", found)]
    if isinstance(found, list) and found:
        items = cast("list[object]", found)
        return [cast("dict[str, Any]", item) for item in items if isinstance(item, dict)]
    raise Missing("`tasks` is required — a non-empty list of {title, spec, after?}")
