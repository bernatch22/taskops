"""The field descriptions, and the aliases shared across tool contracts.

Prose in a data structure, so it is split out for the same reason `transports/mcp/_descriptions` is:
reviewing a change to which fields a tool takes should not mean re-reading sixty lines of unchanged
text. The strings themselves are the contract — they are the only thing a calling agent reads before
it chooses arguments.
"""

from __future__ import annotations

from typing import Annotated

__all__ = ["Repo", "Actor", "Session", "TaskId", "TASKS", "DRY_RUN", "STATUS", "COMMENT", "MENTIONS",
           "BLOCKED_ON", "NO_CODE", "LABELS", "CLAIM_ONE", "ASK_TASK", "ASK_QUERY",
           "DISPATCH_TASKS", "DISPATCH_COUNT", "PREFIX", "MODEL", "REPORT_KIND",
           "REPORT_ACTOR", "SINCE"]

Repo = Annotated[str, "path to the repository root; a path INSIDE it also works — "
                      "the root is found from .taskops"]

Actor = Annotated[str, "who is calling: `agent:<dev>/<name>` or `dev:<name>`. Omit "
                       "and it resolves from $TASKOPS_ACTOR or the git identity"]

Session = Annotated[str, "your Claude Code session id. It links this work to your "
                         "transcript on the live board"]

TaskId = Annotated[str, "a task id, e.g. tk-4f2a9c"]



TASKS = ("the tasks to create: a list of {title, spec, priority?, labels?, files?, parent?, "
         "after?, blocks?, assignee?}. `spec` is the brief a FRESH agent reads to do the work "
         "with no other context — what done looks like, what must not change, where to start. "
         "`after` lists what must finish BEFORE this card, each an existing id or the 0-based "
         "INDEX of an earlier entry in this same list. `blocks` is the inverse: existing cards "
         "that must wait for this one — that is how an agent mid-task creates the prerequisite it "
         "just discovered and makes its own task wait, in one call. `files` is the edit surface: "
         "name it and no two agents get the same file")

STATUS = ("the new status. `released` returns the task to the queue with your progress in "
          "`comment` — the honest move when out of context. `done` needs a commit bound to "
          "this task")

COMMENT = ("what happened, for the task's thread. Write the decision and the surprise; the next "
           "agent and the human reviewing at 9am read this and nothing else")

MENTIONS = ("comma-separated actor ids to notify, e.g. 'agent:ana/api-1,dev:ana'. It reaches "
            "their inbox and the live board — this is how you raise a shared file with another "
            "developer's agent")

BLOCKED_ON = ("a task id that must finish first. Adds the dependency AND sets you blocked, so a "
              "discovery lands in the graph instead of a comment")

NO_CODE = ("declare that this task produces no commit (research, a decision, docs elsewhere). "
           "Required to close one, and recorded with your comment as the justification")

LABELS = "comma-separated labels to restrict the pick to"

CLAIM_ONE = ("claim THIS task rather than letting the scheduler choose. Use it when a human named "
             "one — otherwise the scheduler also avoids files another live agent is in")

ASK_TASK = ("the task to read in full: spec, conversation, commits, what blocks it, what it "
            "blocks, and which other tasks touch the same files")

ASK_QUERY = "free text over titles, specs and comments, when you have no id. Search once, then ask by id"

DISPATCH_TASKS = ("comma-separated task ids to dispatch, one worker each. Omit to let the "
                  "scheduler pick the best `count` ready cards")

DISPATCH_COUNT = ("how many workers to launch when you did not name tasks (default 3, ceiling "
                  "12). Every worker is a real Claude Code process, so ask for what you need "
                  "rather than for everything")

PREFIX = ("names the workers `agent:<you>/<prefix>1..n` (default 'w'), so a fleet view reads as "
          "api1, api2 instead of three hashes")

MODEL = ("model for the workers, e.g. claude-sonnet-5. Omit for their default — a cheap model is "
         "often right for mechanical cards")

REPORT_KIND = ("board (default) every column; standup what changed in a window, per actor; "
               "burndown open-vs-done by day; fleet which agents are alive right now and on what")

REPORT_ACTOR = "restrict a standup to one actor"

SINCE = "how far back a standup looks: '24h', '7d', '30m'"

DRY_RUN = ("show which cards WOULD get a worker and stop — nothing assigned, nothing launched. "
           "Worth doing first when you are about to spend several models on a plan you just wrote")
