"""What a tool call returns — one record, and the one way a failure is shaped.

The reader is a model, so this matters more than usual: `isError` tells it not to trust the
text as an answer, and the machine code inside the text tells it what to do about it. A
failure each call site formats its own way is a failure an agent cannot parse.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..._errors import TaskopsError

__all__ = ["Answer", "answer", "failure", "from_engine"]


@dataclass(frozen=True, slots=True)
class Answer:
    """Text for the agent, and whether it is an answer or an apology."""

    text: str
    failed: bool = False


def answer(text: str) -> Answer:
    return Answer(text=text)


def failure(message: str, code: str = "error") -> Answer:
    """The machine-readable half travels IN the text.

    MCP has no error field beyond the `isError` flag, and a code the agent can match on is
    what turns "it failed" into "claim the task first".
    """
    return Answer(text=f"error ({code}): {message}", failed=True)


def from_engine(err: TaskopsError) -> Answer:
    """A typed failure, translated ONCE.

    The taxonomy carries its own stable code, so a new error type reaches this surface
    correctly the day it is added rather than the day somebody remembers to map it.
    """
    return failure(str(err), err.code)
