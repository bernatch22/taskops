"""What an ACTION returns — a plan, a claim, an update.

Different from a board: the reader just did something and needs to know what happened and
what to do next, so every one of these ends with the consequence rather than a summary.
"""

from __future__ import annotations

from typing import cast

from ..contracts import Claim, EditResult, NextResult, PlanResult, Task, UpdateResult
from ._text import bullet, table, truncate
from ._unreviewed import ask_who_reviews
from .task import render_claim

__all__ = ["render_plan", "render_next", "render_capture", "render_update", "render_search", "render_edit"]


def render_plan(result: PlanResult) -> str:
    """The ids created, in the order the caller listed them.

    In ORDER because the caller has its own plan in mind and needs to map ids onto it;
    sorting by priority here would silently break that correspondence.
    """
    rows = [[task["id"], truncate(task["title"], 50), str(task["priority"]),
             ", ".join(d["task"] for d in result["deps"]
                       if d["blocks"] == task["id"]) or "—"]
            for task in result["created"]]
    said = [f"# planned {len(result['created'])} task(s)", "",
            table(["id", "title", "pri", "after"], rows), "", _readiness(result)]
    # The one question a plan leaves open, asked HERE because this is the return value the
    # planner reads with every id still in front of it. See `_unreviewed` for why not a guide.
    if asked := ask_who_reviews(result["created"]):
        said += ["", asked]
    return "\n".join(said)


def _readiness(result: PlanResult) -> str:
    """The one line worth reading twice.

    A plan where NOTHING is ready is almost always a mistake in the `after` references —
    a cycle, or an index off by one — and it is invisible until the first `next` returns
    nothing. Saying it here turns a puzzle twenty minutes later into a sentence now.
    """
    if result["unblocked"]:
        return f"{len(result['unblocked'])} ready to start now"
    return ("⚠ NOTHING is ready — every task waits on another. Check the `after` "
            "references for a cycle or an off-by-one index")


def render_next(result: NextResult) -> str:
    """A claim, or the reason there is none — never a bare "nothing available"."""
    if result["claim"] is not None:
        return render_claim(result["claim"])
    return "\n".join(["# nothing to claim", "", result["reason"], "",
                      f"_{result['ready']} ready · {result['working']} in flight · "
                      f"{result['blocked']} waiting_"])


def render_capture(result: dict[str, object]) -> str:
    """The new card, and — when it was claimed — the branch to commit on.

    The branch is the whole point of the reply. This tool is reached from a commit that was
    just refused, so the sentence the caller needs is not "created tk-x" but where to put the
    work it already did.
    """
    task = cast("Task", result["task"])
    head = f"# created {task['id']} — {truncate(task['title'], 60)}"
    if result.get("assigned"):
        return "\n".join([head, "", f"Assigned to {result['assigned']} — only they can claim "
                           f"it, and it is in their inbox."])
    if result.get("claim") is None:
        return "\n".join([head, "", "Not claimed. taskops_next task=" + task["id"] +
                           " when you start it."])
    return "\n".join([head, "", render_claim(cast("Claim", result["claim"]))])


def render_search(tasks: list[Task], query: str) -> str:
    """Search results, or a sentence saying nothing matched.

    A sentence rather than an empty list: an agent shown nothing cannot tell a failed search
    from a genuinely empty project, and it will retry the same query. Ends by naming the
    next call, because a list of ids without one invites the agent to guess at the tool.
    """
    if not tasks:
        return (f"nothing matches `{query}` — check the board with taskops_report, or plan "
                f"the work if it does not exist yet")
    lines = [f"- {t['id']} ({t['status']}) — {truncate(t['title'], 60)}" for t in tasks]
    return "\n".join([f"{len(tasks)} task(s) matching `{query}`:", "", *lines, "",
                      "Read one in full with taskops_ask task=<id>."])


def render_edit(result: EditResult) -> str:
    """Which fields moved, and the title as it now reads.

    Says nothing changed when nothing did, rather than printing a card that looks edited:
    the whole risk of an edit command is believing a rewrite landed when the value passed
    was the value already stored.
    """
    task = result["task"]
    if not result["changed"]:
        return f"{task['id']} — nothing changed; the values passed were already stored"
    return "\n".join([f"{task['id']} — edited {', '.join(result['changed'])}", "",
                      f"{truncate(task['title'], 70)}  (priority {task['priority']})"])


def render_update(result: UpdateResult) -> str:
    """The new status, and what it set free.

    The unblocked list is the point: an agent that just closed a task learns what it
    handed to the fleet, which is the difference between finishing work and finishing
    work somebody can pick up.
    """
    parts = [f"{result['task']['id']} → {result['task']['status']}"]
    if result["unblocked"]:
        parts += ["", f"Unblocked {len(result['unblocked'])} task(s):",
                  bullet([f"{t['id']} — {truncate(t['title'], 60)}"
                          for t in result["unblocked"]])]
    if result["notified"]:
        parts += ["", f"Notified: {', '.join(result['notified'])}"]
    if result["task"]["status"] == "review" and not result.get("routed_to"):
        # The orphan case, said out loud. A handover that routed to nobody looked EXACTLY like
        # a handover that worked — same status, same silence — and a card sat in review that
        # no message anywhere mentioned. "Nobody is here" is a fact the author can act on:
        # keep the session open, or tell a person.
        parts += ["", "Nobody else is connected, so this review was routed to NOBODY. It stays "
                      "open to whoever shows up and it is in every eligible dev's sweep — but "
                      "until somebody opens a session, it is waiting on no one. Do not close "
                      "it yourself; say so if that matters."]
    if result.get("routed_to"):
        # Said to the AUTHOR, and said as a prohibition. "Routed to dos" alone reads as
        # bookkeeping; a session that has just watched its own worker finish needs the
        # sentence that stops it spawning a verifier out of reflex.
        parts += ["", f"This review was routed to {result['routed_to']} — it is in their "
                      f"sweep and in nobody else's. Do NOT verify it and do not spawn a "
                      f"verifier for it: `reviewer: peer` is per DEVELOPER, so another agent "
                      f"of yours would be refused at the close. Your part is done."]
    return "\n".join(parts)
