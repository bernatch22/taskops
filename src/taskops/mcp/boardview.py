"""The board panorama: `taskops_board`'s nine groups, in the order to act.

Split out of `render.py` when the wave line was added and the module passed its
200-line budget. The seam is the one `render.py`'s own shape already had: THIS
is the one big screen — a header, one block per group, the team and the hours —
while `render.py` keeps what every other tool result is made of (`plain`, the
pulse line, `ago`). Both are still the only renderers in the project; the rule
`tests/test_architecture.py` enforces is the budget, and it is met by splitting
where the file was already two things, not by shortening the post-mortems.
"""

from __future__ import annotations

from typing import Any

from .._json import as_rows, as_object, as_strings
from .render import BULLET, ago, pulse
from ..core.hours import human


def board(data: dict[str, Any], now: float) -> str:
    groups = _obj(data.get("groups"))
    out = [_header(data), ""]
    out += _group("MERGE — done, not integrated → taskops_merge", groups.get("merge"), now)
    out += _mentions(groups.get("mentions"), now)
    out += _group(
        "REVIEW — handed in, nobody checking → review it yourself: taskops_review task=…",
        groups.get("review"),
        now,
    )
    out += _group(
        "CHANGES — a reviewer asked for changes → back to its worker",
        groups.get("changes"),
        now,
    )
    out += _group(
        "STALLED — owned, nobody running it → taskops_assign to hand it over",
        groups.get("stalled"),
        now,
    )
    out += _group("TAKE — ready → taskops_assign", groups.get("take"), now, _wave(data))
    out += _group("DOING — somebody holds it right now", groups.get("doing"), now)
    out += _group("REVIEWING — somebody is reviewing it right now", groups.get("reviewing"), now)
    out += _group("BLOCKED — waiting on a dependency", groups.get("blocked"), now)
    team = _rows(data.get("team"))
    if team:
        out += ["", "TEAM  " + " · ".join(f"{t['actor']} {ago(t['ago'])}" for t in team)]
    hours = _obj(data.get("hours"))
    if hours:
        out += ["", "HOURS " + _hours(hours)]
    out += ["", pulse(data)]
    return "\n".join(out)



# ── pieces ──────────────────────────────────────────────────────────────────


def _header(data: dict[str, Any]) -> str:
    """One line saying WHICH chapter this is — and never guessing between two.

    With several milestones open, naming one of them would be a coin toss, so
    the header names them all and says how to focus. (v1 answered "the open
    milestone" differently in three places.)
    """
    stone = _obj(data.get("milestone"))
    if stone:
        return f"{BULLET} {stone.get('title')} — {stone.get('goal', '')}".rstrip(" —")
    # `milestones` carries the landed chapters too (`verbs/pulse.py::_chapters`),
    # and this line is about which chapter to FOCUS: a landed one is history, not
    # a choice, and counting it here would say "3 open milestones" over one.
    others = [m for m in _rows(data.get("milestones")) if m.get("status") == "open"]
    if not others:
        return f'{BULLET} no open milestone — taskops_plan milestone="…" goal="…" opens one'
    names = " · ".join(f"{m['id']} {m['title']}" for m in others)
    return f"{BULLET} {len(others)} open milestones: {names} — pass milestone=<id> to focus one"


def _wave(data: dict[str, Any]) -> list[str]:
    """The dispatch advice, under TAKE — `core/seams.py::wave`. A line, not a
    lock: nothing here refuses anything, and a board that sends no wave (one
    ready card, or an older server) simply draws no line."""
    plan = _obj(data.get("wave"))
    if not plan:
        return []
    safe = " ".join(_strs(plan.get("safe")))
    out = [f"  ▸ safe to dispatch together: {safe or 'nothing — every ready card clashes'}"]
    for row in _rows(plan.get("held")):
        why = _obj(row.get("why"))
        shared = _strs(why.get("files")) or _strs(why.get("terms"))
        verb = "shares" if why.get("files") else "names"
        out.append(f"    held: {row.get('id')} ({verb} {', '.join(shared)} with {why.get('with')})")
    return out


def _group(title: str, rows: object, now: float, extra: list[str] | None = None) -> list[str]:
    items = _rows(rows)
    if not items:
        return []
    out = [title]
    for row in items:
        who = row.get("holder") or row.get("assignee") or ""
        since = row.get("since")
        when = f" · {ago(now - float(since))}" if isinstance(since, (int, float)) else ""
        waiting = _strs(row.get("waiting_on"))
        tail = f" · waits on {', '.join(waiting)}" if waiting else ""
        quiet = row.get("quiet_for")
        if isinstance(quiet, (int, float)) and who:
            # STALLED says how long since its owner said ANYTHING. Not a guess
            # about why — a fact you can act on.
            tail += f" · quiet for {human(float(quiet))}"
        line = f"  {row.get('id')}  {row.get('title')}  {who}{when}{tail}".rstrip()
        if row.get("text"):
            # A CHANGES row carries the reviewer's words the way a MENTIONS row
            # carries the comment — the reason, not just the id.
            line += f"  “{_first_line(row.get('text'))}”"
        out.append(line)
    return [*out, *(extra or []), ""]


def _mentions(rows: object, now: float) -> list[str]:
    """Addressed to the reader, unanswered. The move is written into the title
    because there is no verb for it: writing anything on the card clears it."""
    items = _rows(rows)
    if not items:
        return []
    out = ["MENTIONS — addressed to you, not yet answered → answer on the card and it clears"]
    for row in items:
        ts = row.get("ts")
        when = f" · {ago(now - float(ts))}" if isinstance(ts, (int, float)) else ""
        head = f"  {row.get('id')}  {row.get('title')}  {row.get('by')}{when}".rstrip()
        out.append(f"{head}  “{_first_line(row.get('text'))}”")
    return [*out, ""]


def _first_line(text: object) -> str:
    """A board line, not the comment: the whole text is one taskops_card away,
    and a four-line note here would push the rest of the board off the screen."""
    line = str(text or "").strip().splitlines()
    head = line[0] if line else ""
    return f"{head[:97]}…" if len(head) > 98 or len(line) > 1 else head


def _hours(hours: dict[str, Any]) -> str:
    by_actor = _obj(hours.get("by_actor"))
    return " · ".join(f"{a} {_obj(v).get('human')}" for a, v in by_actor.items()) or "nothing yet"



_obj = as_object
_rows = as_rows
_strs = as_strings
