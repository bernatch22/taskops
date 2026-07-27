"""What a tool call carries IN — the inputs, as types.

The MCP `inputSchema` is generated from these (`transports/mcp/schema.py`), so a
parameter is declared once and cannot exist on the wire without existing in the
dispatch, or the reverse — which is how a tool ends up advertising a flag nobody
reads.

The descriptions are part of the contract: they are the only thing the calling
agent sees before it chooses arguments. They describe the FIELD. When to reach for
the tool at all belongs to the tool's own description (`transports/mcp/tools.py`),
and saying it twice is two things to keep in step.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

__all__ = ["PlanParams", "NextParams", "UpdateParams", "AskParams", "ReportParams"]

Repo = Annotated[str, "path to the repository root; a path INSIDE it also works — "
                      "the root is found from .taskops"]

Actor = Annotated[str, "who is calling: `agent:<dev>/<name>` or `dev:<name>`. Omit "
                       "and it resolves from $TASKOPS_ACTOR or the git identity"]

Session = Annotated[str, "your Claude Code session id. It links this work to your "
                         "transcript on the live board"]

TaskId = Annotated[str, "a task id, e.g. tk-4f2a9c"]


class _Target(TypedDict):
    """Which repository. Every tool needs it; none of them guesses it."""

    repo_path: Repo


class _PlanRequired(_Target):
    tasks: Annotated[list[dict[str, Any]], "the tasks to create: a list of "
                     "{title, spec, priority?, labels?, files?, parent?, after?}. "
                     "`spec` is the brief a FRESH agent reads to do the work with "
                     "no other context — what done looks like, what must not "
                     "change, where to start. `after` lists dependencies, each an "
                     "existing task id or the 0-based INDEX of an earlier entry in "
                     "this same list, so a whole plan lands in one call. `files` is "
                     "the edit surface: name it and no two agents get the same file"]


class PlanParams(_PlanRequired, total=False):
    actor: Actor


class NextParams(_Target, total=False):
    actor: Actor
    session: Session
    labels: Annotated[str, "comma-separated labels to restrict the pick to"]
    task: Annotated[str, "claim THIS task rather than letting the scheduler "
                         "choose. Use it when a human named one — otherwise the "
                         "scheduler also avoids files another live agent is in"]


class _UpdateRequired(_Target):
    task: TaskId


class UpdateParams(_UpdateRequired, total=False):
    status: Annotated[Literal["in_progress", "blocked", "review", "done",
                              "released", "cancelled"],
                      "the new status. `released` returns the task to the queue "
                      "with your progress in `comment` — the honest move when out "
                      "of context. `done` needs a commit bound to this task"]
    comment: Annotated[str, "what happened, for the task's thread. Write the "
                            "decision and the surprise; the next agent and the "
                            "human reviewing at 9am read this and nothing else"]
    mentions: Annotated[str, "comma-separated actor ids to notify, e.g. "
                             "'agent:ana/api-1,dev:ana'. It reaches their inbox "
                             "and the live board — this is how you raise a shared "
                             "file with another developer's agent"]
    blocked_on: Annotated[str, "a task id that must finish first. Adds the "
                               "dependency AND sets you blocked, so a discovery "
                               "lands in the graph instead of a comment"]
    no_code: Annotated[bool, "declare that this task produces no commit "
                             "(research, a decision, docs elsewhere). Required to "
                             "close one, and recorded with your comment as the "
                             "justification"]


class AskParams(_Target, total=False):
    task: Annotated[str, "the task to read in full: spec, conversation, commits, "
                         "what blocks it, what it blocks, and which other tasks "
                         "touch the same files"]
    query: Annotated[str, "free text over titles, specs and comments, when you have "
                          "no id. Search once, then ask by id"]


class ReportParams(_Target, total=False):
    kind: Annotated[Literal["board", "standup", "burndown", "fleet"],
                    "board (default) every column; standup what changed in a "
                    "window, per actor; burndown open-vs-done by day; fleet which "
                    "agents are alive right now and on what"]
    actor: Annotated[str, "restrict a standup to one actor"]
    since: Annotated[str, "how far back a standup looks: '24h', '7d', '30m'"]
