"""The tool descriptions. Prose, not logic — which is why they are not in `tools.py`.

Same split as `storage/_ddl`: that module is the SQL, this one is the text, and in both
cases the point is that reviewing a change to the assembly is not also re-reading sixty
lines of unchanged content.

These strings are the single highest-leverage text in the package. They are what an agent
reads before it decides which tool to call and what to put in it, and every sentence here
earns its place by preventing a mistake seen in a real session — an agent coding before
claiming, closing a task with nothing to show, or discovering a shared file at merge time.
"""

from __future__ import annotations

__all__ = ["NEXT", "UPDATE", "ASK", "PLAN", "REPORT", "DISPATCH"]

NEXT = (
    "CLAIM the next piece of work — the call to make when you are ready to code, and the "
    "first call in any session where you do not already hold a task. Returns the task's "
    "full spec, the exact branch to create, the conversation so far, the commits already "
    "on it, and a WARNING listing any other agent editing the same files. The claim is "
    "atomic and leased: no two agents can hold one task, and if your process dies the "
    "lease expires and the work returns to the queue instead of sitting there looking "
    "claimed forever. Every taskops call you make afterwards renews it, so a long task "
    "never expires under you. When nothing is available it says WHY — everything blocked, "
    "everything taken, or the project is finished — which is usually something you can "
    "act on."
)

UPDATE = (
    "Record progress, hand work back, close a task, or MESSAGE another developer's agent — "
    "one call, because they are one thought. `comment` is what the next agent and the "
    "human reviewing at 9am will read, so write the decision and the surprise rather than "
    "a restatement of the title. `mentions` reaches other actors' inboxes: they see it "
    "within one tool call of their own, and it appears live on the board — this is how you "
    "raise a shared file before you both edit it. `status=released` returns the task to "
    "the queue with your progress attached, which is the honest move when you are out of "
    "context or out of depth. `status=done` requires a commit bound to this task (pass "
    "no_code with a comment if the task genuinely produced none) — that guard is the "
    "reason the board can be trusted."
)

ASK = (
    "READ a task in full: the spec, the whole conversation, the commits, what blocks it, "
    "what it is blocking, its subtasks, and which OTHER tasks touch the same files. Use it "
    "before starting on a task somebody handed you by id, and before editing a file you "
    "suspect is contested — the neighbours list is the one thing that prevents a merge "
    "conflict rather than reporting it afterwards. With `query` instead of `task` it "
    "searches titles and specs, for when you know what the work is called but not its id."
)

PLAN = (
    "Turn a decomposition into a persistent task graph in ONE call — tasks, their "
    "parent/child tree, and the dependencies between them. YOU do the decomposition; this "
    "makes it durable, ordered, and visible to every other agent and developer on the "
    "project. `after` accepts the 0-based index of an earlier task in the same batch, so a "
    "whole plan lands atomically instead of needing a second pass that a context limit can "
    "cut short. Write each `spec` for a FRESH agent with none of your context: what done "
    "looks like, what must not change, which files to start from. Name `files` and the "
    "scheduler will never hand two agents the same one."
)

REPORT = (
    "The generated view: `board` (every column, who holds what), `standup` (what changed "
    "in a window, per actor, and what needs a human), `burndown` (open versus done by "
    "day), or `fleet` (which agents are alive right now, on what task, touching what "
    "file). Nobody writes these by hand, so they cannot be out of date — use `standup` "
    "when a human asks how it is going, and `fleet` when you need to know whether another "
    "agent is still working or has gone quiet holding a claim."
)

DISPATCH = (
    "LAUNCH worker agents — one real Claude Code process per card, each in its own git worktree, "
    "each already assigned the card it was started for. This is how you get parallel work: you plan, "
    "then you dispatch, and the workers claim, code, commit and close on their own while you carry on. "
    "Use it right after `taskops_plan` when the cards are independent, and use `count` to say how "
    "many — every worker costs a model, so three is the default and twelve is the ceiling. Assignment "
    "happens BEFORE launch, so a dispatched worker cannot wander off and claim somebody else's card, "
    "and no other agent will be offered one that is assigned. Workers are detached: they outlive your "
    "session, their output is on disk, and `taskops_report fleet` shows what they are doing. If one "
    "dies, its lease expires and the card returns to the queue — nothing is stranded."
)
