"""Reports — a narration that is a committed FILE, on the board by reference.

A report is the one artefact a machine cannot regenerate, and until now it died
in a chat transcript. It becomes part of the board the same way a commit does:
the FILE lives in git, and the log stores a pointer to it — `{path, title,
milestone, sha}` — never its bytes. That is the rule that already keeps diffs
out of `events.jsonl` (`verbs/record.py::bind` records a sha and a numstat, not
a patch), applied to prose: a 200KB report grows the log by a few hundred
bytes, and a reader renders it from its OWN clone at that sha.

Three consequences, and each one is why this module is shaped like this:

**History-only.** `report` is `Kind(False, …)` in `core/types.py`: replay never
folds it into state, because there is nothing to fold. "Which reports does this
chapter have" is a QUESTION, answered by `of()` on every read — never a table,
never a column on `Milestone`. Storing the list would be a second fact to keep
in step with the events that produced it, which is this project's oldest bug
(`core/mentions.py` carries the long version).

**The path is a shape, not a suggestion.** `under()` is the ONE place that
decides whether a path is a report path, and both ends use it: the verb that
registers one (`verbs/record.py::filed`) and the `/git` door that later serves
the bytes. A door that reads "any repo-relative path the caller sends" is a
file server, and the dashboard would be handing out the reader's clone.
`..`, an absolute path and a bare `.taskops/reports/` are all "not a report",
returned as `""` rather than raised: the caller owns the refusal wording, and
a fold over foreign history must never explode on one bad row.

**Newest first.** A reader wants the last thing written about a chapter, and
the caller caps the list and sends the honest total beside it
(`verbs/_facts.py::reports`, `done_total`'s idiom).

Pure (layer 1): no clock, no store, no path from the filesystem — `under()` is
string work on purpose, because a `Path` here would resolve against the machine
that happens to be asking.
"""

from __future__ import annotations

from typing import Iterable, TypedDict

from .types import Event

KIND = "report"

DIR = ".taskops/reports/"
"""Where a report file lives, repo-relative, and the whole of the shape rule."""


class Report(TypedDict):
    """One registered report. Computed from its event on every read; never a row.

    `by` is the actor that REGISTERED it, which is the same name `core/mentions.py`
    gives the author of a comment. `sha` is the commit that carries the file at
    `path` — the pair is what a reader needs to fetch the bytes, and neither one
    is useful alone.
    """

    id: str  # the event id: stable, content-addressed, a key a list can use
    path: str
    title: str
    milestone: str
    sha: str
    by: str
    ts: float


def under(path: str) -> str:
    """The repo-relative report path, or `""` if it is not one.

    Normalises only what cannot change meaning — surrounding space, a `./`
    prefix, Windows separators — and refuses everything else rather than
    repairing it. A traversal (`..`), an absolute path, a doubled separator and
    the directory itself all read as "not a report".
    """
    text = path.strip().replace("\\", "/").removeprefix("./")
    if any(part in ("", ".", "..") for part in text.split("/")):
        return ""  # a traversal, an absolute path, a doubled slash — or DIR itself
    return text if text.startswith(DIR) else ""


def of(events: Iterable[Event], milestone: str = "") -> list[Report]:
    """Every registered report, newest first — all chapters, or just one.

    `milestone=""` is the whole board rather than an empty answer: the same
    bargain `verbs/events.py` makes, so a caller with nothing in focus still
    sees that reports exist. A row whose `path` no longer passes `under()` is
    dropped, not repaired — history is replayed forever and a rule that
    tightened must not resurrect what it now refuses.

    `sorted(reverse=True)` on a STABLE sort keeps arrival order among events
    sharing a timestamp, exactly as `core/replay.py` settles simultaneity: two
    reports registered in the same instant must not swap on every read.
    """
    found = [_row(e) for e in events if e["kind"] == KIND]
    kept = [r for r in found if r["path"] and (not milestone or r["milestone"] == milestone)]
    return sorted(kept, key=lambda r: r["ts"], reverse=True)


def _row(event: Event) -> Report:
    """A body is data from the wire: give every field a typed home, coerce nothing.

    An event written by a newer version keeps its extra keys in the log and
    loses them here, which is correct — this shape is what two consumers agreed
    on, and a reader that forwards unknown keys makes the shape unknowable.
    """
    body = event["body"]
    return Report(
        id=event["id"],
        path=under(str(body.get("path", ""))),
        title=str(body.get("title", "")),
        milestone=str(body.get("milestone", "")),
        sha=str(body.get("sha", "")),
        by=event["actor"],
        ts=event["ts"],
    )
