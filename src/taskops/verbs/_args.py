"""Strict argument reading. No magic coercions, ever.

v1 accepted `"true"`, `"false"`, CSV-or-list and JSON-in-a-string in fifteen
places, and one of those turned `claim="false"` into `True`. Here a wrong
shape is a `BadRequest` whose message shows the right one — the schema in
`mcp/tools.py` already told the caller, so this is the second line of defence,
not the first.
"""

from __future__ import annotations

from typing import Any, cast

from .._ids import is_task_id
from .._errors import BadRequest

Args = dict[str, Any]


def text(args: Args, key: str, *, default: str | None = None) -> str:
    value = args.get(key, default)
    if value is None:
        raise BadRequest(f"{key}= is required")
    if not isinstance(value, str):
        raise BadRequest(f"{key}= must be text, got {type(value).__name__}")
    return value.strip()


def ident(args: Args, key: str, *, default: str | None = None) -> str:
    value = text(args, key, default=default)
    if value and not is_task_id(value):
        raise BadRequest(f"{key}={value!r} is not a card id — they look like tk-a1b2c3")
    return value


def flag(args: Args, key: str, *, default: bool = False) -> bool:
    value = args.get(key, default)
    if not isinstance(value, bool):
        raise BadRequest(f"{key}= must be true or false (a JSON boolean), got {value!r}")
    return value


def number(args: Args, key: str, *, default: int, low: int, high: int) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadRequest(f"{key}= must be a whole number between {low} and {high}")
    if not low <= value <= high:
        raise BadRequest(f"{key}={value} is outside {low}..{high}")
    return value


def strings(args: Args, key: str) -> list[str]:
    value = args.get(key, [])
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in cast("list[Any]", value)):
        raise BadRequest(f'{key}= must be a list of strings, e.g. {key}=["src/models.py"]')
    return [x.strip() for x in cast("list[str]", value) if x.strip()]


def rows(args: Args, key: str) -> list[Args]:
    value = args.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(x, dict) for x in cast("list[Any]", value)
    ):
        raise BadRequest(f'{key}= must be a list of objects, e.g. {key}=[{{"title": "…"}}]')
    return cast("list[Args]", value)
