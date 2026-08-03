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

So there is nothing to be granted here: if you can push to the repository, you are on the board.
Somebody who cannot is added the way they would be added to the code —
`gh repo collaborator add <them> --permission push -R owner/repo` — and `taskops board access`
prints that line rather than offering a command of its own, because a user list kept here would
be a copy of the repository's and copies go stale the day access is revoked.

```sh
pip install taskops-cli                        # the command is `taskops`
taskops login https://boards.example.com       # takes your token from `gh auth token`
```

```
signed in to https://boards.example.com as your-github-login
  1 project(s) — run one of these in the matching checkout:
    payments   taskops remote add https://boards.example.com/payments
```

Then, in your clone of the project:

```sh
taskops join        # no URL: the repository carries its board's address
taskops open        # …and it opens in your browser
```

```
joined https://boards.example.com/payments
  git hooks: post-commit, post-checkout, post-merge, pre-commit, prepare-commit-msg
you are on the board — `taskops attention` says what it is waiting on
```

That is the whole of it: `join` inits the store, wires the git hooks and the MCP, configures the
remote from your session and fills the board. The address comes from `.taskops/board.json`,
which is committed and holds nothing but a URL — the same way `git clone` already knows its
remote. If your clone predates that file, paste the link once (`taskops join <url>`) and it is
written for everybody after you.

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
taskops status      # where the project stands, in one screen
# …work…
```

**That is the whole rhythm, and there is no push in it.** Every write executes in the server's
store and every read comes from it, so your board is never behind and nobody is waiting for you
to send anything. `push` and `pull` still exist for the two things no call carries — the report
files, and a project's local history the first time it gets a remote — but a normal day never
needs either. See §4.

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

Because nothing waits to travel. There is one store and every write happens in it:

| | when it travels | why that is safe |
|---|---|---|
| **every write** — claims, closes, new cards, edits, comments, context, policy | **immediately, in the server's database** | the writes that could collide are resolved on the spot instead of merged afterwards |
| everyone else's work | **on your very next call, whatever it is** | every routed call ends in a pull, so working IS syncing |
| what you read | **live from the server**, degrading to your cache with a warning on stderr | refusing to WRITE offline keeps one truth; refusing to READ offline would make the server a single point of failure for looking at your own board |
| report **files** (`.taskops/reports/*.md`) | on `push` / `pull` | they are files and not events — newest stamp wins, and equal-but-different is a `409`, never a silent overwrite |

**So there is no board to push.** This table used to say new cards travelled on the next `push`,
and that was true before every verb moved behind `/api/rpc`. It is not any more: `plan`, `edit`,
`assign`, `acceptance`, `pick`, `recover`, `context` and `policy` all execute in the server's
store, and `next` and `update` always did. Two things are left for `push`, and neither is the
board: the **report files**, and the **one-time migration** of a project that already had local
history before it had a remote.

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
taskops context show        # the objective in force, the decisions, the notes
taskops context log         # …and what we used to believe
```

These are events like everything else, so they replicate with your `push` and keep their history.
Agents receive the **slice** that applies to their card — the current objective, the unscoped decisions,
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
