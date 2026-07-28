"""Structured errors: a small taxonomy every boundary maps ONCE.

Errors are data, not strings — a stable machine `code` plus an `http_status` — so
each transport translates the TYPE at one catch site instead of matching message
text. Each subclass also inherits the builtin a caller would plausibly already be
catching (the `json.JSONDecodeError(ValueError)` trick). Every message names what
to DO: the reader is an agent mid-turn, and this is all it gets to act on.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "TaskopsError",
    "NotInitialized",
    "NoSuchTask",
    "IllegalTransition",
    "LeaseHeld",
    "NoLease",
    "GuardFailed",
    "BadRequest",
    "AlreadyWritten",
    "AlreadyNarrating",
    "NarrationFailed",
]


class TaskopsError(Exception):
    """Root. `except TaskopsError` catches everything the engine raises."""

    code = "error"
    http_status = 500


class NotInitialized(TaskopsError, FileNotFoundError):
    """No `.taskops/` at or above the given path."""

    code = "not_initialized"
    http_status = 404

    @classmethod
    def at(cls, path: str | Path) -> "NotInitialized":
        return cls(f"no taskops project at or above {path} — run `taskops init` in the "
                   f"repository root")


class NoSuchTask(TaskopsError, KeyError):
    """A task id nobody created — usually a hallucinated or a stale one."""

    code = "no_such_task"
    http_status = 404

    @classmethod
    def named(cls, task: str) -> "NoSuchTask":
        return cls(f"no task {task} — list what exists with `taskops report board`")


class IllegalTransition(TaskopsError, ValueError):
    """A status move the machine does not allow."""

    code = "illegal_transition"
    http_status = 409

    @classmethod
    def between(
        cls, *, task: str, old: str, new: str, allowed: tuple[str, ...]
    ) -> "IllegalTransition":
        legal = ", ".join(allowed) if allowed else "nothing — it is terminal"
        return cls(f"{task} is {old} and cannot go to {new}; from {old} it can go to {legal}")


class LeaseHeld(TaskopsError, RuntimeError):
    """Somebody else is on it and their lease has not expired."""

    code = "lease_held"
    http_status = 409

    @classmethod
    def by(cls, *, task: str, actor: str, seconds: int) -> "LeaseHeld":
        return cls(f"{task} is claimed by {actor} for another {seconds}s — "
                   f"pick another task, or message them on it")


class NoLease(TaskopsError, RuntimeError):
    """Working on a task nobody claimed. Its own type, not a GuardFailed,
    because it has ONE fix the agent can apply unaided — which the message is."""

    code = "no_lease"
    http_status = 409

    @classmethod
    def on(cls, *, task: str, actor: str) -> "NoLease":
        return cls(f"{actor} holds no live lease on {task} — claim it with "
                   f"taskops_next, or `taskops claim {task}`")


class GuardFailed(TaskopsError, ValueError):
    """A transition the machine allows but the project's rules refuse. Separate
    from IllegalTransition: that one is "the arrow does not exist", this one is
    "you have not earned it yet" — and only this one is fixable by doing work."""

    code = "guard_failed"
    http_status = 400


class BadRequest(TaskopsError, ValueError):
    """An argument that cannot mean anything. Raised at the edges, not inside."""

    code = "bad_request"
    http_status = 400


class AlreadyWritten(TaskopsError, FileExistsError):
    """A generated file that exists and would be OVERWRITTEN. 409, never 500.

    A written report is something somebody may have already read, cited, or narrated by
    hand; silently regenerating it would rewrite history under them. Refusing and naming
    `--force` leaves the choice with the person who knows whether the old one mattered.
    """

    code = "already_written"
    http_status = 409


class AlreadyNarrating(TaskopsError, RuntimeError):
    """A narration of that report is already running IN THIS PROCESS. 409.

    Two models writing the same file is not a slow path, it is corruption: both hold the
    dossier they read at the start and each rewrites the whole file when it flushes, so
    whichever finishes last silently erases the other. Refusing the second is the only
    outcome that leaves a readable report — and the first one is still streaming, so the
    person who clicked twice is already looking at what they asked for.
    """

    code = "already_narrating"
    http_status = 409


class NarrationFailed(TaskopsError, RuntimeError):
    """The `claude` CLI could not write the narration. 502: an upstream did not answer.

    Its own type because the fix is never in taskops — the binary is missing, the session is
    not logged in, or the model refused — and the message has to say which. Everything else
    about the report still worked: the dossier is on disk either way, so this never costs the
    facts, only the prose.
    """

    code = "narration_failed"
    http_status = 502
