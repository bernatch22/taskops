# Working on a shared board, from your own machine

This is the guide for the second, third and tenth developer on a project — the ones who did not
set up the server and should not have to care that there is one. It covers what you type, what
your agents do, and the handful of rules the system enforces rather than suggests.

If you are setting the server up, you want the README's *Working as a team* section instead.

---

## 1 · Get in

Nobody hands out tokens. The board is linked to a GitHub repository, and **push access to that
repository is the invitation** — the server asks GitHub, with your own token, whether you may push,
and never stores it.

```sh
pip install taskops-cli                        # the command is `taskops`
taskops login https://boards.example.com       # takes your token from `gh auth token`
```

```
signed in to https://boards.example.com as your-github-login
  1 project(s) — run one of these in the matching checkout:
    payments   taskops remote add https://boards.example.com/payments
```

Then, in your checkout of the project:

```sh
taskops remote add https://boards.example.com/payments   # no --token: it uses your session
taskops pull                                             # the whole board materialises locally
taskops open                                             # …and it opens in your browser
```

Your session lives in `~/.taskops/sessions.json` at `0600`, outside every repository, and lasts a
week. When it lapses you get a sentence telling you to run `login` again, not a mystery 401.

**Point your agents at the same board.** Once per machine:

```sh
claude mcp add taskops -- python3 -m taskops.transports.mcp
```

Install the plugin from the project's `plugin/` directory too — that is what wires the git hooks
and the `/taskops:*` skills.

---

## 2 · The loop, per day

```sh
taskops pull        # when you sit down: everyone else's work arrives
taskops status      # where the project stands, in one screen
# …work…
taskops push        # when you stand up: yours goes up, theirs comes down
```

That is the whole rhythm, and **nothing in between is needed** — because the writes that could
collide never waited for a push in the first place. See §4.

`taskops status` is the one read worth making before you start:

```
╭───────────────────────────── taskops ──────────────────────────────╮
│   project  payments  ·  dev:you                                    │
│ objective  ship the refund flow before the audit                    │
│     board  41 card(s) · 6 ready · 3 in flight · 1 blocked · 31 done │
│     yours  tk-4f2a9c  refund idempotency        lease 11m          │
│     fleet  agent:ana/w1  tk-9c1e02              lease 2m ⚠         │
│   reports  17 event(s) today · yesterday not narrated               │
│      sync  ⇡ 5 to push · last pull 2h ago                          │
╰────────────────────────────────────────────────────────────────────╯
```

---

## 3 · What your agents do

You mostly do not drive this. You say what you want; the agent uses the MCP tools.

> Claim the next card and start.

```
taskops_next  →  the spec, the branch to create, its inbox, and a warning naming
                 anyone else currently editing the same files
```

It works, commits, and closes with `taskops_update`. Two rules are **enforced**, not suggested:

- **A commit belongs to a claimed card.** An agent holding no card cannot commit — the hook
  refuses and prints the fix. The `Task: tk-4f2a9c` trailer is added for it; it never writes one.
- **`done` requires evidence** — a commit bound to the card, and, when the card carries acceptance
  criteria, which of them were met and what proves each.

**When the work belongs to no card** — a bug it tripped over, a fix you asked for mid-review — the
agent does not need you to plan anything:

```
taskops_capture title="fix the refund timeout" spec="DONE = the retry test passes"
  → created tk-4987b6, claimed, commit on tk/tk-4987b6/fix-the-refund-timeout
```

The full agent surface, nine tools:

| Tool | For |
|---|---|
| `taskops_next` | claim work |
| `taskops_update` | progress, comment, close, hand off |
| `taskops_ask` | read one card, or search |
| `taskops_capture` | one unplanned card, claimed in the same call |
| `taskops_plan` | decompose into several cards with dependencies |
| `taskops_context` | the standing facts this card must respect |
| `taskops_report` | the board, a standup, a day |
| `taskops_dispatch` | hand cards to sub-agents, one each |
| `taskops_recover` | release cards held by workers that went silent |

### Two agents, one repository

Each claimed card gets its own branch (`tk/<id>/<slug>`) and, when workers run in parallel, its own
**git worktree** under `.taskops/trees/`. A lease says who owns the *card*; the worktree is what
keeps two agents from overwriting each other's bytes.

---

## 4 · Why you cannot collide with another developer

Not everything travels at the same moment, and the split is the design:

| | when it travels | why that is safe |
|---|---|---|
| **claim** and **close** | **immediately, in the server's database** | the only writes that can collide, resolved on the spot |
| new cards, edits, comments | on the next `push` | ids are content-hashed — two people planning at once produce a union, never a conflict |
| everyone else's work | on `push` / `pull` | events are facts about the past; importing one twice is a no-op |
| reports and narrations | on `push` / `pull` | newest stamp wins; equal-but-different is a `409`, never a silent overwrite |

A claim is a single `INSERT` on one primary key. Exactly one machine wins; the loser is told the
card is taken and asks for the next one.

**If the server is unreachable, a claim fails loudly.** It never quietly falls back to a local
claim — that fallback is precisely the collision the server exists to prevent.

---

## 5 · Reading what happened

Reports are **projections of the event log**, so they cannot be stale and cannot flatter anyone.

```sh
taskops report                      # the board
taskops report standup --since 24h  # what changed, per actor, and what needs a human
taskops report day --digest         # one day, narrated by Claude: asked vs delivered
taskops report range --last 7d
taskops report all --digest         # the whole project, as a document
```

`--digest` streams into your terminal as it is written, uses your existing Claude Code login (never
an API key), and lands in `.taskops/reports/<label>.md`, committed like source.

You will rarely run it by hand. `taskops report sweep` narrates every day that has **ended**, has
events and carries no prose yet — and does nothing when there is none, so it is safe on any
schedule and safe twice. It fires on its own when you open a session; `taskops schedule install`
sets up the Claude Code scheduled task for the unattended path.

---

## 6 · Where the project is heading

```sh
taskops context show        # the objective in force, the invariants, the decisions
taskops context log         # …and what we used to believe
```

These are events like everything else, so they replicate with your `push` and keep their history.
Agents receive the **slice** that applies to their card — every invariant, the current objective,
and the decisions matching its labels or files — rather than a document that grows until nobody
follows it.

---

## 7 · When something goes wrong

| Symptom | What it means |
|---|---|
| `session expired — run taskops login <url> again` | your week is up. One command. |
| a claim raises instead of succeeding | the server is unreachable. **Do not** work around it locally — that is the collision this prevents. |
| `commit blocked — … holds no task` | claim one (`taskops_next`) or make one (`taskops_capture`). The message names both. |
| `409` on a report | somebody narrated the same day elsewhere. Pull, read theirs, and re-narrate only if yours adds something. |
| a card claimed by an agent that died | `taskops recover` returns lapsed leases to the pool. |
| the board looks stale | `taskops pull`. If it still looks wrong, `taskops sync` rebuilds the cache from the event log — the log is truth, the cache is disposable. |

Nothing here loses work: `.taskops/events.jsonl` is append-only and committed, and every view is
derived from it.
