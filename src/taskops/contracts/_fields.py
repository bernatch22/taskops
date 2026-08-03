"""The field descriptions, and the aliases shared across tool contracts.

Prose in a data structure, so it is split out for the same reason `transports/mcp/_descriptions` is:
reviewing a change to which fields a tool takes should not mean re-reading sixty lines of unchanged
text. The strings themselves are the contract — they are the only thing a calling agent reads before
it chooses arguments.
"""

from __future__ import annotations

from typing import Annotated

__all__ = ["Repo", "Actor", "Session", "TaskId", "TASKS", "DRY_RUN", "STATUS", "COMMENT",
           "TITLE", "SPEC", "FILES", "ACCEPTANCE", "PRIORITY", "CLAIM_IT", "ASSIGN",
           "MENTIONS", "BLOCKED_ON", "NO_CODE", "LABELS", "CLAIM_ONE", "ASK_TASK",
           "ASK_QUERY", "DISPATCH_TASKS", "DISPATCH_COUNT", "PREFIX",
           "RECOVER_FORCE", "RECOVER_GRACE", "REPORT_KIND", "REPORT_ACTOR", "SINCE", "DATE",
           "EVIDENCE", "NO_EVIDENCE"]

Repo = Annotated[str, "path to the repository root; a path INSIDE it also works — "
                      "the root is found from .taskops"]

Actor = Annotated[str, "who is calling: `agent:<dev>/<name>` or `dev:<name>`. Omit "
                       "and it resolves from $TASKOPS_ACTOR or the git identity"]

Session = Annotated[str, "your Claude Code session id. It links this work to your "
                         "transcript on the live board"]

TaskId = Annotated[str, "a task id, e.g. tk-4f2a9c"]



TASKS = ("the tasks to create: a list of {title, spec, priority?, labels?, files?, parent?, "
         "after?, blocks?, acceptance?, assignee?, reviewer?}. `reviewer` is who may CLOSE the "
         "card — `human` (or `dev:<name>`) when a person must read the diff and no agent may "
         "close it, or the name of a registered specialist to spawn; omit it and the project's "
         "own default applies. `spec` is the brief a FRESH agent reads to do the work "
         "with no other context — what done looks like, what must not change, where to start. "
         "`parent` is the epic this card is PART OF — an existing id, or the 0-based INDEX of an "
         "earlier entry in this same list, so a whole tree lands in one call. An epic cannot "
         "be closed while any child of it is open, which is what makes a checklist mean "
         "something. `after` is the other question — what must finish BEFORE this card — and "
         "takes the same two forms: an existing id or the 0-based INDEX of an earlier entry. `blocks` is the inverse: existing cards "
         "that must wait for this one — that is how an agent mid-task creates the prerequisite it "
         "just discovered and makes its own task wait, in one call. `files` is the edit surface: "
         "name it and no two agents get the same file. `acceptance` is the list of EARS criteria "
         "this card is accepted against — one per line, \"WHEN <trigger> THE SYSTEM SHALL "
         "<response>\" — and each one should read as a test somebody could write")

STATUS = ("the new status. `released` returns the task to the queue with your progress in "
          "`comment` — the honest move when out of context. `done` needs a commit on this task")

COMMENT = ("what happened, for the task's thread. Write the decision and the surprise; the next "
           "agent and the human reviewing at 9am read this and nothing else")

MENTIONS = ("comma-separated actor ids to notify, e.g. 'agent:ana/api-1,dev:ana'. It reaches "
            "their inbox and the live board — this is how you raise a shared file with another "
            "developer's agent")

BLOCKED_ON = ("a task id that must finish first. Adds the dependency AND sets you blocked, so a "
              "discovery lands in the graph instead of a comment")

NO_CODE = ("declare that this task produces no commit (research, a decision, docs elsewhere). "
           "Required to close one, and recorded with your comment as the justification")

EVIDENCE = ("what proves the acceptance criteria were met: name the criterion and the test, "
            "command or run that demonstrates it. Required to close a card that HAS criteria, "
            "and it is what a verifier reads before it tries to prove you wrong")

NO_EVIDENCE = ("close a card with criteria WITHOUT proving them, giving the reason here — the "
               "criterion turned out to be wrong, or the work moved. The reason is written into "
               "the done event, so this is an argued exemption and not a way around the rule")


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

REPORT_KIND = ("board (default) every column; standup what changed in a window, per actor; "
               "day the full dossier of ONE calendar day — every card closed with its "
               "commits and their diff sizes, what is still in flight, and the conversation; "
               "range the same dossier over MANY days, grouped by day (pass `last`, or "
               "`from`/`to`, and omit both for the WHOLE project)")

REPORT_ACTOR = "restrict a standup to one actor"

SINCE = "how far back a standup looks: '24h', '7d', '30m'"

LAST = ("with kind=range: how far back from `to`, e.g. '7d', '2w', '1m'. Inclusive of both "
        "ends — '7d' is seven days of work. Leave `last`, `from` and `to` all empty and a "
        "range covers the project from its first event, which is what to ask for when "
        "somebody wants everything evaluated and not just one day")

FROM_DATE = ("with kind=range: the first day, 'YYYY-MM-DD'. Use it instead of `last` when the "
             "window is a specific span rather than a distance back from today")

TO_DATE = ("with kind=range: the last day, INCLUSIVE, 'YYYY-MM-DD'. Defaults to today")

DATE = ("which day a `day` report covers: 'today' (default), 'yesterday', or a date like "
        "2026-07-28. It is a CALENDAR day in local time, not a rolling window — ask for the "
        "same date tomorrow and you get the same report")

DRY_RUN = ("show which cards WOULD get a worker and stop — nothing assigned, nothing launched. "
           "Worth doing first when you are about to spend several models on a plan you just wrote")

RECOVER_FORCE = ("release cards even from workers that are STILL reporting. For a fleet that is "
                 "alive and WRONG — chasing a bad spec, say. Without it, only workers that have "
                 "gone silent are touched")

RECOVER_GRACE = ("seconds of silence before a worker counts as gone. Defaults to the same grace "
                 "the fleet view uses to print SILENT, so what you see on the board is exactly "
                 "what this acts on")

TITLE = "one line saying what the work is — this becomes the card"
SPEC = "what DONE looks like, in enough detail that another agent could finish it"
FILES = "comma-separated paths this will touch, so collisions can be warned about"
ACCEPTANCE = ("acceptance criteria, one per line, ideally EARS: "
              "`WHEN <trigger> THE SYSTEM SHALL <response>`. These are what `done` is checked against")
PRIORITY = "0 urgent … 3 whenever (default 2)"
CLAIM_IT = ("claim it immediately (default true) — pass false only when recording work for LATER "
            "that you are not about to start")
ASSIGN = ("give it to another actor (`agent:dev/name` or `dev:name`) instead of claiming it: "
          "it lands in their inbox and stays pickable")



TEXT = "the fact itself, with its reason — one sentence a worker can act on"
