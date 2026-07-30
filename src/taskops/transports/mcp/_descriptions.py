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

__all__ = ["NEXT", "UPDATE", "ASK", "PLAN", "REPORT", "DISPATCH", "RECOVER", "CONTEXT"]

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
    "Record progress, hand work back, finish a task (status=review — another actor closes it; done on your own review is refused), or MESSAGE another developer's agent — "
    "one call, because they are one thought. `comment` is what the next agent and the "
    "human reviewing at 9am will read, so write the decision and the surprise rather than "
    "a restatement of the title. `mentions` reaches other actors' inboxes: they see it "
    "within one tool call of their own, and it appears live on the board — this is how you "
    "raise a shared file before you both edit it. `status=released` returns the task to "
    "the queue with your progress attached, which is the honest move when you are out of "
    "context or out of depth. `status=done` requires a commit bound to this task (pass "
    "no_code with a comment if the task genuinely produced none) — that guard is the "
    "reason the board can be trusted. If the card carries acceptance criteria it also needs "
    "evidence: say which criteria were met and what proves each one — a test name, a command, "
    "a run — or pass no_evidence with the reason they no longer apply, which is recorded on "
    "the card for whoever reviews it."
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
    "The generated view: `attention` — START AN ORCHESTRATOR TURN WITH THIS. It is the one "
    "read that says what the board is WAITING FOR and what to do about each card: reviews "
    "nobody verified, cards assigned to a worker that is not running, ready work to dispatch, "
    "and the two kinds only a person can fix. It writes nothing and is safe to run in a loop. "
    "Or: `board` (every column, who holds what), `standup` (what changed "
    "in a window, per actor, and what needs a human), or `day` (ONE calendar day in full — "
    "every card closed with who closed it, how long it was held, each of its commits with "
    "the size of its diff, what is still in flight or blocked, the whole conversation, and "
    "a roll-up per actor), or `range` (that same dossier over MANY days, its closed cards "
    "grouped by day, newest first). Nobody writes these by hand, so they cannot be out of "
    "date — use `standup` when a human asks how it is going, `day` with date='yesterday' "
    "when they ask what got done, and `range` when they ask about the project rather than "
    "about a day: with `last`='7d' for the week, and with NO window fields at all for "
    "everything since the log began, which is the answer to 'evaluate all of this'."
)

DISPATCH = (
    "PREPARE workers for cards, then spawn them YOURSELF as sub-agents of this session. It assigns "
    "each card to a named worker, creates a git worktree per card already checked out on that card's "
    "branch, and returns a ready-to-use BRIEF per card. It starts nothing — you take those briefs and "
    "spawn one sub-agent each, ALL IN ONE MESSAGE so they run in parallel, on the session you are "
    "already in. That is the whole flow: plan, dispatch, spawn. Each brief already tells its worker "
    "which worktree to work in and never to run `git switch`, because sub-agents share this repository "
    "and switching would move every other worker's branch at once. `count` says how many (default 3, "
    "ceiling 12); `dry_run` shows which cards would be picked and changes nothing. Assignment happens "
    "first, so no other agent is offered a card you prepared — and IF YOU DO NOT SPAWN THEM, run "
    "recovery, because otherwise those cards sit assigned to workers that never existed and are "
    "invisible to everybody else. This tool never starts a process itself."
)

RECOVER = (
    "UNSTICK the board: hand back every card whose worker died, and say what survived. Call it when "
    "the board shows work in flight that is not moving — cards sitting `claimed` by agents that were "
    "killed, or assigned to workers somebody dispatched and never spawned. Both cases are covered, "
    "and the second has no lease at all, so nothing else finds it: those cards are invisible to every "
    "other agent and claimable by nobody until this runs. It does not wait for a lease to expire, "
    "because if you are looking at the board you have already noticed. It clears the ASSIGNMENT as "
    "well as the claim, so the card returns to the open pool. And it writes on each card what "
    "survived: commits are safe in git, and any UNCOMMITTED work is named with its full path — a "
    "killed agent writes before it commits, so that path is often real work. Read it before letting "
    "anybody start the task over. Workers still reporting are left alone and named in the reply; pass "
    "`force` to release those too."
)

CONTEXT = (
    "READ the standing facts of this project: the current objective, the invariants that must "
    "never break, and the decisions already settled — what a card cannot carry and a fresh "
    "agent has no way to guess. Call it at the START of a session, before planning anything, "
    "because a plan that does not serve the current objective is work nobody wanted. Pass a "
    "task id and you get the SLICE that applies to that card — every invariant, the objective, "
    "and only the decisions matching its labels or its files — which is what to hand a worker "
    "instead of the whole book. Reading it costs one call and stops the two failures that cost "
    "a day: re-litigating a settled question, and two agents working from different definitions "
    "of the same rule."
)

CAPTURE = """Create ONE card for work that has no card yet — and claim it, so you can commit.

Reach for this the moment you find yourself doing something the board does not know about: a bug
you tripped over, a fix a reviewer asked for, a refactor the task turned out to need. The commit
guard refuses a commit from an agent holding no card, and this is the one-call way out — the card
exists, you hold it, and the reply names the branch to commit on.

Use `taskops_plan` instead when you are decomposing work into SEVERAL cards with dependencies
between them; that call takes the whole tree at once. Use this one when there is exactly one thing
and you are already doing it.

`assign` hands it to somebody else instead of claiming it; `claim=false` records it for later."""
