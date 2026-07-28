"""What one backfill run did — the answer `report sweep` renders and the MCP returns.

A sweep is the one command whose usual and correct outcome is "nothing", so the result has to
carry the REASON as prose. A run that narrated nothing because every day is already written up
and a run that narrated nothing because the model is unreachable are the same empty list, and
telling them apart from a count alone is impossible — which is how a broken guardrail goes
unnoticed for a week.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Skipped", "SweepResult"]


class Skipped(TypedDict):
    label: str
    """The report label that was NOT narrated — a date, or `push` for the round trip itself."""

    why: str
    """A sentence, not a code. It is read by a person who ran the command once and will not
    read the source to find out what `locked` meant."""


class SweepResult(TypedDict):
    narrated: list[str]
    """The labels this run wrote prose for, oldest first. Empty on the second run of the day,
    which is the idempotence showing through rather than a failure."""

    skipped: list[Skipped]
    pushed: int
    """Reports uploaded by the ONE push at the end. Zero when `--push` was not asked for, when
    nothing was narrated, or when the project has no remote — the `skipped` row says which."""

    truncated: int
    """Eligible days the `--limit` left for the next run. Reported because a silent cap reads
    exactly like 'everything is written up', which is the one thing it must never be mistaken
    for on a repository with a year of history."""
