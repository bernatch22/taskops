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

It calls `taskops_next`, receives the spec, the exact branch to create, and a warning if another agent is editing the same files. It works, commits (the trailer is added for it), and closes with `taskops_update`. Whatever was blocked on that task becomes ready — for every agent, automatically.

You watch it happen:

```sh
taskops ui        # the live board → http://127.0.0.1:2140
```

---

## The CLI — for people

Eleven commands, all of them yours. Agents never use the CLI (they have MCP), and the hook wiring is a separate module nobody types.

| Command | What it does |
|---|---|
| `taskops init` | Create `.taskops/`, install the git hooks, write the agent guide. |
| `taskops ui` | The live web interface: board, activity timeline, reports. |
| `taskops tasks` | List, read, create, edit and close tasks. |
| `taskops report` | Board, standup, or a written dossier of a day, a range, or everything. |
| `taskops run` | Run cards with headless Claude workers *(experimental, billed)*. |
| `taskops recover` | Release cards held by workers that went silent. |
| `taskops sync` | Reconcile with the committed event log (the git path). |
| `taskops serve` | Host many projects' boards on one port, one token each. |
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

Seven tools. The `inputSchema` of each is generated from its typed contract, so a parameter cannot exist on the wire without existing in the dispatch. Deliberately short: every tool costs every connected agent context.

| Tool | What it does |
|---|---|
| `taskops_next` | Claim work. Returns the spec, the branch to create, the agent's inbox, and a collision warning naming anyone else in your files. Says *why* when there is nothing. |
| `taskops_update` | Progress, a comment, a close, a handoff — and `mentions`, which is how agents message each other. |
| `taskops_ask` | One task in full, or free-text search across titles, specs and comments. |
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

One port, many projects, one token each. No token, no access — not even reads. With a remote configured, agents' claims and closes execute **in the server's database**: two agents on two continents asking for the same card are two inserts on one primary key again, and exactly one wins. There is no window.

Reports sync under a rule that refuses to destroy work: the narration is the one part a machine cannot regenerate, so a conflicting report is a `409` naming both versions — never a silent overwrite. A hand-written narration can never be clobbered by a generated one.

The token is the trust boundary. It is minted by the server, stored at `0600`, covered by the ignore rules so it cannot reach git, and never printed twice.

Opening a locked board in a **browser** does not need the token in the URL: the board answers a navigation without a credential with an access screen — paste the credential once, it is kept in `localStorage`, and every later visit goes straight in. The screen names nothing about what it is locking. A `curl` or a `fetch` still gets the plain `401` JSON it can read, and a local `taskops ui` with no token never shows a screen at all.

---

## The web interface

`taskops ui` serves a live board over the same contracts everything else uses. No polling from the browser — a WebSocket (with SSE fallback) pushes every change, and the green dot ticks on each event.

- **Board** — kanban that moves by itself. Click a card for the spec, the thread, the dependency graph, the commits with their files, and a reply box that reaches agents' inboxes.
- **Activity** — the event log as a history: a filterable timeline, and a roll-up per actor ranked by tasks touched rather than noise made.
- **Reports** — the daily dossiers, rendered. Generate a narration from the browser and **watch it being written**, streamed over the same socket.

The UI ships inside the wheel as a committed bundle — `pip install taskops-cli` serves the board with no Node toolchain anywhere.

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
