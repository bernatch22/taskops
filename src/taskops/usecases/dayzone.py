"""Where the project's day starts — reading the zone, and refusing one that is not a zone.

A dossier is a claim about a calendar day, and a calendar day is only a fixed interval once
somebody says whose midnight it is. On one machine nobody has to: "local" is unambiguous while
there is one local. On a shared board it is not, and the failure is quiet — two developers three
hours apart file the same events under different dates, so the same closed day renders as two
different documents, and the second one to be generated replaces the first in git without a
conflict. Measured on the axion board: 2026-07-30 counted 8 commits from UTC-3 and 5 from UTC+2,
the missing 3 sitting inside 07-31.

    taskops policy day_zone Europe/Madrid

Validated here, at the door, exactly like `reviewer`: a zone the tz database does not know would
otherwise be stored, read back by every report, and refused in the middle of somebody's morning
— a setting whose only symptom is a traceback in an unrelated command.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from .._errors import BadRequest
from ..storage import Store

__all__ = ["named"]

_SUGGEST = ("Europe/Madrid", "UTC", "America/Argentina/Buenos_Aires")
"""Three shapes rather than a list of six hundred: a region/city name, `UTC`, and one with a
sub-region — which is the spelling people get wrong."""


def named(store: Store, value: str) -> str:
    """Validate one zone as written, or refuse it saying what a zone looks like.

    "" is legal and means "each machine's own", which is what every project says before anybody
    decides — and how a project goes back to that.

    `store` is unused and part of the signature every validator shares: the lookup in
    `usecases.policy` is what registers a setting, and a table of two different call shapes is
    how one of them stops being called.
    """
    wanted = value.strip()
    if not wanted:
        return ""
    try:
        ZoneInfo(wanted)
    except (ZoneInfoNotFoundError, ValueError):
        raise BadRequest(
            f"`{wanted}` is not a timezone — `day_zone` takes an IANA name, "
            f"e.g. {', '.join(_SUGGEST)}{_nearby(wanted)}") from None
    return wanted


def _nearby(wanted: str) -> str:
    """The zones whose city half matches what was typed. `Madrid` is the mistake people make,
    and naming `Europe/Madrid` back at them is the whole answer to it."""
    tail = wanted.rsplit("/", 1)[-1].lower()
    close = sorted(z for z in available_timezones() if z.rsplit("/", 1)[-1].lower() == tail)
    return f". Did you mean {', '.join(close[:3])}?" if close else ""
