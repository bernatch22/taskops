# Changelog

## Unreleased — a card remembers which sessions worked it

- **The conversation viewer found nothing for interactively-worked cards.** A card's transcript was
  located by path plus a `gitBranch` filter, which identifies a dispatched agent (it makes a branch)
  and loses the most ordinary case there is: a person who claims a card in their own terminal and
  never leaves `main`. Every one of their entries failed the filter. The `PostToolUse` hook now
  stamps its session id onto the leases the actor holds, and a transcript named by a recorded session
  id is read whole, whatever branch it was on. Nothing passed a session before — the tool accepted
  one and no caller supplied it, so every `claimed` event in a real project carried an empty string.
- **An empty pane now says which kind of nothing it is.** "No conversation found" plus a path reads
  as a broken viewer, and was reported as one. Three cases are now distinguished: no transcript
  directory at all (check `$CLAUDE_CONFIG_DIR`), a directory with no session recorded against this
  card (normal, nothing to show), and a recorded session whose entries are missing.

Cards worked before this shipped stay unrecoverable, and that is a real limit rather than a bug: with
no session id and entries on `main`, there is no evidence tying them to a card.

## 0.1.0 — the engine, the enforcement, and the plugin

First release. The coordination substrate works end to end: an agent can claim work nobody else
will start, commit against it under enforcement, close it only with something to show, and hand
a message to another developer's agent.

**The claim is a lease.** Two agents racing for one task are two `INSERT`s on one primary key,
settled by SQLite — no lock files and no retry loop. Verified with 50 real threads on separate
connections: exactly one winner. Every taskops call renews the holder's lease, so the TTL bounds
a crashed process rather than a slow task, and a dead agent's work returns to the queue instead
of sitting there looking claimed.

**Commits are bound to tasks, and it is enforced.** A `PreToolUse` hook denies a commit with no
claim and returns `updatedInput` to *rewrite* the agent's own `git commit -m …` with the
`Task:` trailer — the agent never writes it and never sees a failure about it. A `post-commit`
hook records everything the guard never saw: a human's terminal commit, a `--no-verify`, a
rebase landing on a task branch. `done` is refused without a commit bound to the task, unless
`no_code` is passed with a written justification, which is recorded.

**Multi-developer with no server.** `.taskops/events.jsonl` is committed and append-only with
content-hash ids, so two clones converge through `git pull` and importing the same event twice
is a no-op. Verified with two real clones and a bare remote. The SQLite file is a cache and is
gitignored.

**Agents talk to each other.** `taskops_update` with `mentions` reaches another actor's inbox,
delivered by a `PostToolUse` hook on their very next tool call. Delivery is tracked per
`(actor, event)` rather than by a timestamp cursor, because hooks fire in an order nobody
controls and a cursor would silently skip a message that arrived late.

**Five MCP tools, and no sixth.** `next`, `update`, `ask`, `plan`, `report`. The `inputSchema`
of each is generated from its TypedDict, so a parameter cannot exist on the wire without
existing in the dispatch. Messaging is `update` with `mentions` on purpose — a message about a
task belongs in that task's thread, where it is still findable in three weeks.

**A plugin.** `plugin/` ships the MCP server, four hooks and four skills (`claim`, `plan`,
`standup`, `handoff`), plus the agent-facing `GUIDE.md` that `taskops init` writes into the
repository — one document for agents and humans, because two drift.

### Architecture

Zero runtime dependencies. Seven layers with 13 executable invariants (`tests/architecture`),
copied from megabrain-v3 with three deliberate differences, each documented where it is made:

- **WAL, not a rollback journal.** megabrain's choice is a property of its workload — rare
  writes, so readers never wait. Here a hundred agents write continuously while the board
  reads, so the trade flips.
- **The file budget counts CODE lines** (≤70, docstrings excluded) with a raw ceiling of 160,
  rather than 100 raw. Counting raw punishes the one thing this codebase is built on and
  rewards deleting the explanation to fit.
- **`ruff format` is not run.** It puts a collection either on one line or one per line, which
  spends the file budget on style. megabrain does not run it either: 221 of its 300 files would
  be reformatted.

### Found by the tests, not by review

Recorded because they are the decisions only a running system produces:

- `BEGIN IMMEDIATE` must be a transaction's first statement — sqlite3 opens one implicitly on
  the first write, and the heartbeat wrote first. The whole claim is one transaction now.
- `claimed → done` was missing, so `in_progress` was mandatory: one extra call in the lifecycle
  of every task in exchange for nothing the commit does not already prove.
- Git hooks must embed `sys.executable`. Hooks run with git's environment, which routinely
  cannot see the virtualenv — a bare `taskops` resolved to nothing and the hook did nothing,
  silently, because every line ends in `|| true`.
- `rev-parse --abbrev-ref HEAD` fails on an unborn HEAD, so in a repository with no commits the
  guard told an agent that the task branch it was standing on was not a task branch.
  `symbolic-ref` instead, which also reports a detached HEAD honestly.
- `git log --grep commit` was read as a commit: the parser looked for the word near the front
  instead of resolving the actual subcommand.

### Not in this release

The Studio — the live web board — is designed (`PLAN.md` §8) and unbuilt. `taskops_report
burndown` answers "not implemented yet" rather than returning an empty chart.
