"""Values → markdown. The only renderer in the project.

v1 had thirty renderers because it also had a management CLI, a statusline and
a channel format. There is one consumer here — an agent reading a tool result —
so there is one shape.

Two rules:

* **Every result ends with the pulse line.** That is the whole of layer 3 of the
  context injection: refresh rides along with the call the agent already made.
* **Times are relative** (`3m ago`). Absolute clock formatting would need the
  timezone question answered in the renderer, and `test_architecture.py` keeps
  `strftime` out of everything but the calendar code for exactly that reason.
"""

from __future__ import annotations

from typing import Any

from .._json import as_rows, as_object, as_strings
from ..core.hours import human

BULLET = "◆"


def ago(seconds: float) -> str:
    """`human()` answers "—" under a minute, which reads as "no idea" in a
    timeline. Here that same gap is the truth: it just happened."""
    return f"{human(seconds)} ago" if seconds >= 60 else "just now"


def board(data: dict[str, Any], now: float) -> str:
    groups = _obj(data.get("groups"))
    out = [_header(data), ""]
    out += _group("MERGE — done, not integrated → taskops_merge", groups.get("merge"), now)
    out += _mentions(groups.get("mentions"), now)
    out += _group(
        "REVIEW — handed in, nobody checking → spawn a verifier (taskops_take review=true)",
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
    out += _group("TAKE — ready → taskops_assign", groups.get("take"), now)
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


def matches(data: dict[str, Any]) -> str:
    rows = _rows(data.get("matches"))
    if not rows:
        return f"nothing matches {data.get('query')!r}"
    return "\n".join(
        f"{m['id']}  {m['title']}  ({m['state']}{', ' + m['holder'] if m.get('holder') else ''})"
        for m in rows
    )


def plain(data: dict[str, Any]) -> str:
    """Whatever a write verb answered, plus the pulse. Never a bare 'ok'."""
    card = _obj(data.get("card"))
    lines: list[str] = []
    if card:
        lines.append(f"{card.get('id')} {card.get('title')} → {data.get('state', card['status'])}")
    stone = _obj(data.get("milestone"))
    if stone and not card:
        lines.append(f"{BULLET} {stone.get('title')} — {stone.get('status')}")
    for freed in _rows(data.get("freed")):
        lines.append(f"freed {freed['id']} {freed['title']} (worktree kept: {freed['worktree']})")
    for made in _rows(data.get("cards")):
        after = f"  after {', '.join(_strs(made.get('after')))}" if made.get("after") else ""
        lines.append(f"{made['id']}  {made['title']}{after}")
    for merged in ("into", "sha"):
        if data.get(merged):
            lines.append(f"{merged}: {data[merged]}")
    lines.append(pulse(data))
    return "\n".join(lines)


def pulse(data: dict[str, Any]) -> str:
    beat = _obj(data.get("pulse"))
    if not beat:
        return ""
    counts = _obj(beat.get("counts"))
    order = ("doing", "ready", "stalled", "blocked")
    parts = [f"{counts.get(k, 0)} {k}" for k in order if counts.get(k)]
    body = " · ".join(parts) or "nothing open"
    # The mention count is layer 3 doing what a hook was asked to do: it rides
    # on EVERY tool result, so being addressed is found within one call even
    # when nobody opened the board this turn. Nothing when there is nothing —
    # silence is what makes the ✉ mean something when it appears.
    waiting = beat.get("mentions")
    if isinstance(waiting, int) and waiting > 0:
        body += f" · ✉ {waiting} mention{'s' if waiting > 1 else ''} for you"
    return f"─ {BULLET} {beat.get('milestone', 'board')} · {body} ─"


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
    others = _rows(data.get("milestones"))
    if not others:
        return f'{BULLET} no open milestone — taskops_plan milestone="…" goal="…" opens one'
    names = " · ".join(f"{m['id']} {m['title']}" for m in others)
    return f"{BULLET} {len(others)} open milestones: {names} — pass milestone=<id> to focus one"


def _group(title: str, rows: object, now: float) -> list[str]:
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
    return [*out, ""]


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
