"""Runtime structural validation of a TypedDict against a real payload.

A TypedDict is erased at runtime, so on its own it is documentation that can
quietly stop being true. This is the strict-validation harness: production code
never runs it, the test suite always does — the same stance as the reference
SDK's `_strict_response_validation`, which is on in its fixtures and off for
users.
"""

from __future__ import annotations

import types
import typing
from typing import Any, Union, get_args, get_origin, get_type_hints


def check(payload: object, spec: type, path: str = "$") -> list[str]:
    """Structural violations of `payload` against `spec` (empty = valid)."""
    if not (isinstance(spec, type) and hasattr(spec, "__annotations__")
            and hasattr(spec, "__required_keys__")):
        return _check_value(payload, spec, path)
    if not isinstance(payload, dict):
        return [f"{path}: expected a mapping for {spec.__name__}, got {type(payload).__name__}"]
    return _check_mapping(payload, spec, path)


def _check_mapping(payload: dict[str, Any], spec: type, path: str) -> list[str]:
    hints = get_type_hints(spec)
    required: frozenset[str] = spec.__required_keys__          # type: ignore[attr-defined]
    out = [f"{path}.{k}: required key missing" for k in sorted(required - payload.keys())]
    out += [f"{path}.{k}: not in {spec.__name__} (undocumented key)"
            for k in sorted(payload.keys() - hints.keys())]
    for key, value in payload.items():
        if key in hints:
            out += _check_value(value, hints[key], f"{path}.{key}")
    return out


def _check_value(value: object, hint: Any, path: str) -> list[str]:
    origin = get_origin(hint)
    if hint is Any or hint is object:
        return []
    if origin in (Union, types.UnionType):
        return _check_union(value, hint, path)
    if origin is list:
        return _check_list(value, hint, path)
    if origin is dict:
        return _check_dict(value, hint, path)
    if origin is typing.Literal:
        # Value AND type: `True == 1`, so a value-only `in` admits booleans
        # into an int Literal — and Literal tags are the discriminators of
        # every event union, where a misrouted bool would be silent.
        opts = get_args(hint)
        ok = any(value == opt and type(value) is type(opt) for opt in opts)
        return [] if ok else [f"{path}: {value!r} not in {opts}"]
    if isinstance(hint, type) and hasattr(hint, "__required_keys__"):
        return check(value, hint, path)
    # `origin is None` is what makes this a real class rather than a subscripted
    # one, and it has to be asked BEFORE `isinstance(hint, type)` because that
    # question changes answer across the versions this package supports:
    # `isinstance(tuple[int, int], type)` is True on 3.10 and False from 3.11.
    # On 3.10 the generic reached `_check_scalar`, whose `isinstance(value,
    # hint)` raises "argument 2 cannot be a parameterized generic" — so the one
    # test asserting that unknown forms FAIL CLOSED died with a TypeError on the
    # oldest runtime in the matrix, and only there.
    if origin is None and isinstance(hint, type):
        return _check_scalar(value, hint, path)
    # FAIL CLOSED. The old fallback returned [] — a validator that passes what
    # it cannot read is vacuous for exactly the fields most likely to be new
    # (the first tuple, the first Mapping, the first anything-else a contract
    # grows). An unsupported hint is a checker gap to fix, loudly.
    return [f"{path}: unsupported annotation {hint!r} — teach shape.py this form"]


def _check_union(value: object, hint: Any, path: str) -> list[str]:
    """Valid if ANY member matches; report the closest-fitting member's errors."""
    attempts = [check(value, arg, path) for arg in get_args(hint)]
    if any(not errs for errs in attempts):
        return []
    return min(attempts, key=len)


def _check_list(value: object, hint: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{path}: expected list, got {type(value).__name__}"]
    (item_hint,) = get_args(hint) or (Any,)
    out: list[str] = []
    for i, item in enumerate(value):          # type: ignore[misc]
        out += _check_value(item, item_hint, f"{path}[{i}]")
    return out


def _check_dict(value: object, hint: Any, path: str) -> list[str]:
    """A mapping, with its PARAMETRIZATION honoured.

    Ignoring the args made every `dict[str, str]` field vacuous — any dict at
    all validated, whatever its values held.
    """
    if not isinstance(value, dict):
        return [f"{path}: expected dict, got {type(value).__name__}"]
    args = get_args(hint)
    if not args:
        return []
    key_hint, value_hint = args
    out: list[str] = []
    for key, item in value.items():          # type: ignore[union-attr]
        out += _check_value(key, key_hint, f"{path}[{key!r} (key)]")
        out += _check_value(item, value_hint, f"{path}[{key!r}]")
    return out


def _check_scalar(value: object, hint: type, path: str) -> list[str]:
    if hint is type(None):
        return [] if value is None else [f"{path}: expected None"]
    # bool subclasses int, so a bare isinstance would wave `True` through any
    # int or float field. No JSON producer means a boolean millisecond count.
    if hint in (int, float) and isinstance(value, bool):
        return [f"{path}: expected {hint.__name__}, got bool"]
    if hint is float and isinstance(value, int):
        return []                              # JSON ints are valid floats
    if hint is bool and not isinstance(value, bool):
        return [f"{path}: expected bool, got {type(value).__name__}"]
    return [] if isinstance(value, hint) else \
        [f"{path}: expected {hint.__name__}, got {type(value).__name__}"]


def assert_shape(payload: object, spec: type) -> None:
    errs = check(payload, spec)
    assert not errs, f"{spec.__name__} does not describe the payload:\n  " + "\n  ".join(errs)
