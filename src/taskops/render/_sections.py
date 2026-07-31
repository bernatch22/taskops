"""The sections a task view is built from: the thread and the commits.

Split from `task` because that module decides the ORDER — which is its whole design, since an agent
reads top-down and may stop early — and these decide the CONTENT of two blocks that keep growing.
"""

from __future__ import annotations

from ..contracts import Event, TaskView
from ._text import ago

__all__ = ["thread_section", "commits_section"]


def thread_section(thread: list[Event]) -> list[str]:
    if not thread:
        return []
    lines = [f"**{e['actor']}** ({ago(e['ts'])}): {_said(e)}" for e in thread]
    return ["### Thread", "", "\n\n".join(lines), ""]


def _said(event: Event) -> str:
    """What this entry SAYS, by what its kind carries.

    Every kind used to be read through `body["text"]`, and a `handoff` carries no text — it
    carries `assigned_to`. So a card's thread opened with `**agent:uno/w2** (19m ago):` and
    nothing after the colon, which a reader on a live board took for a duplicated, half-lost
    message. Nothing was lost: a real fact was being rendered as an empty sentence.
    """
    if event["kind"] == "handoff":
        return f"→ assigned to {event['body'].get('assigned_to', 'somebody')}"
    return str(event["body"].get("text", "")) or "(nothing recorded)"


def commits_section(view: TaskView) -> list[str]:
    """Sha, subject, and the files each commit touched.

    The subject is the point. This printed bare twelve-character hashes for a while, which made a
    finished card look like it had recorded nothing — while the `commit` event underneath had carried
    the subject and the file list the whole time. The data was recorded, stored and replicated, and
    then dropped one layer before anybody could read it.

    Short shas still: the full forty characters is noise nobody reads, and anybody following one up
    pastes it into git, where twelve is unambiguous.
    """
    if not view["commits"]:
        return []
    lines: list[str] = []
    for commit in view["commits"]:
        lines.append(f"`{commit['sha'][:12]}` {commit['subject'] or '(no subject)'}")
        if commit["files"]:
            lines.append(f"  {_files(commit['files'])}")
    return [f"### Commits ({len(view['commits'])})", "", "\n".join(lines), ""]


def _files(files: list[str]) -> str:
    """The paths, truncated by COUNT rather than by characters.

    A commit that touched forty files would push the rest of the card off the screen, and the first
    few plus a count is what a reader actually uses.
    """
    shown = ", ".join(files[:4])
    return shown if len(files) <= 4 else f"{shown} +{len(files) - 4} more"
