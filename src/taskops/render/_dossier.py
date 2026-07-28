"""One closed card, as the day's dossier prints it.

Split from `day` for the same reason `_sections` is split from `task`: that module decides the
ORDER of the report — which is its whole design, since a reader stops early — and this one
decides the CONTENT of the block that keeps growing.

TWO DENSITIES, ONE RENDERER. `detail="brief"` is what a terminal has always printed; `"full"`
is what `--write` puts on disk, and it adds the card's spec, every comment whole, and every
file of every commit. A second renderer for the file would drift from this one within a week,
and then a committed report and a printed one would disagree about what happened.
"""

from __future__ import annotations

from ..contracts import ClosedCard, CommitStat, Event
from ._text import STATUS_MARK, span, truncate
from ._verbatim import Detail, said_block, spec_block

__all__ = ["card_block"]

BRIEF_FILES = 4
"""Files named per commit in the terminal. `full` names them all: a written report is where
somebody looks up which files a card touched, and `+9 more` is exactly the answer they came
for being withheld."""


def card_block(card: ClosedCard, conversations: list[Event],
               detail: Detail = "brief") -> list[str]:
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
    lines += spec_block(task, detail)
    lines += [f"  {line}" for commit in card["commits"] for line in _commit(commit, detail)]
    return lines + said_block(mine, detail)


def _weight(commits: list[CommitStat]) -> str:
    """The card's total diff, or "" when git had nothing to say.

    Suppressed rather than printed as `+0 -0`: zeros here mean "git could not answer", and a
    card that really did ship nothing is already visible as zero commits.
    """
    adds = sum(c["additions"] for c in commits)
    dels = sum(c["deletions"] for c in commits)
    return f" · +{adds} -{dels}" if adds or dels else ""


def _commit(commit: CommitStat, detail: Detail) -> list[str]:
    """Sha, subject, size, then the files — the same shape `_sections.commits_section` uses,
    so a commit reads identically on a card and in a day's report."""
    head = (f"`{commit['sha'][:12]}` {commit['subject'] or '(no subject)'} "
            f"(+{commit['additions']} -{commit['deletions']})")
    files = commit["files"]
    if not files:
        return [head]
    if detail == "full":
        return [head, "  " + ", ".join(files)]
    extra = "" if len(files) <= BRIEF_FILES else f" +{len(files) - BRIEF_FILES} more"
    return [head, f"  {', '.join(files[:BRIEF_FILES])}{extra}"]
