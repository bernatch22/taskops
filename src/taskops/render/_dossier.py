"""One closed card, as the day's dossier prints it.

Split from `day` for the same reason `_sections` is split from `task`: that module decides the
ORDER of the report — which is its whole design, since a reader stops early — and this one
decides the CONTENT of the block that keeps growing.
"""

from __future__ import annotations

from ..contracts import ClosedCard, CommitStat, Event
from ._text import STATUS_MARK, span, truncate

__all__ = ["card_block"]


def card_block(card: ClosedCard, conversations: list[Event]) -> list[str]:
    """The card, who closed it, how long it was held, what it shipped, and what was said.

    The duration is claim -> done and is printed even when it is minutes, because a card
    closed four minutes after being claimed is the single most useful thing this report can
    surface: it is either a trivial fix or an agent that closed something it never did.
    """
    task = card["task"]
    held = span(max(0.0, card["done_ts"] - card["claimed_ts"]))
    mine = [e for e in conversations if e["task"] == task["id"]]
    lines = [f"{STATUS_MARK['done']} **{task['id']}** — {truncate(task['title'], 70)}",
             f"  {card['actor']} · held {held} · "
             f"{len(card['commits'])} commit(s){_weight(card['commits'])}"]
    lines += [f"  {line}" for commit in card["commits"] for line in _commit(commit)]
    return lines + _said(mine)


def _weight(commits: list[CommitStat]) -> str:
    """The card's total diff, or "" when git had nothing to say.

    Suppressed rather than printed as `+0 -0`: zeros here mean "git could not answer", and a
    card that really did ship nothing is already visible as zero commits.
    """
    adds = sum(c["additions"] for c in commits)
    dels = sum(c["deletions"] for c in commits)
    return f" · +{adds} -{dels}" if adds or dels else ""


def _commit(commit: CommitStat) -> list[str]:
    """Sha, subject, size, then the files — the same shape `_sections.commits_section` uses,
    so a commit reads identically on a card and in a day's report."""
    head = (f"`{commit['sha'][:12]}` {commit['subject'] or '(no subject)'} "
            f"(+{commit['additions']} -{commit['deletions']})")
    if not commit["files"]:
        return [head]
    shown = ", ".join(commit["files"][:4])
    extra = "" if len(commit["files"]) <= 4 else f" +{len(commit['files']) - 4} more"
    return [head, f"  {shown}{extra}"]


def _said(mine: list[Event]) -> list[str]:
    """The count, plus the LAST thing said on the card.

    The last one and not the first: on a closed card that is the hand-off note, which is what
    somebody reading the day after actually needs.
    """
    if not mine:
        return []
    text = str(mine[-1]["body"].get("text", ""))
    return [f"  {len(mine)} comment(s) · last: {truncate(text, 120)}"]
