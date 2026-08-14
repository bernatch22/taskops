"""The single registry of event KINDS — what the log may say, and what replay does with it.

Split out of `types.py` at its own seam: that file is the data MODEL (the rows
and the wire format), this one is the vocabulary of the log. v1 spread the same
facts across four hand-maintained tuples (`REPLAYED`, `SAYS_STATUS`,
`LOCAL_ONLY_KINDS`, `WORK`) and they drifted; there is deliberately no
`LOCAL_ONLY_KINDS` here either — every event lives wherever the log lives.

`types` re-exports both names, so `from .types import KINDS` keeps working and
callers still have one name to know.
"""

from __future__ import annotations

from typing import NamedTuple


class Kind(NamedTuple):
    replayed: bool  # does replay fold it into state, or is it history only?
    body_keys: tuple[str, ...]  # required keys; extras are allowed and kept


KINDS: dict[str, Kind] = {
    "created": Kind(True, ("card",)),
    "edited": Kind(True, ("field", "to")),
    "claimed": Kind(True, ("branch",)),
    "released": Kind(True, ("note",)),
    "status": Kind(True, ("to",)),
    "comment": Kind(False, ("text",)),
    "commit": Kind(False, ("sha", "subject")),
    "merged": Kind(False, ("into", "sha")),
    "milestone": Kind(True, ("op",)),
    # A fact about the REPO, not about any card: `task` is PROJECT and the fold
    # keeps the newest per `op`. Same shape as `milestone` on purpose — an `op`
    # is how a family of board-level facts grows without a new kind each time.
    "project": Kind(True, ("op",)),
    # Review is derived from the thread, exactly like a pending mention: both
    # kinds are history-only, and `core/review.py` folds them into a Standing.
    "submitted": Kind(False, ("note",)),  # the worker says it is finished
    "reviewed": Kind(False, ("verdict", "note")),  # verdict: "pass" | "changes"
    # A narration that is a committed FILE. The body is a POINTER, never the
    # bytes; `task` is PROJECT because a report is about a CHAPTER; the list per
    # chapter is a fold. `core/reports.py` carries the argument and `path`'s rule.
    "report": Kind(False, ("path", "title", "milestone", "sha")),
}
