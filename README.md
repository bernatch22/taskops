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
taskops init                       # everything below, in one command
```

`init` writes `.taskops/`, the gitignore block, the git hooks, `.mcp.json` and
`.claude/settings.local.json` — so the MCP server, the five Claude Code hooks and the status
line are wired without you typing any of them. **Do not add the MCP server by hand.** The entry
`init` writes names an ABSOLUTE interpreter, and a `claude mcp add … python3 …` typed into a
shell records whatever `python3` means in *that* shell — which is not what a GUI-launched
session resolves, and the failure is an MCP server that silently does not start.

Every file it touches is merged, never overwritten: a hook, an MCP server or a `statusLine` you
configured yourself is left exactly as you wrote it. `taskops init` is safe to re-run — and
re-running is how you repair a fresh clone, since `.git/hooks` is never tracked.

For the `/taskops:*` skills and the agent definitions, install the plugin from `plugin/`.

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

Twenty-five commands, all of them yours. Agents never use the CLI (they have MCP), and the hook wiring is a separate module nobody types.

Grouped by what they are FOR, which is the only grouping that helps: the board, the standing
facts, git, and the server. Every command and every subcommand is here.

**The board — what you read and change**

| | |
|---|---|
| `taskops attention [--wait] [--every N]` | **What the board is waiting for**, grouped by the move each card needs. The one read worth making every turn. `--wait` blocks until that changes. |
| `taskops status [--fetch] [--idle-days N]` | The `git status` of a project, in one screen: what is open, who holds what, what is unwritten, what is unpushed. |
| `taskops statusline` | The row Claude Code paints at the bottom of a session. Not for typing — `taskops init` wires it into `.claude/settings.local.json`, and it prints what you are holding, what the board wants, and whether that is the truth or a cache. |
| `taskops tasks …` | `list · show · add · plan · edit · done · release · reject · cancel · log · search`. `edit` takes `--title --spec --priority --reviewer --acceptance` — the last one semicolon-separated, because an EARS line is a sentence with commas in it. |
| `taskops recover [--force] [--grace S]` | Release cards held by workers that went silent. |
| `taskops ui [--port] [--host] [--token] [--readonly]` | The live web interface: board, activity, reports, and the standing context. Records where it bound in `.taskops/ui.json`, so anything else can find it. |
| `taskops open [--projects] [--print]` | This board — or all of yours — in a browser, credential included. In a project with **no** server it starts a local `ui` and opens that: the question is the same either way. |
| `taskops report …` | `board · standup · day · range · all · fleet · sweep` |
| `taskops schedule {install\|status}` | The Claude Code scheduled task that keeps reports current. |

**What the project has already decided**

| | |
|---|---|
| `taskops context …` | `show · objective · decision · note · log · retire` — **prose a worker weighs** |
| `taskops policy {show\|reviewer} [value]` | **Values the engine obeys**, validated when written |

**Setting up, and the team**

| | |
|---|---|
| `taskops init [--no-hooks]` | The whole wiring: `.taskops/`, the gitignore block, the git hooks, `.mcp.json`, `.claude/settings.local.json` (five hooks + the status line) and the two specialists in `.claude/agents/`. Merges, never overwrites. Safe to re-run — that is how you repair a fresh clone. |
| `taskops join [<url>]` | Join this repo's board: init, hooks, MCP, remote and first pull. **No URL needed** — the clone carries it. |
| `taskops board …` | `create · list · view · access · invite` |
| `taskops login <url> [--logout] [--show]` | Sign in to a server with your GitHub account. |
| `taskops setup [--channel] [--print] [--remove]` | Wire this project's MCP servers. `init` already does it; this is the repair. |

**Git — the CODE, never the board**

| | |
|---|---|
| `taskops publish` | Push every `tk/` branch to origin, so a reviewer can see the diff. |
| `taskops land <task>` | Merge a done card's branch into the trunk. |
| `taskops sync` | The board **through git**, for a project with no server: import, replay, unblock, export. |

**The server**

| | |
|---|---|
| `taskops serve [--host] [--port] [--readonly] [--no-create] [--rate-limit]` | Many boards on one port. |
| `taskops serve init <name>` · `serve link <name> --github owner/repo` | A board made ON the box — for one with no GitHub repository behind it. |
| `taskops remote [add <url> [--token t] \| remove]` | The server this project syncs with. `board create` and `join` set it for you. |
| `taskops push [--force]` · `taskops pull` | The report FILES, and a pre-remote board's history. **Not** how a remote board syncs. |

> **With a server the two never collide, and it is not luck.** A clone accepts a relayed event
> already marked exported, so `sync` has nothing to send and `.taskops/events.jsonl` stops
> growing the moment a remote is configured — measured with two clones working and both running
> `sync`: the server reached 4 events, both local logs stayed at 1, and `git status` was clean
> in both. The file freezes as the pre-remote history and git has nothing left to merge.
>
> **The board never travels through GitHub.** Two channels that never touch: git carries the
> CODE (`publish`, `land`), and the board lives either in `.taskops/events.jsonl` — committed,
> the no-server path, which is what `sync` reconciles — or on a server, where every write goes
> as it happens and there is nothing to send. See [What synchronises when](#what-synchronises-when--and-why-you-cannot-collide).


### Working with tasks

```sh
taskops tasks                                  # open tasks  (`taskops tasks list` spelled out)
taskops tasks --all --status review            # closed ones too, or one column
taskops tasks show tk-4f2a9c                   # one card in full: what it is PART OF, its spec,
                                               #   subtasks, what it blocks, the thread, the commits
taskops tasks log tk-4f2a9c [--limit 50]       # the agent's own conversation while working it
taskops tasks search "refresh"

taskops tasks add "Fix the timeout" --spec "DONE = the retry test passes" --files api/client.py
taskops tasks add "Rename the column" --reviewer human   # a person closes this one; no agent may
taskops tasks add "Ship the parser" --after tk-4f2a9c --priority 0 --label core
taskops tasks edit tk-4f2a9c --priority 0 --spec "…" --title "…" --reviewer peer
```

A whole tree in ONE call — `parent` is what a card is PART OF, `after` is what must finish
first, and both take an existing id **or the 0-based index of an earlier entry in the same
list**:

```sh
taskops tasks plan - <<'JSON'
[{"title": "EPIC: the importer", "spec": "a CSV goes in, every row is stored",
  "acceptance": ["WHEN a 3-row CSV is imported THE SYSTEM SHALL store 3 rows"]},
 {"title": "the reader",    "spec": "read in chunks",        "parent": 0, "files": "src/read.py"},
 {"title": "open the file", "spec": "encoding is explicit",  "parent": 1},
 {"title": "iterate lazily","spec": "yield per line",        "parent": 1},
 {"title": "the validator", "spec": "refuse a short row",    "parent": 0, "after": [1]}]
JSON
```

An epic cannot reach `done` while a child of it is open — that refusal is what makes a
checklist mean something.

**Closing is yours.** A card in `ready` cannot go straight to `done`: the agent claims it,
works it and leaves it in `review`, and you decide.

```sh
taskops tasks done    tk-4f2a9c -m "landed; expiry is a column, not a job"
taskops tasks done    tk-4f2a9c --no-code -m "a decision, not a diff" --evidence "criterion 1: …"
taskops tasks reject  tk-4f2a9c -m "FAILS: the empty case raises — pytest -k empty"
taskops tasks release tk-4f2a9c -m "out of depth — the parser needs someone who knows the grammar"
taskops tasks cancel  tk-4f2a9c -m "superseded by tk-8b31d0"
```

`tasks done` goes through the same guard an agent faces: no commit bound, no close. And
`reject` demands its findings — a card bounced with nothing to act on goes round twice.

### Milestones — the chapter a board is in

A milestone has a **title** (three or five words — what the board's selector and a card's badge
show) and a **goal** (what done means, and what is out of scope — prose, as long as it needs to be,
and what every worker under the chapter reads).

**Every card belongs to exactly one milestone**, and a board with none refuses to plan. That is the
one hard rule of the model, and it buys the thing a context layer cannot buy any other way: a fact
attached to a chapter LEAVES every slice when a person says the chapter was reached. Nobody has to
retire it. A decision taken in March stops being injected in December on its own.

An agent may open one, start it, work under it and REPORT it finished. Only a person may say it was
reached — the same argument as `done` on a card, one level up: no count of closed cards can mean
"we shipped it".

```sh
taskops milestone new "El importador" \
  --goal "que una clienta suba su CSV y reciba el reporte sin pedirnos nada. NO entra el envío por
          mail ni el export a Excel — ese es el capítulo siguiente" \
  --horizon 2026-09-01
taskops milestone new "Facturación" --planned      # written down, not started
taskops milestone edit 31b0b89a --goal "…"         # the goal is written as the team learns it
taskops milestone start 31b0b89a                                    # a planned one becomes active

taskops milestone                        # every ACTIVE chapter, its counts, then what is planned
taskops milestone show a2d96841          # one chapter WITH its cards
taskops milestone list --all             # the record: reached and abandoned too

taskops milestone review a2d96841 -m "las tres cards cerradas, el import anda"   # an agent reports
taskops milestone done   a2d96841        # a PERSON verifies
taskops milestone reject a2d96841 -m "falta el encoding latin-1"                 # …or sends it back
taskops milestone cancel a2d96841 -m "la clienta se fue"    # kept, with the reason. No delete
```

**Several at once is normal.** A team ships two things in a fortnight, and a board that refused to
record the second would disagree with what is happening. The bound is not "one chapter per board",
it is "one chapter per card" — so `plan` asks which when more than one is active:

```
$ taskops milestone
# active — 2
◐ c5df2915  El importador  by 2026-09-01
   que una clienta suba su CSV y reciba el reporte sin pedirnos nada. NO entra el envío por mail…
   3 card(s) · 2 done · 1 in review
   REPORTED FINISHED — "las tres cards cerradas, el import anda"
   A person verifies: `taskops milestone done c5df2915` — or sends it back with `reject`.
◆ 5217f040  Facturación
   que se pueda emitir una factura desde el CRM y quede en AFIP
   4 card(s) · 1 done · 2 ready · 1 blocked

# planned — written down, not started
○ 31b0b89a  Export a Excel
```

### What this project has already decided

Three nouns over one log, split by WHOSE fact it is and how long it lives. A **decision** is prose
a worker weighs; a **policy** is a value the engine obeys and refuses to be wrong about.

```sh
taskops context rule     "cero dependencias fuera de la stdlib" --project   # outlives every chapter
taskops context decision "el CSV se lee en streaming, nunca entero en memoria"
taskops context decision "sqlite, not postgres" --labels db --files src/db.py
taskops context note     "el importador tiene tres etapas: leer, validar, cargar"

taskops me objective "terminar el parser esta semana" --horizon 2026-08-08   # YOURS
taskops me note      "corro pytest -x, no la suite entera"
taskops me                            # your page

taskops context                       # what is in force right now
taskops context --task tk-4f2a9c      # the SLICE that card's worker receives
taskops context --milestone c5df2915  # what ONE chapter settled — a closed one too
taskops context log                   # and what we used to believe, retired ones marked `~`
taskops context retire 0829cfb9       # withdraw one. The eight characters printed are enough
```

`--project` is the LIFETIME. Without it a fact belongs to the chapter in force and leaves every
slice when that chapter is reached; with it, it stands forever. The default falls on the
recoverable side deliberately: a fact that died with its chapter is restated in one command, and
one that lives forever accumulates until nobody reads any of them.

**Scope has three dimensions, one rule each.** `--labels` / `--files` narrow by SUBJECT; the
noun you used narrows by PERSON (`taskops me` files it under you); and the chapter narrows by TIME.

| | how many | who receives it |
|---|---|---|
| `rule` | few — that is the point | **everybody, always**, and `--project` makes it outlive the chapter |
| `decision` with NO labels/files | as many as you like | every card in its chapter |
| `decision` | as many as you like | cards sharing its `--labels` / `--files` |
| `note` | as many as you like | its chapter's cards. Never `--project`: a permanent note is a rule |
| `me objective` | **one per person** — the latest wins | that person's sessions, and nobody else's |

So a worker on ana's card reads the project's rules, ITS chapter, and ana's objective — never
juan's, and never a chapter that shipped:

```
                                            ← what ana's worker is INJECTED with
## Rules — the project's. Every card, every milestone, no exceptions.
· 03ff2ef1  cero dependencias fuera de la stdlib

## ◆ Milestone in force — El importador      by 2026-09-01
   que una clienta suba su CSV y reciba el reporte sin pedirnos nada
   3 card(s) · 2 done · 1 in review
   decisions   36b8de72  el CSV se lee en streaming, nunca entero en memoria  [importador]
   notes       79c06207  el importador tiene tres etapas: leer, validar, cargar
   yours       4055c4a0  terminar el parser esta semana  by 2026-08-08
```

**A slice grows by ONE, whatever the size of the team**, and that is why `owner` is a filter
rather than a label: past ~150-200 standing instructions compliance decays, so a page that grew
with the team would make every agent slightly worse each time somebody joined. Juan does not see
ana's objective, ana's note, or the `[db]` decision.

The one person is the card's **author**, not whoever is reading. A card in review is assigned to
the reviewer the server routed it to, so a verifier from juan's session asking for that slice gets
the project's facts plus **ana's** — the objective the work has to be judged against. Still one
person: the verifier's own context is not added on top.

```sh
taskops policy reviewer peer          # what every NEW card is created with
taskops policy reviewer               # read it
taskops policy reviewer none          # turn it off
taskops policy show
```

> Working alone, do **not** set `reviewer peer`: the only person allowed to close is the author,
> so every card deadlocks. It is for a team.

### Reports

Every report is a **projection of the event log** — generated, so it cannot be out of date and cannot flatter anyone.

```sh
taskops report                      # the board  (`taskops report board` spelled out)
taskops report board
taskops report fleet                # every worker: what it holds, how fresh its lease is
taskops report standup --since 24h  # what changed, per actor, and what needs a human
taskops report day                  # one calendar day in full: what closed, with every
                                    #   commit's diff size, what opened, the whole conversation
taskops report range --last 7d      # a week, grouped by day
taskops report range --from 2026-07-01 --to 2026-07-31
taskops report all                  # the entire project, from the first event
taskops report sweep [--limit N] [--push]   # narrate every ENDED day that has none yet
taskops report day --write --force  # persist the dossier without calling a model
```

`sweep` **pushes on its own when the project has a remote**, which is the only way an
unattended narration reaches anybody: neither trigger passes a flag, so a hosted board used to
get its prose written to somebody's laptop and left there. `--no-push` writes and sends nothing.

Add `--digest` and Claude reads the dossier and writes the narration — what was asked versus what was delivered, card by card, decisions, surprises, and what is still owed. It streams into your terminal as it is written, uses your existing Claude Code login (never an API key), and lands in `.taskops/reports/<label>.md`, committed like source. The facts are written before the model is called, so a failed narration never costs the record.

```sh
taskops report day --digest         # yesterday, explained
taskops report all --digest         # the whole project, as a document you read instead of the git log
```

### The board on a server

```sh
taskops board create                       # infers name + repo from `origin`; --server the first time
taskops board create --github you/acl-repo --name probe    # code elsewhere, access list on GitHub
taskops board list
taskops board view --web
taskops board access                       # who can get in, and the `gh` lines that change it
taskops board invite ana                   # a one-use code, for a board with no GitHub behind it
taskops board invite --withdraw ana

taskops join                               # the teammate: no URL, the clone carries it
taskops join "https://server/probe?invite=…"
taskops login https://boards.example.com

taskops remote                             # what this project syncs with, and how far
taskops remote add https://server/probe --token <t>     # by hand; `board create` does it for you
taskops remote remove                      # forget the server AND its credential
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
| `taskops_context` | The standing objective, decisions and notes — the whole project's, or the slice that applies to ONE card. The session that plans can also **state** one (`state` + `text`) or `retire` one; a worker is refused, because those are what it is judged against. |
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
  - tk-8b31d0 (claimed, agent:ana/api-1) — Issue tokens
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
- **An agent is its developer's hand.** A card assigned to `dev:ana` is claimable by `agent:ana/w1`, because that is what delegation *is*: you hand work to a person, and their session spawns the worker that does it. It never folds the other way (an `agent:` card stays that worker's) and never across people (`agent:juan/w1` is still refused it).

---

## The plugin: agents, and the wiring that makes rules unavoidable

The Python package is the board. The **plugin** is what makes a Claude Code session behave like
a member of a team that has one — and it is three separable things:

```
   plugin/agents/*.md        WHO does the work        →  sub-agents you spawn
   Claude Code hooks         WHEN the board speaks    →  5 events, 5 different readers
   git hooks                 WHAT binds work to a card →  5 hooks, in .git/hooks
```

The reason there are three and not one paragraph of instructions is the lesson this project
paid for most often, and it is worth stating before any of the detail:

> **An instruction is not a mechanism.** Anything a model must remember across a long session
> belongs in the message that needs it, or in a guard that refuses. Prompts dissolve.

Every hook below exists because the same thing had been written in a prompt first, and a real
session had forgotten it by turn forty.

### The agents — two files, and one role that is not a file

Installing the plugin gives you two sub-agents. They are **data**: a markdown file each, with
name, description and tool list in the frontmatter, so a project can add its own without
touching any Python.

| | Tools it has | What it does |
|---|---|---|
| **your session** — the orchestrator | context, board, plan, dispatch — **no Edit, no Write** | Reads the context and the board, creates the cards that serve the objective with EARS criteria, hands work out, decides what moves. It plans and delegates, never implements. |
| `taskops-worker` | claim, ask, update, and the full edit surface | One card: claim → branch → work → commit → close **with evidence** for each criterion. Hands the card back with notes rather than sitting on it. Also what resolves a merge conflict when `attention` reports one under `LAND`. |
| `taskops-verifier` | ask, claim, update, Read, Bash — **no Write** | The adversary. Reads the criteria and the diff and tries to demonstrate `done` is false. Claims the card first, which is what stops a second verifier starting. |

**Two, and there were four.** A `taskops-lead` owned an epic and dispatched its children, and a
`taskops-fixer` resolved one merge conflict — and neither earned a file. The lead is the
orchestrator with a different name: same tools minus `Edit`, same job, one level down, and the
session doing the planning is the one that already has the plan. The fixer is a worker whose card
happens to be a conflict; it had the same loop, the same guards and a narrower prompt. Two roles
that are really one, described twice, is two places for the same rule to drift.

**The tree is two deep and cannot go deeper**, and that is a property of the tool lists above
rather than a rule anybody has to keep: your session spawns workers and verifiers, and neither
has anything to spawn with. A card whose shape is a CHECKLIST — subtasks under subtasks — is
planned in one `taskops_plan` call and worked one worker per subtask:

```
your session ──▶ taskops-worker    (subtask 1)
             ──▶ taskops-worker    (subtask 2)
             ──▶ taskops-verifier  (each one, as it comes back)
```

The engine backs the shape up — an epic cannot reach `done` while a child is open.

### The one model that is pinned

The worker's file names **no model**, and the verifier's names `opus`. That asymmetry is the
whole policy:

- **A worker inherits.** A card that is a typo in a docstring and a card that is a state machine
  are the same shape to that prompt and nothing like the same job, and the orchestrator
  dispatching it is the only party that has read the spec. Pinning one model would either
  overpay for every small card or send a cheap one at the hard ones.
- **A verifier does not.** Its whole job is to be harder to convince than the worker was, so it
  may never be the weaker of the two — and unpinned it would inherit whatever the session
  happened to be running, which on a cheap session is a rubber stamp with extra steps.

The orchestrator is the only one with no file, because it is not a sub-agent: **it is the
session you are typing into.** That is not a naming choice, it is enforced by an event —
`SessionStart` fires for the main conversation and never for a sub-agent, so a session reading
its own opening screen has proof of which one it is. It is told so in the first line it reads,
before you type anything:

> You are the ORCHESTRATOR of this board. You do not implement: you dispatch `taskops-worker`
> sub-agents for the work and `taskops-verifier` sub-agents for the reviews, and you decide what
> moves. A card you work yourself is a card nobody is keeping the plan for.

That sentence used to end with *"Run `taskops_next` to claim one"* — and two live sessions read
it, became workers, did the work themselves and left both cards dead in `review` with nobody
left to verify anything. The first thing a session reads decides what it becomes.

### The Claude Code hooks — five events, five different readers

The rule that governs all of them, learned the expensive way:

> **A hook speaks to whoever its event delivers to, and no further.** Before writing an
> instruction into one, name the reader and check it can do the thing.

`SubagentStop` injects into the **sub-agent that stopped** — a worker, with no ability to spawn
anything. An ask for a verifier placed there had a worker spend four turns explaining that it
lacks the tool.

| Hook | Who reads it | What it does |
|---|---|---|
| `SessionStart` | the main conversation, only | The opening screen: your role, the project's standing objective and decisions, **who else is on the board and what they hold**, and what is waiting on a decision. It also sets two things in motion without blocking: the daily sweep, and — for a project with no server — a local board, so the first line has an address to click. |
| `SessionStart` | **and the person at the keyboard** | One coloured sentence in plain English — the only thing taskops ever prints to a terminal. See below. |
| `PreToolUse` | the agent about to act | Sees a `git commit` before it runs and refuses one no lease covers — with a sentence that says how to get a card, not just "no". |
| `PostToolUse` | the agent that just acted | Delivers the inbox. A session cannot be pushed to mid-turn, so a message addressed to an agent arrives on its **very next tool call** — seconds, for a working agent. |
| `Stop` | the main conversation | Refuses to end a turn on a review this session opened and nobody picked up, and on cards it left unfinished. Twice, then it lets you go: an agent that has read the message twice will not act on a third copy, and a trapped session is worse than a stale board. |
| `SubagentStop` | the sub-agent that stopped | Only what that reader can act on: its own unfinished card. Nothing about spawning, because it cannot. |

Two of those are the *only* reason the loop closes without anybody watching it. `SessionStart`
is what makes a session know it is the orchestrator; `Stop` is what keeps a finished card from
sitting in `review` for a week because the session that produced it ended politely.

### The two things a PERSON sees

Every field above goes to the model. `additionalContext` is wrapped in a system reminder the
human never sees, and a hook's plain stdout is hidden too — so for a long time a session opened,
the agent silently received the whole board, and the person watching could not tell taskops had
run at all. Two surfaces fix that, and both are written for somebody who does not know the
vocabulary:

**The opening sentence** — `systemMessage`, the one hook field that reaches a terminal:

```
taskops is tracking this project with your team — the team is working towards ship the importer
(by 08-20), and you are on the date parser. Right now: 5 ready to hand to an agent and 2 waiting
for somebody to review. Since yesterday, you moved tk-ff2f62 to review and ana picked up tk-0a84e1.
Board: https://taskops.example.com/probe/
```

One line, coloured, and it never grows with the board: people are capped at two and cards are
counted per meaning, so forty cards and nine developers cost what three do. It says
`on this machine only` when there is no server, because "5 ready to hand out" means something
different on a board only you can see.

**The status line** — the row above Claude Code's own footer badges, repainted on every update:

```
-- INSERT --  ·  ◐ tk-92c0aa the date parser  ·  4 to hand out, 2 to review  ·  probe (shared, cached)  ·  78% ctx
```

`taskops init` writes it into `.claude/settings.local.json`, and leaves a `statusLine` you
already configured completely alone. Three things worth knowing about it:

- It **never touches the network and never writes.** Claude Code re-runs a status line on a
  300 ms debounce; an HTTP call on that cadence would be a request per keystroke-burst, and a
  projection that wrote would make merely looking at the screen an event on an append-only log.
- Because of that, on a shared board it says **`cached`**. Your teammate's claim lands in that
  row on the next sync, not the instant they make it, and a bar that hid the difference would
  promise a liveness it does not have.
- It **cannot remove** `⏵⏵ bypass permissions on`. Claude Code renders a status line in its own
  row *above* the built-in footer badges. What it can do is repeat `-- INSERT --`, which it does
  when you use vim bindings — so the eye that goes looking for the mode finds the board too.

### The git hooks — five, and each one covers a path the others cannot see

`taskops init` writes them into `.git/hooks`. They are never tracked, which is why re-running
`init` is how you repair a fresh clone.

| Hook | What it does |
|---|---|
| `pre-commit` | Refuses an **agent's** commit that no lease covers. A human is warned and passes — the asymmetry is deliberate. |
| `prepare-commit-msg` | Writes the `Task: tk-4f2a9c` trailer onto the commits it allowed. The only hook git hands the message file to; the agent never writes the trailer and never sees an error about it. |
| `post-commit` | Binds the commit to the card — including commits the PreToolUse guard never saw: a human's terminal commit, a `--no-verify`, a rebase landing on a task branch. |
| `post-checkout` | Records the branch on the lease, so the board shows where an agent is working without asking it to report that. |
| `post-merge` | Imports what a `git pull` just brought in — the moment another developer's events become visible. |

They are also the answer to *"what if the agent is not Claude Code?"* The PreToolUse guard sees a
Bash tool call and nothing else, so a script, a rebase or another harness was unguarded. The git
hooks sit under all of them, because git is the one thing every path goes through.

**All of them fail open.** A coordination tool that blocks your commit because its database was
locked has broken the thing it exists to support.

### How the three compose

One card, from a plan to the trunk, with each mechanism named as it fires:

```
  SessionStart ─▶ "you are the orchestrator" + who else is here + what is waiting
        │
        │  the session plans, then dispatches: a worktree and a brief per card
        ▼
  spawns taskops-worker ──▶ claims the card (a LEASE; it renews on every call)
        │                        │
        │                   pre-commit: is this agent holding a card?  ── no ──▶ refused
        │                        │ yes
        │                   prepare-commit-msg: the Task: trailer is written for it
        │                   post-commit: the commit is bound to the card, branch published
        │                        │
        │                   update status=review
        │                        │
        │                   the SERVER routes it to one other developer, and the
        │                   worker's own return value tells its session:
        │                   "routed to dev:dos — do NOT verify it yourself"
        ▼
  SubagentStop ─▶ speaks to the WORKER: anything of yours still open?
        │
  Stop ────────▶ speaks to the SESSION: a review you opened is unverified. Spawn a
                 verifier for it — and never names a card routed to somebody else.
                                   │
                                   ▼
                      the other developer's session:
                      SessionStart or the channel delivers the routed review
                                   │
                      spawns taskops-verifier ──▶ claims it (card STAYS in review,
                                   │              which is what stops a second one)
                                   │              runs the tests, reads the diff
                                   ▼
                              closes it with evidence per criterion
                                   │
                        approval merges the branch into the trunk
                                   │
                          conflict? ──▶ attention reports it under LAND
                                        ──▶ spawn taskops-worker
                                   │
                        whatever was blocked becomes ready, for everyone
```

Read it once more looking only at what is **enforced** rather than asked for: the lease, the
refused commit, the written trailer, the routing, the claim that keeps a second verifier out,
the evidence `done` demands, the merge on approval. Nothing in that column depends on an agent
remembering anything.

### Specialists a project registers for itself

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
manager   taskops_context            -> objective: "ship 0.4 by Friday"; decision: "frozen contract"
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
command changes everything:

```sh
taskops policy reviewer peer
```

A **policy**, not a context decision, and the difference is the point: a decision is prose for
a model to weigh, so it cannot refuse anything. This was one for a while, parsed out of the
text, and a misspelt specialist matched nothing, degraded to "nobody named", and left every
card unreviewed — silently, and indistinguishable from never having stated it. A policy is a
value the engine acts on, so it goes through the same validator the card's own field does and a
typo is refused at the door. It is read when a card is CREATED and written onto the card.

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
                                 `attention` lists it under LAND, where a `taskops-worker`
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

Somebody runs the server once, and after that **nobody logs into it again**:

```sh
taskops serve --root ~/taskops-server --host 0.0.0.0
```

Everything else happens from a laptop, and there are **two ways in, neither of which needs you
to ssh anywhere**. Which one you want depends on a single question: *is this project on GitHub?*

| | with GitHub | without |
|---|---|---|
| you type | `taskops board create` | `taskops remote add <server>` then `taskops board create <name>` |
| who may create it | anyone who can push to the repo | anyone who can reach the server (`--no-create` shuts it) |
| what comes back | a **session** — GitHub already said who you are | the board's **token**, into `.taskops/remote.json` |
| how a teammate joins | `taskops join` — push access IS the invitation | `taskops board invite ana` → one code, one person |
| revoking | remove them from the repo; effective next login | withdraw the code, or rotate the token |

Neither is the fallback. A GitHub-linked board gets an access list that revokes itself, which is
worth having; a tokenless board is what a project on a GitLab, a checkout with no origin, or a
directory that is not in git at all actually needs, and that is most of them.

#### Without GitHub — three commands

```sh
taskops remote add https://boards.example.com
taskops board create test
taskops board invite ana
```

The first names the server and asks for nothing: there is no board yet, so there is nothing to
authenticate to and no credential to do it with. The second creates it and writes the minted
token into `.taskops/remote.json` — gitignored, `0600`, never printed twice. The third cuts a
one-person, one-use code that expires in seven days:

```
invited ana to https://boards.example.com/test

  send them this — it works ONCE, and expires in 7 days:
      taskops join https://boards.example.com/test?invite=<code>
```

#### With GitHub

Making a board is `gh repo create`'s shape — it reads the checkout you are standing in rather
than interviewing you about it:

```sh
cd your-repo
taskops board create --server https://boards.example.com
```

```
created https://boards.example.com/your-repo
  linked to you/your-repo — push access to that repo is the invitation
  signed in as you
  remote configured, 24 event(s) migrated

  commit .taskops/board.json so your team needs no URL:
    git add .taskops/board.json && git commit -m 'the board lives here'

  then they run, in their own clone:
    taskops join
```

The name came from `origin`, the repository it binds to came from `origin`, the session came
back with it, and whatever the project had already recorded locally went up. **`--server` is
needed only for the first board**: after that this machine is signed in and it is the default.

The authorisation is the same question the login asks, one step earlier — *you may create a
board for a repository you can already push to*. Nothing is granted that GitHub had not granted
first, and the board is bound at birth to something you demonstrably control. A server that
should not accept this starts with `--no-create`, and a `--readonly` one refuses it already.

And the teammate, in a fresh clone of the same repository:

```sh
taskops join
```

No URL, no token, nothing pasted from a chat. `.taskops/board.json` is committed — it holds the
address and nothing else, which is why it can be — so the clone already knows where its board
is, exactly as `git clone` already knows its remote. If they are not signed in yet, the refusal
names the one command that fixes it rather than answering `401`.

### Invite somebody: `taskops board invite`

For a board with **no GitHub repository behind it**, the owner mints a per-person code:

```sh
taskops board invite ana
```

```
invited ana to https://boards.example.com/probe

  send them this — it works ONCE, and expires in 7 days:
      taskops join https://boards.example.com/probe?invite=45969642478202d5d60e0053cfb4

  the board will record them as `dev:ana`. The code is stored only as a digest and
  is never printed twice; inviting them again replaces it.
```

Ana runs that one line and is working: `join` inits the store, installs the git hooks, wires the
MCP, redeems the invite into a session and fills the board. `taskops board invite --withdraw ana`
takes a code back before it is spent.

Four properties, each closing a way this shape leaks: **single use** (a code that works twice is
a code that works forever, because it is in a chat log), **it expires** on the session's own
week, **it names the invitee** so the board records `dev:ana` rather than "somebody with the
link", and it is **stored hashed** — a leaked `invites.json` is a list of names, not a set of
working keys.

A board that IS linked to a repository does not need this: push access already is the
invitation, and it revokes when the repository does.

### The project is not on GitHub, and you still want a GitHub access list

Self-hosted git, GitLab, a bare repo on a box, no remote at all — the code does not have to be
on GitHub for the *board* to get GitHub's access model. Bind it to a repository you control that
exists only to be the access list:

```sh
gh repo create you/proyecto-x-board --private       # empty; nobody ever pushes code to it
cd proyecto-x                                       # origin is gitlab, or nothing
taskops board create --server https://boards.example.com \
                     --github you/proyecto-x-board --name proyecto-x
```

```
created https://boards.example.com/proyecto-x
  linked to you/proyecto-x-board — push access to that repo is the invitation
```

The code stays wherever it lives; the empty repository is the **ACL**. Adding somebody is
`gh repo collaborator add them --permission push -R you/proyecto-x-board`, removing them is the
mirror of it, and you get named people, real revocation and no string to pass around — none of
which the token gives you. `taskops board access` reads the link from the server, so it answers
correctly even though this checkout's `origin` is not GitHub.

<details><summary>The token path, when even that is too much</summary>

```sh
taskops serve init myproject --root ~/taskops-server    # on the box; prints the token once
taskops remote add https://boards.example.com/myproject --token <token>
```

Still the right answer for CI, and for a project that does not live on GitHub. It is no longer
how a team starts.
</details>

`login` trades a GitHub token for a **session** — stored in `~/.taskops/sessions.json` at `0600`,
outside every repository, scoped to that one server, expiring on its own in seven days. The
GitHub token itself is never written down: it crosses one call and is gone. Somebody who leaves
the GitHub org loses the board when their session lapses, with nobody rotating anything by hand.

One port, many projects, one token each. No token, no access — not even reads. With a remote configured, agents' claims and closes execute **in the server's database**: two agents on two continents asking for the same card are two inserts on one primary key again, and exactly one wins. There is no window.

Reports sync under a rule that refuses to destroy work: the narration is the one part a machine cannot regenerate, so a conflicting report is a `409` naming both versions — never a silent overwrite. A hand-written narration can never be clobbered by a generated one.

The token is the trust boundary for a MACHINE. It is minted by the server, stored at `0600`, covered by the ignore rules so it cannot reach git, and never printed twice.

For PEOPLE there is no token to hand out, and no user list either. **The GitHub repository's push access IS the board's access**, which `board create` binds at birth (`taskops serve link` rebinds one that predates it).

So granting somebody the board is not a taskops command at all:

```sh
gh repo collaborator add ana --permission push -R you/your-repo   # grant
gh repo collaborator remove ana -R you/your-repo                  # revoke
taskops board access                                              # what the rule is, and those two lines
```

There is deliberately no `board access add`. A user list here would be a copy of the repository's collaborators, and a copy is exactly what goes stale the day somebody's access is revoked. `admin`, `maintain` and `write` get in; `triage` and `read` do not — the check is GitHub's own `permissions.push`.

The server holds no GitHub credentials. The client sends the token `gh auth token` prints, the server asks GitHub with *that* token who it is (`/user`) and whether it may push to the linked repo, and **discards it** — the request carries no username, so there is nothing to forge. What survives is a session, good for a week, that opens exactly the boards that answered yes. One consequence worth knowing: revoking on GitHub closes the door on their **next login**, not their next request, so a lapsed member keeps access for up to seven days. Contract in `docs/exchange.md`; the guide to hand a new teammate is [docs/remote-developers.md](docs/remote-developers.md).

Opening a locked board in a **browser** does not need the token in the URL: the board answers a navigation without a credential with an access screen — paste the credential once, it is kept in `localStorage`, and every later visit goes straight in. The screen names nothing about what it is locking. A `curl` or a `fetch` still gets the plain `401` JSON it can read, and a local `taskops ui` with no token never shows a screen at all.

Or skip the address bar entirely:

```sh
taskops open              # this project's board, credential included
taskops open --projects   # the server's own page: every board your session reaches
taskops open --print      # just the URL, for a terminal with no browser
```

### What synchronises when — and why you cannot collide

Nothing travels later, and that is the whole design: **there is one store, and every write happens in it.**

| | when | why |
|---|---|---|
| **every write** — claims, closes, new cards, edits, comments, context, policy | **instantly, in the server's database** | two machines writing about one card must resolve *now*; there is no local copy left to disagree with |
| everyone else's work | **on your very next call, whatever it is** | every routed call ends in a pull, so working is syncing |
| what you read | **live from the server**, degrading to your cache with a warning on stderr | refusing to write offline keeps one truth; refusing to *read* offline would make the server a single point of failure for looking at your own board |
| report **files** | on `push`/`pull`, newest stamp wins | they are files, not events; equal-but-different is a `409`, never a silent overwrite |

A claim is a single `INSERT` on one primary key. That is the whole collision story: exactly one machine wins, the loser is told the card is taken and asks for the next one. **If the server is unreachable, a claim fails loudly** — it never quietly falls back to a local claim, because that fallback is precisely the collision the server exists to prevent.

**So there is no rhythm to keep, and no push in it.** This section used to say new cards travelled on the next `push`; that was true before every verb moved behind `/api/rpc`, and it is not any more. Two things are left for `push`, and neither is the board: the **report files**, and the **one-time migration** of a project that already had local history before it had a remote.

---

## Daily reports, unattended

`taskops report sweep` narrates **every day that has ended, has events and has no write-up yet** — so it is safe to run late, early, or twice, and the second run costs nothing because it calls no model. Two triggers put it on autopilot, and neither is cron or launchd:

```sh
taskops schedule install     # writes ~/.claude/scheduled-tasks/taskops-sweep/SKILL.md
taskops schedule status      # what is on disk, and what is still missing
```

**Honest limitation: we write the prompt, not the schedule.** Claude Code keeps a scheduled task's time, folder and model inside the app, so `schedule install` writes the file and then prints the one sentence to say to Claude — *"create a daily scheduled task at 00:05 named taskops-sweep that runs /taskops:sweep in \<this folder\>"*. Until you say it, nothing is scheduled. If Claude Code is not on this machine the command refuses instead of creating a config directory nothing will read.

The **backup trigger needs no setup at all**: the plugin's `SessionStart` hook fires the sweep detached, so opening a session in the morning is what gets yesterday written up. It is bounded on purpose — at most one sweep per project per day (a stamp under `.taskops/`), nothing at all for a project with no history and no remote, silent on every failure, and `TASKOPS_NO_SWEEP=1` turns it off (its sibling `TASKOPS_NO_UI=1` does the same for the local board). It never delays a session: the child is spawned in its own process group and the hook returns in microseconds.

## The web interface

`taskops ui` serves a live board over the same contracts everything else uses. No polling from the browser — a WebSocket (with SSE fallback) pushes every change, and the green dot ticks on each event.

**You never have to start it.** `taskops open` opens this project's board whichever kind of project it is: with a server, the address the team shares; without one, it starts a local `ui` and opens that. It used to refuse a project with no remote and name `taskops ui` instead — a command that *blocks*, in the terminal you were using for something else.

```sh
taskops open              # the board, either kind, credential included
taskops open --print      # the URL instead, for a terminal with no browser
taskops open --projects   # the server's page: every board you can reach
```

The `SessionStart` hook does the same thing for you, so the first line of a session always has somewhere to click — local or remote. Three details, each of which was a bug first:

- the port comes from the OS (`--port 0`), so two projects open at once do not collide. Pinned at 2140, the second one failed inside a detached child: a URL that never answers and no error anywhere.
- `taskops ui` writes where it bound to `.taskops/ui.json` (gitignored) **after** the bind, never before — a note written on intent advertises a port a bind error is about to leave dead.
- a stale note is worse than none, so it is verified twice: the pid is alive **and** the port answers. A pid the kernel has since reused passes the first check on its own, and following it points a browser at whatever program now owns that port.

`TASKOPS_NO_UI=1` turns the offer off — it stops taskops *starting* a board, never looking for one you started yourself.

- **The standing context** — a strip under the header, on **every** screen, carrying the objective. It is the one thing here that is not about a moment, so it is not filed behind a tab: an objective behind a click is an objective nobody reads twice. It updates itself — write a decision in your terminal and it appears without a reload.

  Click it and the rest opens in a **modal with three tabs**, because there are three different questions and one scroll made you do the filtering:

  | tab | answers |
  |---|---|
  | **Project** | what this project has decided — the objective, the decisions, the notes |
  | **Who is on what** | one block per developer: their own objective, and the facts they stated for themselves |
  | **Policies** | what the ENGINE obeys — validated values, not prose, which is how a policy once ended up hidden inside a decision |

  It replaced an inline expansion, and both halves of that were wrong once a real project used it: it pushed the board down — reference material shoving the work off the screen — and it laid facts out as one-line rows in a three-column grid. **An agent can state a paragraph**, and does; a fact is now a block whose text keeps the full width, wraps, and preserves its line breaks, with the scope and the id underneath. The modal is bounded and its body scrolls, so forty decisions do not produce a dialog taller than the screen.

- **Board** — kanban that moves by itself. Click a card for what it is **part of**, its spec, its **subtasks**, the thread, the dependency graph, the commits with their files, and a reply box that reaches agents' inboxes. The `claimed` column is headed **"In progress"**, because that is what it means to somebody looking at the board — a person took the card and is on it. "Claimed" is the engine's word for the lease underneath, and a column heading is not the place to teach it.
- **Activity** — the event log as a history: a filterable timeline, and a roll-up per actor ranked by tasks touched rather than noise made.
- **Reports** — the daily dossiers, rendered. Generate a narration from the browser and **watch it being written**, streamed over the same socket. Only where a `claude` is: a narration is a subprocess of the CLI somebody is logged into, so a board served from a box without one says so rather than failing on a socket nobody is watching.

There is deliberately **no chat panel**. There was one, reaching "whichever session is running the channel" — which assumes exactly one is, and a shared board can have five, each on its own machine. A message about a card goes in that card's thread, on the card, where it is addressed and still findable in three weeks.

**A server's front page** is a separate, deliberately tiny surface: visit the hostname and, once you are signed in, it lists every board that session opens — each with the repository behind it when there is one, and when it last moved. It lists **nothing** without a session, because naming the boards would hand every visitor the enumeration that the per-project bare 404 exists to deny. It has no bundle and no build step on purpose: this is the page that must still answer when something else is broken, so "when did this move" is the log's mtime — one `stat` per board — and not a query into a cache that might be the broken thing.

The UI ships inside the wheel as a committed bundle — `pip install taskops-cli` serves the board with no Node toolchain anywhere.

## Going deeper

| | |
|---|---|
| [docs/workflows.md](docs/workflows.md) | **Every flow, end to end**: starting a board, planning, the claim→review→close loop, landing, sharing, invites, the context, reports, and the two surfaces a person sees. The map — `USAGE.md` is the tutorial. |
| [docs/orchestrator.md](docs/orchestrator.md) | Why the sweep replaced a notification feed, what routing fixed, and the four failures that only appeared with two real sessions running. |
| [docs/remote-developers.md](docs/remote-developers.md) | The guide to hand a new teammate: getting in, the daily rhythm, what their agents do. |
| [docs/agents.md](docs/agents.md) | Specialists a project defines, orchestration, sub-tasks and worktrees, who invokes whom. |
| [docs/reports.md](docs/reports.md) | Why the record matters, the narration, and the sweep that writes itself. |
| [docs/context.md](docs/context.md) | Objectives, decisions and notes — and the slice each card receives. |
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
