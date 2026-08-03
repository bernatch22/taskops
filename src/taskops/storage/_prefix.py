"""Naming a folded row by the first characters of its id.

Facts and milestones both live as events, so both are identified by a content hash — and every
renderer prints eight characters of it, because a 64-character hash in a terminal is noise. The
string a person can SEE is therefore the only one they can retype, which makes prefix resolution
part of the contract rather than a convenience: `context retire` once refused the exact eight
characters `context log` had just printed, and sent the reader back to `log` to read them again.

One function for both kinds. It was written twice — once for facts, once for milestones — before
the second copy was deleted: the rule ("an exact id wins; otherwise every row it could name") is
identical, and two copies of it is one place for the ambiguity behaviour to drift.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = ["matching"]


def matching(rows: Sequence[Mapping[str, object]], prefix: str) -> list[str]:
    """Every id `prefix` could name, sorted — the whole id alone when it matches one exactly.

    Ambiguity is RETURNED rather than resolved: which of two rows the caller meant is not a
    question this layer may answer by picking one. The caller above turns a list of two into a
    refusal that names both.

    An exact hit short-circuits, and that is not an optimisation: one id can be a prefix of
    another, and without this the row somebody named exactly would come back as "ambiguous".
    """
    if any(str(row["id"]) == prefix for row in rows):
        return [prefix]
    return sorted(str(row["id"]) for row in rows if str(row["id"]).startswith(prefix))
