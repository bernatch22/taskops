"""What an agent reads to decide whether to call `taskops_context` or `taskops_milestone`.

Split from `_fields` on that module's line budget, and the split is by SUBJECT rather than by
size: those describe a CARD — its spec, its status, its evidence — and these describe what stands
around one. A tool description is the only documentation an agent ever reads, so the two sets are
edited by different questions and belong apart.
"""

from __future__ import annotations

__all__ = ["CONTEXT_TASK", "CONTEXT_MILESTONE", "LEVEL", "STATE", "SCOPE", "RETIRE",
           "PLAN_MILESTONE",
           "MS_READ", "MS_CREATE", "MS_GOAL", "MS_TITLE", "MS_HORIZON", "MS_PLANNED",
           "MS_START", "MS_UPDATE",
           "MS_REVIEW", "MS_DONE", "MS_REJECT", "MS_CANCEL", "MS_NOTE", "MS_CARRY", "MS_INTO"]

CONTEXT_TASK = ("a task id: the slice that applies to THAT card — the project's permanent rules, "
                "its own MILESTONE's rules, and the decisions and notes that are chapter-wide or "
                "match its labels or files. Omit for the whole project's")
CONTEXT_MILESTONE = ("a milestone id: the facts of THAT chapter, including a closed one. Omit for "
                     "what is in force now")
LEVEL = ("`project` makes the fact PERMANENT — it outlives every milestone. Omit and it belongs to "
         "the chapter in force and leaves every slice when that chapter is reached, which is what "
         "keeps a worker's context from growing with the year. `note` is always the chapter's")
STATE = ("state a standing fact instead of reading. `rule` (never broken) and `decision` (settled, "
         "so it is not re-litigated) are the PROJECT's or the chapter's — a worker is REFUSED "
         "both, because they are what it is judged against. `note` is standing and neither. "
         "`objective` is YOUR OWN, inside the chapter, and an agent may set it: it is its own "
         "developer's. Needs `text`.")
SCOPE = ("comma-separated labels a DECISION applies to; omit for project-wide. Scope is what "
         "keeps the slice a worker reads from growing until nobody follows it.")
RETIRE = ("a standing fact's id, or the first eight characters of it. It leaves `show` and stays "
          "in the log, because an append-only log has no eraser.")
MINE = ("file it under YOU rather than the project. A worker then reads the project's facts and "
        "its own developer's and nobody else's, which is what keeps a slice from growing with "
        "the team. Usual for an objective: the team's north and your week are both true.")

# ---- taskops_milestone. A chapter is the only thing on a board that ENDS.

MS_READ = ("a milestone id: that chapter with its facts AND ITS CARDS. Omit and you get every "
           "ACTIVE chapter with its counts, plus what is planned next — which is what an "
           "orchestrator needs, because it chooses which one to plan into")
MS_CREATE = ("open a new chapter with this TITLE — three or five words somebody would recognise "
             "(\"the importer\", \"invoicing\"). Cards attach to a chapter and `plan` refuses "
             "without one, so this is the first call on a fresh board. Say what done means in `goal`")
MS_GOAL = ("what DONE means for this chapter, and what is out of scope. Prose, as long as it needs "
           "to be: every worker under this chapter reads it, and it is the difference between a "
           "name and a thing anybody can tell is finished")
MS_TITLE = "with `update`: rename it. Absent leaves the name alone rather than blanking it"
MS_HORIZON = "when it is meant to be reached, `YYYY-MM-DD`. Advisory: nothing expires on it"
MS_PLANNED = ("write it down WITHOUT starting it. That is the todo-list — visible, carrying no "
              "cards and no facts, so it cannot be mistaken for work in progress")
MS_START = "a planned chapter's id: it becomes active. Several may be active at once"
MS_UPDATE = ("a chapter's id to re-word: pass `title`, `goal` and/or `horizon`. What you omit is "
             "left alone, so writing a goal does not erase the name")
MS_REVIEW = ("a chapter's id you believe is finished. It stays ACTIVE and a person verifies — "
             "nothing is archived on your word. Say what shows it in `m`")
MS_DONE = ("verify a chapter as reached. REFUSED to an agent: `done` on a card already needs "
           "somebody who is not its author, and this is that rule one level up")
MS_REJECT = "send a reviewed chapter back in force. REFUSED to an agent, and `m` is required"
MS_CANCEL = "abandon a chapter — it will not be done. REFUSED to an agent; `m` says why"
MS_NOTE = "the message on the move: what is finished, what is missing, or why it stopped"
MS_CARRY = ("comma-separated fact ids of THIS chapter to keep alive in another one, for a "
            "chapter-level fact that turns out to matter beyond it")
MS_INTO = ("which active chapter `carry` moves those facts into. Needed when more than one is "
           "active: guessing which chapter inherits a rule is guessing what the rule is about")

PLAN_MILESTONE = ("which chapter these cards belong to. Needed when more than one is active — a "
                  "card in the wrong chapter is judged against somebody else's rules and nothing "
                  "says so, so this is refused rather than guessed. Omit with exactly one active")
