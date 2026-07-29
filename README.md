# taskops

**The shared task board for Claude Code agents.** Persistent tasks with a dependency graph, atomic claims that survive a crashed agent, every commit bound to the work that motivated it, daily reports written by AI from a log that cannot lie — and a team mode where agents on different machines can never grab the same card.

Zero runtime dependencies. One SQLite file per repository, one committed event log. A server is optional.

```
  claim ──▶  work  ──▶  git commit  ──▶  done
    │                        │             │
  a lease, the spec,    the Task: trailer  whatever was waiting
  and a warning if      is injected        on you becomes ready
  another agent is      for you            for everyone
  in your files
```

---

## Why

Coding agents are good at working and terrible at remembering. A session plans five tasks, finishes two, and dies — and with it dies the plan, the reasoning, and the claim on the work. Run several agents at once and it gets worse: two of them edit the same file, both mark things "done" that nobody can verify, and tomorrow no one can say what actually happened.

taskops is the durable half. Tasks live **in the repository**, not in anybody's session. Claims are **leases** that expire when a process dies. Commits are **bound to tasks by enforcement**, not convention. And because the source of truth is an append-only event log with content-hashed ids, the whole board travels through `git push` — or through a shared server when you want claims to be atomic across machines.

Two rules are enforced rather than suggested:

- **A commit belongs to a claimed task.** A hook denies an agent's commit when it holds no claim, and rewrites its own `git commit -m …` to carry a `Task: tk-4f2a9c` trailer. The agent never writes the trailer and never sees an error about it.
- **`done` requires evidence.** Closing a task with no commit bound to it is refused — otherwise "done" means only that an agent said so, which is exactly what reading a board instead of the diff is meant to avoid. Research and decisions close with `no_code` plus a written justification, which is recorded.

## Install

```sh
pip install taskops-cli            # the command, the import and the MCP module
                                   # are all `taskops` — only the PyPI name differs

cd your-repo
taskops init                       # creates .taskops/, installs the git hooks
claude mcp add taskops -- python3 -m taskops.transports.mcp
```

For the Claude Code hooks and the `/taskops:*` skills, install the plugin from `plugin/`. `taskops init` is safe to re-run — re-running is how you repair a fresh clone, since `.git/hooks` is never tracked.

## Quickstart

Ask Claude, in plain language:

> Read the auth module and plan the work to add refresh tokens. Use taskops.

It calls `taskops_plan` once with the whole tree — tasks, specs, dependencies — and the board exists. Then:

> Claim the next task and start.

It calls `taskops_next`, receives the spec, the exact branch to create, and a warning if another agent is editing the same files. It works, commits (the trailer is added for it), and finishes at `review`; a verifier — never the worker itself, the engine refuses that — closes it against the card's criteria. Whatever was blocked on it becomes ready, for every agent, automatically.

You watch it happen:

```sh
taskops ui        # the live board → http://127.0.0.1:2140
```

---

## The CLI — for people

Sixteen commands, all of them yours. Agents never use the CLI (they have MCP), and the hook wiring is a separate module nobody types.

| Command | What it does |
|---|---|
| `taskops init` | Create `.taskops/`, install the git hooks, write the agent guide. |
| `taskops status` | The `git status` of a project: what is open, who holds what, what is unwritten, what is unpushed. |
| `taskops ui` | The live web interface: board, activity timeline, reports. |
| `taskops open` | Open this project's board — or all your boards — in a browser, credential included. |
| `taskops tasks` | List, read, create, edit and close tasks. |
| `taskops context` | The standing facts: the objective, the invariants, the decisions. |
| `taskops report` | Board, standup, a written dossier of a day/range/everything — and `sweep`. |
| `taskops schedule` | Write the Claude Code scheduled task that keeps reports current. |
| `taskops run` | Run cards with headless Claude workers *(experimental, billed)*. |
| `taskops recover` | Release cards held by workers that went silent. |
| `taskops sync` | Reconcile with the committed event log (the git path). |
| `taskops serve` | Host many projects' boards on one port, one token each. |
| `taskops login` | Sign in to a server with your GitHub account; the remote configures itself. |
| `taskops remote` | Point this project at a server. |
| `taskops push` / `pull` | Exchange events and reports with the server. |


### Working with tasks

```sh
taskops tasks                                  # open tasks; a finished project lists its closed ones
taskops tasks show tk-4f2a9c                   # one card in full: spec, thread, commits, dependencies
taskops tasks add "Fix the timeout" --spec "DONE = the retry test passes" --files api/client.py
taskops tasks edit tk-4f2a9c --priority 0      # title, spec and priority stay correctable
taskops tasks done tk-4f2a9c -m "landed; expiry is a column, not a job"
taskops tasks release tk-4f2a9c -m "out of depth — the parser needs someone who knows the grammar"
taskops tasks search "refresh"
```

`tasks done` goes through the same guard an agent faces: no commit bound, no close.

### Reports

Every report is a **projection of the event log** — generated, so it cannot be out of date and cannot flatter anyone.

```sh
taskops report                      # the board
taskops report standup --since 24h  # what changed, per actor, and what needs a human
taskops report day                  # one calendar day in full: what closed, with every
                                    #   commit's diff size, what opened, the whole conversation
taskops report range --last 7d      # a week, grouped by day
taskops report all                  # the entire project, from the first event
```

Add `--digest` and Claude reads the dossier and writes the narration — what was asked versus what was delivered, card by card, decisions, surprises, and what is still owed. It streams into your terminal as it is written, uses your existing Claude Code login (never an API key), and lands in `.taskops/reports/<label>.md`, committed like source. The facts are written before the model is called, so a failed narration never costs the record.

```sh
taskops report day --digest         # yesterday, explained
taskops report all --digest         # the whole project, as a document you read instead of the git log
```

### Running a fleet

```sh
taskops run --dry-run               # which cards would get a worker — free
taskops run tk-a99e3f tk-4c84b3     # one headless Claude per card, each in its own git worktree
taskops recover                     # a killed worker's card returns to the queue
```

Each worker gets its own **worktree** on its own branch — a lease coordinates who owns a *task*, not whose bytes are on disk, and the worktree is what keeps parallel agents from overwriting each other. Workers never inherit your `ANTHROPIC_API_KEY`: they use the subscription you are already logged into, and `--use-api-key` is an explicit opt-in.

The cheaper default is `dispatch` through MCP: the orchestrating session spawns its **own sub-agents**, one per prepared brief, on the subscription that is already paid for.

---

## The MCP tools — for agents

Nine tools. The `inputSchema` of each is generated from its typed contract, so a parameter cannot exist on the wire without existing in the dispatch. Deliberately short: every tool costs every connected agent context.

| Tool | What it does |
|---|---|
| `taskops_next` | Claim work. Returns the spec, the branch to create, the agent's inbox, and a collision warning naming anyone else in your files. Says *why* when there is nothing. |
| `taskops_update` | Progress, a comment, a close, a handoff — and `mentions`, which is how agents message each other. |
| `taskops_ask` | One task in full, or free-text search across titles, specs and comments. |
| `taskops_capture` | ONE card for work nobody planned — created *and* claimed, so a refused commit is one call from allowed. |
| `taskops_context` | The project's standing objective, invariants and settled decisions — or the slice of them that applies to ONE card. |
| `taskops_plan` | A whole decomposition in one call: tasks, tree, dependencies. |
| `taskops_dispatch` | Prepare worker briefs — assign cards, create worktrees. The caller spawns its own sub-agents. |
| `taskops_recover` | Hand back the cards of workers that died. |
| `taskops_report` | `board`, `standup`, `day`, `range` — generated, never stale. |

### What a session actually does

Plan once, with dependencies referencing earlier entries by index:

```
taskops_plan tasks=[
  {"title": "Add the refresh token table",
   "spec":  "Migration plus model. DONE = a token round-trips with an expiry. Do not touch sessions.",
   "files": ["db/schema.sql"]},
  {"title": "Issue a refresh token on login",
   "spec":  "Return one alongside the access token. DONE = the login test asserts both.",
   "files": ["auth/login.py"],
   "after": [0]}
]
```

Claim — and note what rides along:

```
taskops_next
→ # tk-4f2a9c — Add the refresh token table
  Claimed. Create the branch and work there:
      git switch -c tk/tk-4f2a9c/add-the-refresh-token-table

  ### 📬 1 message(s) for you
  **agent:ana/api-1** on tk-8b31d0 (3m ago): careful with token.py

  ### ⚠ Also touching these files
  - tk-8b31d0 (in_progress, agent:ana/api-1) — Issue tokens
  _Message them before editing shared files, not after the merge._
```

Talk to another developer's agent — there is no sixth chat tool on purpose. A message about a task lives in that task's thread, where it is still findable in three weeks:

```
taskops_update task=tk-8b31d0
  comment="I'm rewriting the token model in models/token.py — hold off until I land it."
  mentions="agent:ana/api-1"
```

Delivery is honest about what Claude Code allows: a session cannot be pushed to mid-turn, so the inbox arrives through hooks on the recipient's **very next tool call** — seconds, for a working agent. Delivery is tracked per `(actor, event)`, never by a timestamp cursor, so a message that arrives out of order is never silently skipped.

Discover a prerequisite mid-task, and record it in the graph rather than in prose:

```
taskops_update task=tk-4f2a9c blocked_on=tk-9d21aa
  comment="the schema migration has to land first"
```

A dependency that lives only in a comment is one the scheduler will walk somebody else straight into.

### How agents avoid each other

- **A claim is a lease.** Every taskops call renews it; if the process dies, the lease lapses and the task returns to the queue. The TTL bounds a *crash*, never a slow task.
- **A race is an INSERT.** Two agents claiming one task are two inserts on one primary key; SQLite decides. Verified with fifty real threads: exactly one winner.
- **Files repel.** A task whose declared `files` overlap what a live agent is editing sorts behind everything else, regardless of priority — the cheapest place to prevent a merge conflict is before either side starts.
- **Assignment hides.** A card assigned to a worker is invisible to every other agent — not sorted last, *gone* — which is what makes "this one is yours" mean something.

---

## The three agents the plugin ships

Installing the plugin gives you three sub-agents. They are DATA — a markdown file each in
`plugin/agents/`, with their name, description, tool list and model in the frontmatter — so a
project can add its own without touching any Python.

| Agent | Tools it has | What it does |
|---|---|---|
| `taskops-manager` | context, board, plan, dispatch — **no Edit, no Write** | Reads the context, the board and the last week of dossiers; creates the cards that serve the current objective with EARS acceptance criteria; names the card blocking everything else; hands work out. It plans and delegates, never implements. |
| `taskops-worker` | claim, ask, update, and the full edit surface | One card: claim → branch → work → commit → close **with evidence** for each criterion. Hands the card back with notes rather than sitting on it. |
| `taskops-verifier` | ask, update, Read, Bash — **no Write** | The adversary, on a cheap model. Reads the acceptance criteria and the diff and tries to demonstrate `done` is false. |

### …and the specialists a project registers for itself

Drop a markdown file in **`.taskops/agents/`** and it travels through git with the project.
Same format as the plugin's, plus two optional keys taskops understands and Claude Code does
not:

```markdown
---
name: taskops-collectors
description: The ingestion specialist.
tools: [Read, Edit, Bash, mcp__taskops]
model: sonnet
labels: [collectors, etl]     # which cards are this specialist's
files: ["src/data/**"]        # its edit surface
---

You own the ingestion path. …
```

Three things then happen, and the third is the one nobody else does:

1. **It becomes invokable.** The SessionStart hook copies it into `.claude/agents/` (stripping
   `labels`/`files`, which Claude Code does not know). Only files carrying the
   `# generated by taskops from …` marker are ever overwritten or pruned — an agent you wrote
   by hand there is never touched.
2. **`taskops_dispatch` routes to it.** Card labels ∩ registry labels, most shared wins, ties
   alphabetical; the brief comes back with `agent_type: taskops-collectors`, and the
   orchestrating session spawns THAT sub-agent. No match, no `agent_type`, stock worker.
3. **The claim enforces it.** An agent running as `agent:berna/taskops-collectors` that asks
   for a `[ui]` card is refused, and the refusal names both label sets. Role→card binding
   enforced where it is a fact instead of suggested in a prompt where it is advice. An actor
   name that matches no registry entry stays unrestricted.

A repo file with the same `name` as a plugin file **wins** — that is how you replace the stock
worker without forking the plugin. A project with no `.taskops/agents/` behaves exactly as it
always did.

A card's `acceptance` is a list of EARS lines — `WHEN <trigger> THE SYSTEM SHALL <response>` —
set by `taskops_plan`, by `taskops tasks edit --acceptance`, and readable by anybody. Closing a
card that has them requires `evidence` saying which were met and what proves it, or
`no_evidence` with a reason, which is written into the card's event log. A card with no
criteria closes exactly as it always did.

Worked example, one real card:

```
manager   taskops_context            -> objective: "ship 0.4 by Friday"; invariant: "frozen contract"
          taskops_plan  tk-9f21aa    title:      "Requeue a card whose lease lapsed"
                                     acceptance: WHEN a lease expires, THE SYSTEM SHALL return
                                                 the card to ready
                                                 WHEN a card is requeued, THE SYSTEM SHALL keep
                                                 the previous holder's comments
          spawns one worker on tk-9f21aa

worker    taskops_next task=tk-9f21aa  -> git switch -c tk/9f21aa-requeue
          ... edits engine/scheduler.py, writes tests/engine/test_sweep.py, commits ...
          taskops_update status=done
            evidence="criterion 1: test_a_lapsed_lease_returns_the_card passes
                      (pytest tests/engine -q, 41 passed). criterion 2:
                      test_requeue_keeps_the_thread — the comments survive."

verifier  taskops_ask tk-9f21aa        -> reads both criteria and the evidence
          pytest tests/engine -q       -> 41 passed
          git show <the card's commit> -> nothing beyond the card
          taskops_update comment="HOLDS: verified 2 criteria by running the named tests."
```

Had the verifier found `test_requeue_keeps_the_thread` missing, it would have posted `FAILS`
naming the criterion and the command that shows it — and the card, already `done`, would have
a comment on it that a human reads before believing the board.

## Working as a team

### Through git — no server at all

`.taskops/events.jsonl` is committed. Append-only, content-hashed ids: appending to different ends of a file is the one edit git merges without help, and importing the same event twice is a no-op. Two developers' boards converge through ordinary `git pull`; the post-merge hook reconciles automatically. Events are facts about the past — the union of two logs *is* the correct log, so there is nothing to conflict.

### Through a server — when claims must be atomic across machines

```sh
# somewhere reachable
taskops serve init myproject --root ~/taskops-server    # prints the project token once
taskops serve --root ~/taskops-server --host 0.0.0.0

# each developer
taskops remote add https://boards.example.com/myproject --token <token>
taskops push        # send your events up, take theirs down
taskops pull
```

**Or nobody hands out tokens at all.** If the server was started with GitHub auth, a new
teammate signs in with the account they already have and the remote configures itself:

```sh
taskops login https://boards.example.com     # takes your token from `gh auth token`
taskops remote add https://boards.example.com/myproject    # no --token: it uses the session
taskops push
```

`login` trades a GitHub token for a **session** — stored in `~/.taskops/sessions.json` at `0600`,
outside every repository, scoped to that one server, expiring on its own in seven days. The
GitHub token itself is never written down: it crosses one call and is gone. Somebody who leaves
the GitHub org loses the board when their session lapses, with nobody rotating anything by hand.

One port, many projects, one token each. No token, no access — not even reads. With a remote configured, agents' claims and closes execute **in the server's database**: two agents on two continents asking for the same card are two inserts on one primary key again, and exactly one wins. There is no window.

Reports sync under a rule that refuses to destroy work: the narration is the one part a machine cannot regenerate, so a conflicting report is a `409` naming both versions — never a silent overwrite. A hand-written narration can never be clobbered by a generated one.

The token is the trust boundary for a MACHINE. It is minted by the server, stored at `0600`, covered by the ignore rules so it cannot reach git, and never printed twice.

For PEOPLE there is no token to hand out. Link the project to its GitHub repository and the repository's push access becomes the board's:

```sh
taskops serve link myproject --github owner/repo --root ~/taskops-server   # on the server
taskops login https://boards.example.com                                   # each person
```

The server holds no GitHub credentials. The client sends the token `gh auth token` prints, the server asks GitHub with *that* token whether the account may push to the linked repo, and **discards it** — so GitHub is the collaborator list and is never copied here. What survives is a session, good for a week, that opens exactly the boards that answered yes. Contract in `docs/exchange.md`; the guide to hand a new teammate is [docs/remote-developers.md](docs/remote-developers.md).

Opening a locked board in a **browser** does not need the token in the URL: the board answers a navigation without a credential with an access screen — paste the credential once, it is kept in `localStorage`, and every later visit goes straight in. The screen names nothing about what it is locking. A `curl` or a `fetch` still gets the plain `401` JSON it can read, and a local `taskops ui` with no token never shows a screen at all.

Or skip the address bar entirely:

```sh
taskops open              # this project's board, credential included
taskops open --projects   # the server's own page: every board your session reaches
taskops open --print      # just the URL, for a terminal with no browser
```

### What synchronises when — and why you cannot collide

Not everything travels at the same moment, and the split is deliberate: **the writes that could collide go over the wire immediately; the ones that cannot are batched.**

| | when | why |
|---|---|---|
| **claim** (`next`) and **close** (`update`) | **instantly, in the server's database** | two machines claiming one card must resolve *now*; there is no local copy to disagree with |
| new cards, edits, comments | on the next `push` | a new card has an id nobody else can mint, so two people planning at once produce a union, never a conflict |
| everyone else's work | on `push` (which also pulls) or `pull` | events are facts about the past; importing one twice is a no-op |
| reports and narrations | on `push`/`pull`, newest stamp wins | equal-but-different is a `409`, never a silent overwrite |

A claim is a single `INSERT` on one primary key. That is the whole collision story: exactly one machine wins, the loser is told the card is taken and asks for the next one. **If the server is unreachable, a claim fails loudly** — it never quietly falls back to a local claim, because that fallback is precisely the collision the server exists to prevent.

So the rhythm is: `taskops pull` when you sit down, `taskops push` when you stand up (or whenever you want your cards visible), and *nothing in between* — the part that had to be atomic already was.

---

## Daily reports, unattended

`taskops report sweep` narrates **every day that has ended, has events and has no write-up yet** — so it is safe to run late, early, or twice, and the second run costs nothing because it calls no model. Two triggers put it on autopilot, and neither is cron or launchd:

```sh
taskops schedule install     # writes ~/.claude/scheduled-tasks/taskops-sweep/SKILL.md
taskops schedule status      # what is on disk, and what is still missing
```

**Honest limitation: we write the prompt, not the schedule.** Claude Code keeps a scheduled task's time, folder and model inside the app, so `schedule install` writes the file and then prints the one sentence to say to Claude — *"create a daily scheduled task at 00:05 named taskops-sweep that runs /taskops:sweep in \<this folder\>"*. Until you say it, nothing is scheduled. If Claude Code is not on this machine the command refuses instead of creating a config directory nothing will read.

The **backup trigger needs no setup at all**: the plugin's `SessionStart` hook fires the sweep detached, so opening a session in the morning is what gets yesterday written up. It is bounded on purpose — at most one sweep per project per day (a stamp under `.taskops/`), nothing at all for a project with no history and no remote, silent on every failure, and `TASKOPS_NO_SWEEP=1` turns it off. It never delays a session: the child is spawned in its own process group and the hook returns in microseconds.

## The web interface

`taskops ui` serves a live board over the same contracts everything else uses. No polling from the browser — a WebSocket (with SSE fallback) pushes every change, and the green dot ticks on each event.

- **Board** — kanban that moves by itself. Click a card for the spec, the thread, the dependency graph, the commits with their files, and a reply box that reaches agents' inboxes.
- **Activity** — the event log as a history: a filterable timeline, and a roll-up per actor ranked by tasks touched rather than noise made.
- **Reports** — the daily dossiers, rendered. Generate a narration from the browser and **watch it being written**, streamed over the same socket.

The UI ships inside the wheel as a committed bundle — `pip install taskops-cli` serves the board with no Node toolchain anywhere.

## Going deeper

| | |
|---|---|
| [docs/remote-developers.md](docs/remote-developers.md) | The guide to hand a new teammate: getting in, the daily rhythm, what their agents do. |
| [docs/agents.md](docs/agents.md) | Specialists a project defines, orchestration, sub-tasks and worktrees, who invokes whom. |
| [docs/reports.md](docs/reports.md) | Why the record matters, the narration, and the sweep that writes itself. |
| [docs/context.md](docs/context.md) | Objectives, invariants and decisions — and the slice each card receives. |
| [docs/exchange.md](docs/exchange.md) | The wire contract between a client and a server. |
| [docs/production.md](docs/production.md) | The plan for agents that run where the board lives — runner, sandbox → staging → prod. |

## Architecture, briefly

```
contracts/    every payload that crosses a boundary, as TypedDicts. Zero logic.
storage/      the ONLY package that writes SQL. One SQLite file per repo, WAL.
engine/       the decisions: state machine, scheduler, projections, git, buses.
render/       contract → text. Pure functions, no I/O.
usecases/     one module per verb. Sync, all the way down.
transports/   cli · mcp · http · hooks — thin, and forbidden to reach deeper.
```

The rules that matter are executable — an architecture test suite fails the build when one breaks:

- **The event log is the truth; SQLite is a cache.** Delete the database and rebuild it from the log. Every view — board, standup, report — is a projection, so a new view is a rendering decision, never a migration.
- **One transport per audience.** The CLI is the developer's, MCP is the agent's, `taskops.transports.hooks` is what git and Claude Code invoke. None of them contains logic; all of them call the same use cases, which is why three surfaces cannot disagree about what `done` requires.
- **The state machine has one home.** A transition table plus one convenient `if status ==` somewhere else is two state machines, and the convenient one always forgets the guard.
- **Hooks fail open.** A coordination tool that blocks your commit because its database was locked has broken the thing it exists to support.
- **The engine never calls a model.** The one place taskops talks to Claude — narrating a report — shells out to the CLI you are already logged into, strips API credentials from the environment so a background process can never spend money you didn't choose to spend, and shows the model only the generated dossier: never a transcript, never a diff.

## Philosophy

- **Generated over written.** A standup nobody typed cannot be out of date and cannot flatter anybody.
- **Evidence over assertion.** `done` demands a commit; exemptions demand a written reason; both are recorded.
- **Honest over smooth.** An empty pane says which kind of nothing it is. A truncated list says what it dropped. A report that has gone stale says so instead of regenerating and pretending.
- **The log is for humans.** The committed event log stays readable in a diff — heartbeats and streaming deltas never touch it.

## License

MIT.
