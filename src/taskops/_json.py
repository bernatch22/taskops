"""Foreign JSON becomes a typed mapping HERE, or it becomes nothing.

Every boundary that reads JSON somebody else wrote — a config file, an HTTP
envelope, an MCP argument object — goes through `as_object`. One place to be
lenient, everywhere else typed. v1 spread this coercion over fifteen call
sites and one of them read `claim="false"` as True.
"""

from __future__ import annotations

from typing import Any, cast


def as_object(value: object) -> dict[str, Any]:
    """A JSON object as `dict[str, Any]`. Anything else is an empty mapping."""
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in cast("dict[Any, Any]", value).items()}


def as_rows(value: object) -> list[dict[str, Any]]:
    """A JSON array of objects. A non-object entry becomes an empty mapping."""
    if not isinstance(value, list):
        return []
    return [as_object(x) for x in cast("list[object]", value)]


def as_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [x for x in cast("list[object]", value) if isinstance(x, str)]


def text(value: object, default: str = "") -> str:
    """A string field that may be missing or of the wrong type."""
    return value if isinstance(value, str) else default


def query(url: str) -> dict[str, str]:
    """`…?token=abc&invite=xyz` → the parameters, without a urllib import at
    every call site. Anything malformed is simply absent."""
    _, _, tail = url.partition("?")
    found: dict[str, str] = {}
    for part in tail.split("&"):
        key, sep, value = part.partition("=")
        if sep and key:
            found[key] = value
    return found
