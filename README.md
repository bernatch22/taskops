# taskops

**The shared task board for Claude Code agents.** Persistent tasks with a dependency graph, atomic claims that survive a crashed agent, every commit bound to the work that motivated it, and daily reports written by AI from a log that cannot lie.

Put two developers on it and it stops being a list: a finished card is **routed to one** reviewer rather than announced to everybody, a session opens knowing who else is working and on what, and approving somebody's work is what merges it into the trunk. It runs the same whether your team is online together or twelve hours apart — see [Coordination](#coordination-how-a-card-finds-its-person).

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

Twenty commands, all of them yours. Agents never use the CLI (they have MCP), and the hook wiring is a separate module nobody types.

| Command | What it does |
|---|---|
| `taskops init` | Create `.taskops/`, install the git hooks, write the agent guide. |
| `taskops join` | Join somebody's board from a fresh clone: init, hooks, MCP, remote and first pull, from one pasted URL. |
| `taskops attention` | **What the board is waiting for**, grouped by the move each card needs. `--wait` blocks until that changes. |
| `taskops status` | The `git status` of a project: what is open, who holds what, what is unwritten, what is unpushed. |
| `taskops ui` | The live web interface: board, activity timeline, reports. |
| `taskops open` | Open this project's board — or all your boards — in a browser, credential included. |
| `taskops tasks` | List, read, create, edit and close tasks. |
| `taskops context` | The standing facts: the objective, the invariants, the decisions. |
| `taskops report` | Board, standup, a written dossier of a day/range/everything — and `sweep`. |
| `taskops schedule` | Write the Claude Code scheduled task that keeps reports current. |
| `taskops recover` | Release cards held by workers that went silent. |
| `taskops land` | Merge a done card's branch into the trunk — the retry for one that did not land on approval. |
| `taskops publish` | Push every `tk/` branch to origin: the repair for work stranded on one machine. |
| `taskops setup` | Wire this project's MCP servers, and with `--channel` the opt-in board channel. |
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
taskops tasks add "Rename the column" --reviewer human   # a person closes this one; no agent may
taskops tasks edit tk-4f2a9c --priority 0      # title, spec, priority and reviewer stay correctable
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

Through MCP, from a session: `taskops_dispatch` assigns the cards, makes a git worktree each, and hands back one brief per card. The session spawns its **own sub-agents**, one per brief, on the subscription it is already paying for.

```sh
taskops recover                     # a killed worker's card returns to the queue
```

Each worker gets its own **worktree** on its own branch — a lease coordinates who owns a *task*, not whose bytes are on disk, and the worktree is what keeps parallel agents from overwriting each other.

There is no detached mode. `taskops run` existed and was removed: it opened a new billed session per card, and it could not hand that worker the specialist a project registered — a detached `claude -p` gets a generic prompt and the shell's default model, which is a worker pretending to be the role rather than being it.

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
| your orchestrator | context, board, plan, dispatch — **no Edit, no Write** | Reads the context, the board and the last week of dossiers; creates the cards that serve the current objective with EARS acceptance criteria; names the card blocking everything else; hands work out. It plans and delegates, never implements. |
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

---

## Coordination: how a card finds its person

Everything above is one agent and one board. This chapter is the part that only shows up when
there are two of you — two developers, each with a fleet of sub-agents, on two machines.

The mistake worth naming first is the one taskops does **not** make: it does not coordinate by
telling agents about each other. Every rule that matters lives in the board and executes there —
who may close a card, whose review it is, what becomes ready, when a merge happens. A message is
never how a decision travels; it is at most how somebody finds out it was made.

That distinction is what makes the rest of this chapter short.

### A review is an assignment, not an announcement

The default is that anybody may verify anybody's work. Turn that into peer review and one
sentence changes everything:

```sh
taskops context decision "reviewer: peer — nobody closes their own card"
```

Now `done` is refused for the developer whose agents produced the work. Which raises the
question the design turns on: **when a card enters `review`, who is it for?**

The obvious answer — tell everyone, whoever is free picks it up — is the one that fails. It was
tried, watched, and thrown away: two developers were free, both were told, both started reading
the same diff, and one of them spent an afternoon on work that was thrown away the instant the
other closed the card. Being *eligible* to review something is not the same as *having* it.

So the server picks one, and the choice is a **write on the card**, not a notification:

```
        a worker of uno's hands a card over
                        │
                        ▼
        ┌───────────────────────────────────┐
        │  who is actually here right now?  │   presence rides every call:
        │  (any call in the last 10 min)    │   nobody has to announce themselves
        └───────────────────────────────────┘
                        │
              ─ the author's own dev            ← never review your own team's work
                        │
              ─ whoever carries the most reviews already
                        │
              ─ whoever signalled most recently
                        │
              ─ alphabetical                    ← no coin flips, ever
                        ▼
              the card is assigned to dev:dos
              one directed message is written
              nobody else hears anything
```

Four consequences, and each one was a bug before it was a rule:

- **The chosen developer sees it in their sweep; nobody else does.** Not sorted last — absent.
- **Any of their agents may claim it.** Routing names a *person*, and a person reviews through
  sub-agents; a claim from `agent:dos/verifier` on a card routed to `dev:dos` is the very
  verifier it was sent to.
- **Closing it is theirs too.** The routing guards the claim *and* the close, because the close
  is the door that decides something.
- **It expires.** After thirty minutes the card opens to every eligible developer again. A nudge
  with a deadline, never a lock — a card must not be able to die waiting for somebody who closed
  their laptop.

And when there is genuinely nobody else, the handover says so in the return value the author is
guaranteed to read:

> Nobody else is connected, so this review was routed to NOBODY. It stays open to whoever shows
> up and it is in every eligible dev's sweep — but until somebody opens a session, it is waiting
> on no one.

That sentence exists because silence used to look identical to success.

### A session opens knowing who else is on the board

Everything a session was handed used to describe its own state, so two sessions on one board each
behaved as though they were alone. That is not a hypothesis: it is how one card got implemented
twice.

So the first screen of every session carries the other people, **before** it carries the work:

```
## Who else is on this board right now
  dos (active now): tk-b9a926 El endpoint de export
  ana (quiet 4m):   free — nothing claimed
Do not dispatch onto what they are holding, and do not review what is theirs.

## Waiting on a decision (this is where you start)
VERIFY — hand each to the verifier; a close here may unblock others
  tk-e9ad5d  El parser de fechas
```

The ordering is the argument. A session that reads the work list first has already started
choosing.

It is silent when you are alone, which is most of the time. A paragraph that always says the
same thing is one nobody reads.

---

## Being told, and finding out

Here is the only real fork in the road, and it is narrower than it looks: **both modes run the
same board, the same routing, the same guards.** What differs is *when a session learns that
something is waiting for it* — and the answer changes what kind of team the tool is good at.

The rule underneath both is one line:

> **A fact the board can re-derive belongs to the sweep. A fact somebody chose for you belongs
> to the channel.**

A card moved to `review`, a card that became ready, a lease that lapsed — every session that
looks reaches the same conclusion, so pushing those is noise with a timestamp. But *"this review
is yours"* is a decision somebody made about you, and it cannot be recovered by looking harder.
Routing is what turns a review from the first kind into the second. Without it, there would be
nothing worth pushing at all.

### The sweep — the board as the meeting point

One read answers "what does the board need from me", grouped by the verb you would use:

```sh
taskops attention              # or taskops_report kind=attention, from a session
```

```
VERIFY — hand each to the verifier; a close here may unblock others  (1)
  tk-e9ead7  El parser de fechas    in review since it was handed over; peer has not closed it

DISPATCH — taskops_dispatch tasks=…, then spawn one worker per brief  (2)
  tk-3620bd  El cuerpo de una nota  ready, unassigned, and nothing depends on it first
```

It is **read-only**, and that is the line between it and `recover`: a sweep that fixed what it
found would be a second dispatcher running on a timer. It reports; the orchestrator decides.

It also refuses to list work it knows you cannot do. A review routed to somebody else is not in
your sweep, and neither is one your own agents produced on a peer-review board — advice the
engine will refuse costs calls and teaches the reader to distrust the list.

When there is nothing to do and other people's workers are mid-flight, you do not end the turn
and you do not invent a poller:

```sh
taskops attention --wait       # blocks until the board wants a decision, prints it, exits
```

Run it in the background, keep working, sweep again when it returns. It wakes on **messages**
too, which matters more than it sounds: a routed review arrives as a message, so a loop watching
only card moves would sleep straight through the one event chosen for you.

**This is the whole mechanism.** Nothing below is required for a team to work.

### The channel — the board as an interruption

With the channel loaded, the same directed facts arrive **mid-turn**, without being asked:

```sh
claude --dangerously-load-development-channels server:taskops-channel
```

```
<channel source="taskops" card="tk-45a3ca" event_kind="mention" actor="agent:dos/w1">
agent:dos/w1 mentioned dev:uno on tk-45a3ca: tk-45a3ca espera tu revisión: "El comando notas".
Claim it first (taskops_next task=tk-45a3ca) — that is what keeps a second reviewer out.
</channel>
```

Three refusals decide what crosses, in the order they cost least:

1. **Your own dev.** `dev:ana` and `agent:ana/w1` are one person, so a session hearing what its
   own agents just did is hearing an echo of its own return values. Measured on a live
   afternoon: five of every six events.
2. **An id already delivered.** The live feed bounds itself every five minutes by design and this
   client reconnects, so a replayed event is ordinary traffic — and a line said twice reads as
   two things happening.
3. **An audience you are not in.** An event that names people and does not name you is somebody
   else's work.

Status changes are **not** in the default set, and that is the correction rather than an
oversight. They are derivable; `attention` is where you read them.

The feed also catches up on connect — bounded to the life of the session — because a session that
opened fifteen seconds before a teammate handed a card over used to miss that event permanently,
and a channel that silently drops the one thing you were waiting for is worse than one that is
obviously off.

A measured run of four cards between two developers, end to end:

```
uno: 1 event   (the review routed to it)
dos: 1 event   (uno's reply on that card)
```

Two events. Not two hundred.

### What each mode is actually good at

They are not tiers. They fit different teams, and the same repository can switch by starting a
session differently.

**Working at the same time.** The channel closes the gap between a handover and its review: a
card handed over at 14:32 is being verified at 14:32, and a session that would otherwise be
idle acts instead. The team behaves like one process — dispatch, review, land, unblock, dispatch
again — with nobody watching a board.

**Working at different times.** One developer at night, another in the morning, and they never
overlap. Routing finds nobody to choose, says so, and the card stays open. The next session to
open finds it in its own sweep. Nothing was pushed, nobody was polling, and the work still moved:

```
23:40   uno, alone
        worker commits, hands the card over
        routed to NOBODY — and the return value says exactly that
        session closes

        · · · · · · · · · the night passes · · · · · · · · ·
        (presence lapses; the board now knows nobody is here)

09:00   dos opens a session
        the opening screen carries the sweep:
            VERIFY  tk-9634ca  in review since it was handed over
        claims it, verifies it, closes it
        → the merge reaches the trunk, with the author asleep
```

There is nothing degraded about that path. The card was not a notification anybody missed; it is
a fact stored on the board, and the board was still there in the morning. **The channel removes
the wait, not the coordination** — which is why a team that never overlaps loses nothing by not
running it, and why a server-side scheduled session, where nothing is listening because nothing
is open, works the same way.

**A useful default:** start with the sweep. Add the channel when you notice sessions sitting idle
with the answer already on the board. That is the only symptom it treats.

---

## The work reaches the trunk

A card closing used to mean two different things — "I finished" and "this is in the trunk" — and
only the first was ever true. One board reported a hundred and eighteen cards done with `main`
still on its seed commit.

**Approval is the trigger.** A card reaching `done` has been read by somebody who is not its
author; that is exactly when a merge is justified, and hanging it there means nobody has to
remember:

```
   dos closes uno's card                        (peer review: the closer is never the author)
        │
        ├─ fetch the branch                     ← the closer's clone has never seen it
        ├─ catch the trunk up from the remote   ← somebody may have landed a minute ago
        ├─ merge --no-ff                        ← the card's work stays findable as a unit
        └─ push, and CHECK that it landed       ← a refused push is not a landing
                │
                ├── ok ──▶ the trunk everybody pulls has it
                │
                └── conflict ──▶ the card still closes, and the board records why.
                                 `attention` lists it under LAND, where a `taskops-fixer`
                                 sub-agent resolves it. A conflict is two approved pieces of
                                 work disagreeing about the same lines — that is a task, not
                                 a failure, and telling a person to "resolve it by hand" is
                                 telling somebody who is not there.
```

Two of those steps exist because they were missing. Landing is concurrent by construction — two
developers approving each other's cards is the *normal* case — so each of them merges into their
own copy of the trunk. Without the catch-up the second one merged onto a trunk hours old; without
the push check `land` reported success while the shared trunk had never seen the work. "Done
means an agent said so" is the one thing this system exists to prevent, and landing had quietly
reinvented it.

The merge runs on a **client**, never the server: git lives on a developer's machine, and a
server has state and no checkout. The *fact* of it is recorded on the board, because that is
where `attention` reads and where the other developer looks.

---

## Sharing a board: git, or a server

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
| [docs/orchestrator.md](docs/orchestrator.md) | Why the sweep replaced a notification feed, what routing fixed, and the four failures that only appeared with two real sessions running. |
| [docs/remote-developers.md](docs/remote-developers.md) | The guide to hand a new teammate: getting in, the daily rhythm, what their agents do. |
| [docs/agents.md](docs/agents.md) | Specialists a project defines, orchestration, sub-tasks and worktrees, who invokes whom. |
| [docs/reports.md](docs/reports.md) | Why the record matters, the narration, and the sweep that writes itself. |
| [docs/context.md](docs/context.md) | Objectives, invariants and decisions — and the slice each card receives. |
| [docs/exchange.md](docs/exchange.md) | The wire contract between a client and a server. |
| [docs/production.md](docs/production.md) | The plan for agents that run where the board lives — runner, sandbox → staging → prod. |
| [plugin/channel/README.md](plugin/channel/README.md) | The channel: what crosses, what never does, and how to load it. |

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
