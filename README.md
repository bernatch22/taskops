# taskops

**The coordination substrate Claude Code does not have.** Persistent tasks with a dependency
DAG, atomic claims that survive a crashed agent, every commit bound to the work that motivated
it, and agents that can talk to each other across developers and machines.

Zero runtime dependencies. One SQLite file per repository, one committed event log, no server.

```
  taskops_next ──▶  work  ──▶  git commit  ──▶  taskops_update status=done
       │                            │                     │
   a lease, the spec,          the trailer is        whatever was waiting
   and a warning if            injected for you      on you becomes ready
   another agent is                                  for everyone
   in your files
```

## Why

Claude Code's Agent Teams coordinate through JSON files under `~/.claude/`, which is exactly
right for one developer's fleet for one afternoon: it is ephemeral, single-machine, has no UI,
and nothing connects it to git. taskops is the durable half — the shared truth a fleet needs
when the work outlives the session, spans machines, and has to be reviewable afterwards.

Two things it enforces rather than suggests:

- **A commit belongs to a claimed task.** A `PreToolUse` hook denies a commit with no claim,
  and *rewrites* the agent's own `git commit -m …` to carry `Task: tk-4f2a9c`. The agent never
  writes the trailer and never sees an error about it.
- **`done` requires a commit bound to the task.** Otherwise "done" means only that an agent
  said so — which is what reading a board instead of the diff is meant to avoid. Research and
  decisions close with `no_code` plus a written justification, which is recorded.

## Install

```sh
pip install taskops                 # or: uv pip install taskops
cd your-repo && taskops init        # creates .taskops/, installs the git hooks, writes the guide
claude mcp add taskops -- python3 -m taskops.transports.mcp
```

For the hooks and skills too, install the plugin in `plugin/`. `taskops init` is safe to
re-run, and re-running is how you repair a fresh clone — `.git/hooks` is not tracked, so a
clone has none.

## The five tools

| Tool | What it does |
|---|---|
| `taskops_next` | Claim work. Returns the spec, the branch to create, and a warning naming any other agent in your files. Says *why* when there is nothing. |
| `taskops_update` | Progress, a comment, a handoff, a close — and `mentions` to message another developer's agent. |
| `taskops_ask` | One task in full: spec, conversation, commits, what blocks it, what it blocks, who else touches its files. |
| `taskops_plan` | A whole decomposition in one call — tasks, tree and dependencies, with `after` referencing earlier entries by index. |
| `taskops_report` | `board`, `standup`, `day`. Generated, so they cannot be out of date. |

There is no sixth tool for messaging. Sending is `update` with `mentions`, so a message about a
task lives in that task's thread and is still findable in three weeks. Receiving is not a tool
at all — the inbox rides along with `next` and `ask`, and a `PostToolUse` hook delivers anything
new on the agent's very next tool call.

That is also the honest limit of "real time" between agents: Claude Code cannot be pushed to
mid-turn, so a session only listens when a hook fires. For a working agent that is seconds.

## How 100 agents avoid each other

A claim is a **lease**, not an assignment. Every taskops call renews it, so the deadline bounds
a *crash*, not a slow task: if a process dies, the task returns to the queue instead of sitting
there looking claimed forever. Two agents racing for one task are two `INSERT`s on one primary
key, and SQLite decides — no lock files, no retry loop.

The scheduler also refuses to hand two agents the same file: a task whose `files` overlap what a
live agent is editing sorts last, behind everything else, regardless of priority.

## Multi-developer, no server

```
  .taskops/events.jsonl   COMMITTED. append-only, content-hash ids.   ← the truth
  .taskops/db.sqlite      gitignored. WAL. rebuildable from the log.  ← a cache
```

Two developers' agents converge through `git pull`. Appending to different ends of a file is
the one edit git merges without help, and a content-hash id makes importing the same event
twice a no-op — so there are no conflicts to resolve. Events are facts about the past, and the
union of two logs *is* the correct log.

## Status

**Working and gated:** the engine, storage, the five MCP tools, an 11-command CLI, git-binding
with real hooks, multi-developer sync, and the plugin. 383 tests, `ruff` + `mypy` + `pyright`
strict, and 13 executable architecture invariants.

**Not built yet:** the Studio — the live web board. Its design is in `PLAN.md` §8, and the
pieces it needs (the event bus, the `after_seq` cursor, the projections) exist and are tested.
`taskops_report` no longer advertises `burndown` or `fleet` to a model: the first was never
implemented and replied with a sentence saying so, and the second answers a question that
stopped existing when workers became disposable. `fleet` is still a use case and the HTTP api
still serves it. What replaced them is `day` — one calendar day in full.

## Reading this repository

- **`ARCHITECTURE.md`** — the layers, every invariant and what it protects, and the decisions
  that differ from megabrain-v3 with the reasons.
- **`PLAN.md`** — the design, the ASCII diagrams, phase status, and the five bugs the tests
  found that the plan did not anticipate.
- **`RESEARCH.md`** — the landscape (Agent Teams, Gas Town/Beads, Vibe Kanban, backlog…) and
  what taskops does that none of them combine.
- **`src/taskops/assets/GUIDE.md`** — what `taskops init` drops into a repository: the manual
  an agent or a human reads to operate the thing.

MIT.
