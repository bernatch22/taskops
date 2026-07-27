"""A params contract -> the JSON Schema a host validates against.

Generated, never written twice. The alternative — a JSON literal beside the TypedDict — is
two declarations of one thing, and the one that drifts is always the schema, because
nothing type-checks it: the tool keeps advertising a parameter the dispatch stopped
reading, and the agent keeps sending it.
"""

from __future__ import annotations

from typing import Any, get_args, get_type_hints

__all__ = ["json_schema"]

_JSON_TYPES: dict[Any, str] = {str: "string", bool: "boolean", int: "integer",
                               float: "number"}


def json_schema(params: type[Any]) -> dict[str, Any]:
    """One tool's `inputSchema`, derived from its TypedDict.

    Required-ness comes from the TypedDict's own totality rather than a hand-written list,
    so an optional key cannot be advertised as required by whoever forgot the second edit.
    See `contracts/__init__` for why that totality has to be spelled with a class split.
    """
    required: frozenset[str] = getattr(params, "__required_keys__", frozenset())
    hints = get_type_hints(params, include_extras=True)
    return {"type": "object",
            "properties": {name: _property(hint) for name, hint in hints.items()},
            "required": sorted(required)}


def _property(hint: Any) -> dict[str, Any]:
    """One field: its JSON type, its allowed values, and what it is for."""
    described = getattr(hint, "__metadata__", ())
    annotation = getattr(hint, "__origin__", hint) if described else hint
    schema: dict[str, Any] = {"description": " ".join(str(d) for d in described)}
    if getattr(annotation, "__origin__", None) is list or annotation is list:
        # An array of objects, with the ITEM shape left OPEN on purpose: `plan` accepts
        # the habitual spellings a model reaches for (a bare `after` instead of a list, a
        # comma-separated `files` string), and a schema that pinned the canonical forms
        # would have the host reject the very inputs `_entry` goes out of its way to read.
        return {**schema, "type": "array", "items": {"type": "object"}}
    choices = list(get_args(annotation))
    if choices and all(isinstance(c, (str, int, bool)) for c in choices):
        # A Literal: the allowed values ARE the documentation. Rendered as a bare string,
        # the agent can send anything and only finds out at dispatch.
        return {**schema, "type": _JSON_TYPES.get(type(choices[0]), "string"),
                "enum": choices}
    return {**schema, "type": _JSON_TYPES.get(annotation, "string")}
