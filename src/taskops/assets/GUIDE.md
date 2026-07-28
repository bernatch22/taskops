# taskops — how work happens in this repository

You are reading the shared task list's manual. One document for agents and humans, on
purpose: two documents drift, and then the two audiences are told different things.

`taskops init` copies this to `.taskops/GUIDE.md`. If anything here contradicts what the
tools actually do, the tools are right and this file is a bug.

---

## The one-paragraph version

Tasks live in this repository, not in anybody's session. You **claim** one before you code,
and the claim is a lease nobody else can take. Your commits are bound to the task that
motivated them — enforced, not suggested. When you finish, whatever was waiting on your task
becomes available to everyone else automatically. Every developer's agents share the same
list, and it travels by `git push` and `git pull` with no server involved.

## The loop

```
  taskops_next ──▶  work  ──▶  git commit  ──▶  taskops_update status=done
       │                            │                     │
   a lease, the spec,          the guard adds        whatever was waiting
   and a collision             `Task: tk-…`         on you becomes ready
   warning                     for you              for everyone
```

**Start every session by finding out where you stand.** If you do not already hold a task,
call `taskops_next`. It returns the spec, the exact branch to create, the conversation so
far, and a warning listing any other agent editing the same files. If nothing is available
it tells you *why*, which is usually something you can act on.

**Work on the branch it names** — `tk/<task-id>/<slug>`. Not a branch of your own choosing:
the commit guard matches this exact shape, and an invented name gets your own commits denied.

**Commit normally.** The guard adds the `Task:` trailer. You do not write it.

**Close with `taskops_update status=done`.** It will be refused if no commit is bound to the
task. That refusal is the feature — see below.

## The two rules the server enforces

These are not conventions. The server rejects the call.

**1. A commit belongs to a claimed task.** You must be on the task's branch and hold its
lease. Why: a commit nobody can attribute is a commit nobody can review against the work it
was supposed to do, and the moment one is allowed the board stops being a complete picture of
what changed.

**2. `done` requires a commit bound to the task.** Otherwise "done" means only that an agent
said so — which is exactly what a human reading a board instead of the diff is trying to
avoid. If a task legitimately produced no code (research, a decision, docs elsewhere), pass
`no_code: true` **with a comment saying what it produced instead**. That is recorded, so a
review can see which closures had no code and why.

## Your claim is a lease, not an assignment

It expires. Every taskops call you make renews it, so a task that takes an hour is fine — you
do not have to do anything special. What the deadline actually bounds is a **crash**: if your
process dies, the lease lapses within fifteen minutes and the task returns to the queue
instead of sitting there looking claimed forever.

Two consequences worth knowing:

- If a write is refused for a missing lease, **claim again**. Do not work around it. Another
  agent may genuinely have taken the task while you were gone.
- If you are out of context or out of depth, use `status: released` **with a comment** saying
  where you got to. That is the honest move and it is always allowed. Abandoning the task
  silently also works, eventually — but it throws away everything you learned.

## Talking to other agents

`taskops_update` with `mentions` puts a message in another actor's inbox:

```
taskops_update task=tk-4f2a9c
  comment="I'm rewriting the tokenizer in parser.py — hold off until I land this."
  mentions="agent:ana/api-1,dev:ana"
```

They see it within one tool call of their own, and it appears live on the board. The message
lives in the task's thread, so it is still findable in three weeks — which is why there is no
separate chat tool.

**When to use it:** the collision warning in `taskops_next` and `taskops_ask` lists other
tasks touching your files. That list is the one thing that prevents a merge conflict rather
than reporting it afterwards. Message them *before* you edit, not after the merge.

## Writing a spec that works

`taskops_plan` is where most of the damage gets done, because the reader of a `spec` is a
**fresh agent with none of your context** — possibly on another developer's machine, three
days from now.

A spec that works says:

- what **done** looks like, concretely enough to disagree with
- what must **not** change
- **where to start** — the files, the sibling to copy, the test that pins the behaviour

A one-line spec is the single most common cause of an agent doing the wrong thing correctly.

Also name `files`. It is how the scheduler avoids handing two agents the same file, and it is
what the collision warning is computed from.

## Dependencies

`after` in `taskops_plan` accepts the 0-based **index** of an earlier task in the same batch,
so a whole plan lands in one call:

```json
[
  {"title": "Add the events table",  "spec": "…", "files": ["storage/_events.py"]},
  {"title": "Board reads the table", "spec": "…", "after": [0]}
]
```

Nothing polls. When a task closes, everything that was only waiting on it becomes ready
immediately, and `taskops_update` tells you what you just handed to the fleet.

If you discover a dependency mid-task, use `blocked_on` — it adds the edge **and** marks you
blocked. A dependency that lives only in a comment is one the scheduler will walk somebody
straight into.

## If you are an ORCHESTRATOR: dispatching workers

`taskops_dispatch` assigns cards, creates a git worktree per card, and hands you a **brief per
card**. It starts nothing. You then spawn ONE SUB-AGENT PER BRIEF, all in a single message so they
run in parallel — they use the session you are already in.

```
taskops_plan      →  the cards
taskops_dispatch  →  N briefs           ← nothing is running yet
your Agent tool   →  N sub-agents       ← paste one brief each, in ONE message
```

Two rules for the workers, and both are in the brief already:

- **Each works inside its own worktree** (`.taskops/trees/<id>/`), which is already checked out on
  the card's branch. A worktree is per CARD, not per agent.
- **Nobody ever runs `git switch`.** Sub-agents share the repository, so switching would move the
  branch under every other worker at once. This is the whole reason the worktree exists.

Pass `spawn: true` only if you want detached processes that outlive your session — each one opens a
NEW Claude session, which is rarely what you want.

A spawned worker inherits your environment MINUS the Anthropic credentials
(`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`). The `claude` CLI prefers an
exported key over the logged-in subscription, so without this every worker would quietly bill per
token against a plan you already pay for. `taskops run --use-api-key` asks for the other mode out
loud; no MCP tool can.

**If you dispatch and then do not spawn**, the cards sit assigned to workers that never existed. Run
`taskops recover` to hand them back.

## When a fleet dies

Workers get killed: a session ends, a balance runs out, somebody hits ctrl-C. Their cards stay
`claimed` until their leases expire, which is fifteen minutes of a board that looks busy and is not.

```
taskops recover           # releases every card whose worker has gone quiet
taskops recover --force   # …including the ones still reporting, for a fleet that is alive and wrong
```

It clears the assignment as well as the lease — a card handed back still assigned to a dead worker is
one NOBODY can pick up, since the scheduler hides it from everyone else.

And it writes on each card what survived: commits are safe in git, and **uncommitted work is named
with its path**, because a killed agent writes before it commits. Read that before starting over.

## Reading the board

- `taskops_report board` — every column, who holds what
- `taskops_report standup --since 24h` — what changed, per actor, and what needs a human
- `taskops_report fleet` — which agents are alive right now, on what, touching what file

In `fleet`, `SILENT` means the agent still holds a claim but has gone quiet past the grace
period. That row is shown rather than hidden, because it is the one somebody needs to act on.

## Multi-developer, no server

`.taskops/events.jsonl` is an append-only log, and it is **committed**. Two developers'
agents converge through `git pull`: appending to different ends of a file is the one edit git
merges without help, and every event's id is its content hashed, so importing the same event
twice does nothing.

`.taskops/db.sqlite` is a **cache** and is gitignored. It can be rebuilt from the log, so
deleting it loses nothing but live leases.

The `post-merge` hook runs `taskops sync` for you. Run it by hand any time; it is idempotent.

## If something looks wrong

- **"no taskops project"** — run `taskops init` in the repository root.
- **A commit was denied** — read the message; it names the branch to switch to or the task to
  claim. Do not use `--no-verify` to get around it. The `post-commit` hook will record the
  commit anyway, and you will have a commit whose task nobody agreed on.
- **`taskops_next` says nothing is ready** — read the reason. "Everything blocked" is worth
  reporting to a human; "everything claimed" means ask again shortly.
- **Hooks are not firing** — they live in `.git/hooks`, which is not tracked, so a fresh
  clone has none. `taskops init` again is the repair; it chains onto existing hooks rather
  than replacing them.
