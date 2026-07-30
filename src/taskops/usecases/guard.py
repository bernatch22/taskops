"""The commit guard — where git-binding stops being a convention.

Called from a Claude Code `PreToolUse` hook on `git commit`. It answers one question:
may this commit happen, and with what message. The hook turns a refusal into a DENY
that the agent reads before the commit runs, so a task-less commit never exists rather
than being reported afterwards.

Why enforce at all, when a `post-commit` hook could just record whatever happens: a
commit with no task is a commit nobody can attribute at review time, and the moment
one is allowed the board stops being a complete picture of what changed. The refusal is
also cheap to satisfy — the fix is one `taskops_next` call, and the message says so.

What it deliberately does NOT do is judge the CONTENT. Whether the diff matches the
spec is a question for a model, and putting a model in the path of every commit would
add seconds and a failure mode to the most common action in the repository.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from ..engine import commitline, gitio
from ..storage import Store
from ._committer import committer
from ._project import heartbeat, project

__all__ = ["Verdict", "check_commit", "check_command"]


class Verdict:
    """Allowed or not, the message the commit should carry, and the command to run.

    A class rather than a tuple because a caller reads all four fields, and a bare
    `(bool, str, str, str)` at a call site is where two of them get swapped.
    """

    def __init__(self, *, allowed: bool, reason: str = "", message: str = "",
                 task: str = "", command: str = "") -> None:
        self.allowed = allowed
        self.reason = reason
        self.message = message
        self.task = task
        self.command = command
        """The rewritten shell command, or "" if there is nothing to change.

        Set only by `check_command`. It exists so the hook transport can hand back an
        `updatedInput` without knowing anything about git commit syntax — deciding what a
        command becomes is a decision, and decisions do not live in a transport.
        """


def check_command(start: Path | str, command: str, *, actor: str = "") -> Verdict | None:
    """Judge a whole `git commit` shell command. None if it is not one.

    The Claude Code matcher can only filter on the TOOL name, so the hook sees every Bash
    call and something has to recognise a commit. That something is here rather than in the
    transport, along with the rewrite: the transport passes through what it received and gets
    back what to do.
    """
    if not commitline.is_commit(command):
        return None
    verdict = check_commit(start, commitline.message_of(command), actor=actor)
    if verdict.allowed and verdict.message:
        verdict.command = commitline.with_message(command, verdict.message)
    return verdict


def check_commit(start: Path | str, message: str, *, actor: str = "") -> Verdict:
    """May this commit run, and what should its message say.

    The task is taken from the BRANCH, not from the caller's claims. An agent holding
    three leases and committing on one branch means exactly one of them, and asking it
    to also state which invites the one answer that is wrong.
    """
    with project(start) as store:
        branch = gitio.current_branch(store.root)
        who = committer(store, branch, actor)
        heartbeat(store, who)
        return _judge(store, who, branch, message)


def _judge(store: Store, who: str, branch: str, message: str) -> Verdict:
    on_branch = gitio.task_of_branch(branch)
    stated = gitio.task_of_message(message)
    if not on_branch:
        return _no_branch(store, who, branch, message, stated)
    if stated and stated != on_branch:
        return Verdict(allowed=False, task=on_branch,
                       reason=f"the message says {stated} but the branch is for "
                              f"{on_branch} — fix whichever is wrong, do not guess")
    if not store.leases.held_by(on_branch, who, now()):
        return Verdict(allowed=False, task=on_branch,
                       reason=f"{who} holds no live lease on {on_branch}. Claim it "
                              f"(taskops_next task={on_branch}) before committing — "
                              f"another agent may have taken it while you worked")
    return Verdict(allowed=True, task=on_branch,
                   message=gitio.add_trailer(message, on_branch))


def _no_branch(store: Store, who: str, branch: str, message: str,
               stated: str) -> Verdict:
    """Not on a `tk/...` branch. The one case with a genuinely useful suggestion.

    A trailer alone is accepted: a developer cherry-picking onto main, or committing a
    fix straight to a trunk-based repository, is doing something legitimate — and the
    trailer is what actually binds the commit, since a branch name does not survive a
    squash. Only the case with NEITHER is refused, and then the reason names the branch
    to switch to, because "claim a task first" without the command is a puzzle.
    """
    if stated and store.tasks.get(stated) is not None:
        return Verdict(allowed=True, task=stated, message=message)
    held = store.leases.of_actor(who, now())
    if not held:
        return Verdict(allowed=False,
                       reason=f"`{branch or 'HEAD'}` is not a task branch and {who} holds "
                              f"no task. If this work belongs to a card nobody made yet, "
                              f"taskops_capture title=… creates it AND claims it in one "
                              f"call; otherwise taskops_next picks one up. Then commit on "
                              f"the branch it names")
    suggestions = ", ".join(f"tk/{lease['task']}/…" for lease in held[:3])
    return Verdict(allowed=False,
                   reason=f"`{branch}` is not a task branch. You hold "
                          f"{len(held)} task(s) — switch to one of {suggestions} "
                          f"(taskops_ask gives the exact branch name)")
