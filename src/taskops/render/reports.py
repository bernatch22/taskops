"""The time-window reports: a standup, and who is live.

Both answer "what is going on" rather than "what should I do", and both are generated —
which is the claim worth protecting. A standup nobody typed cannot be out of date, and it
cannot flatter anybody either.
"""

from __future__ import annotations

from ..contracts import Fleet, Standup
from ._text import ago, bullet, table, truncate

__all__ = ["render_standup", "render_fleet"]


def render_standup(standup: Standup) -> str:
    """What changed in the window, per actor, then what needs a human."""
    if not standup["events"]:
        return "# standup\n\nNothing happened in this window."
    parts = [f"# standup — {len(standup['events'])} event(s), "
             f"{len(standup['actors'])} actor(s)", ""]
    for actor in standup["actors"]:
        mine = [e for e in standup["events"] if e["actor"] == actor]
        kinds = sorted({e["kind"] for e in mine})
        parts.append(f"**{actor}** — {len(mine)} event(s): {', '.join(kinds)}")
    parts += ["", f"Done: {len(standup['done'])} · in flight: "
                  f"{len(standup['in_flight'])} · blocked: {len(standup['blocked'])}"]
    return "\n".join(parts + _needs_a_human(standup))


def _needs_a_human(standup: Standup) -> list[str]:
    """Blocked tasks, called what they are.

    A standup's real job is surfacing the thing no agent can resolve. Listing blocked
    tasks under a neutral heading buries them among the counts; naming the ask is what
    makes a human read the section.
    """
    if not standup["blocked"]:
        return []
    return ["", "### Blocked — needs a human", "",
            bullet([f"{t['id']} — {truncate(t['title'], 60)}"
                    for t in standup["blocked"]])]


def render_fleet(fleet: Fleet) -> str:
    """Who is live, and who has gone quiet while still holding a claim.

    A silent member is SHOWN, never filtered out: a claim nobody is honouring is exactly
    the row somebody needs to act on, and hiding it is how a board loses its credibility.
    """
    if not fleet["members"]:
        return "# fleet\n\nNo live claims."
    rows = [[m["actor"], m["task"], "yes" if m["alive"] else "SILENT",
             ago(m["last_seen"]), truncate(m["doing"] or "—", 40)]
            for m in fleet["members"]]
    return "\n".join([f"# fleet — {len(fleet['members'])} live claim(s)", "",
                      table(["actor", "task", "alive", "last seen", "doing"], rows)])
