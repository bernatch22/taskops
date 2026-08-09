# taskops — what the product is, and every attribute in it

A brief for designing the interface. This document says **what exists and what
each thing carries**; it makes no design decisions. Unlike its neighbours in
`docs/`, it is not a dated post-mortem: it is a live reference of the data
model and is kept true. `src/taskops/core/types.py` is the arbiter — if the two
disagree, that file is right.

---

## 1. The subject, in one line

**Trello × GitHub, for AI agents.** A shared work board where the workers are
Claude Code agents running in parallel, and one human decides what ships.

That sentence is the whole theme, and the two halves are literal:

* **Trello**: milestones hold cards, cards hold the work, cards move between
  states and belong to somebody.
* **GitHub**: every card is a real git branch with a real working directory,
  real commits bound to it, and a real merge into an integration branch. Work
  is code, and the board knows which code.

What makes it *not* Trello: **the members are agents, not people.** A card is
picked up by a process that may die mid-task; several agents work at the same
instant in different directories; and a human orchestrator assigns, reads,
and merges but never holds a card. The interface's job is to make a room of
autonomous workers legible to one person.

Three vocabulary notes, because they recur everywhere:

| term | means |
|---|---|
| **orchestrator** | the human's session, id `dev:<name>`. Plans, assigns, merges. Never holds a card. |
| **worker** | a spawned sub-agent, id `agent:<dev>/<name>` e.g. `agent:berna/w1`. Holds exactly one card, works in its own directory. |
| **card** | one unit of work, id `tk-` + 6 hex e.g. `tk-a11ffa`. Also the name of its git branch. |

---

## 2. The one idea that shapes every screen: stored vs derived

Only **three** facts are ever stored about a card: `open`, `done`, `dropped`.
Everything else the board says is **computed at read time** and never written
down.

```
STORED (a row)        DERIVED (recomputed on every read, never stored)
open                  ready    = open ∧ no unfinished dependency ∧ nobody owns it
done                  doing    = somebody holds a live LEASE on it, right now
dropped               blocked  = a dependency has not closed yet
review: true          stalled  = it has an owner, but nobody is running it
(a flag, not a state) mention  = you were named in a comment ∧ you have not written since
                      review    = handed in ∧ nobody has judged it   (only if review: true)
                      reviewing = a verifier holds a live REVIEW lease on it
                      changes   = the last verdict asked for changes ∧ nobody is on it
```

Why this matters for the interface: **`doing` is a heartbeat, not a status.**
A worker holds a *lease* that expires 15 minutes after its last activity, and
every call it makes renews it. If the agent's process dies, nothing is written
anywhere — the lease simply lapses and the card stops being `doing` on its own,
becoming `stalled`. There is no "stuck" state to clear and no repair action,
because nothing was ever written that could be wrong. The review states work
identically: a verifier that dies stops renewing its review lease and the card
returns to `review` on its own.

**Review is optional and off by default.** A card with `review: false` (the
default) never shows any review state; a board that never turns it on behaves
exactly as if the feature did not exist.

So the board is **live by nature**: the same card can change how it presents
itself with no event, no user action, and no write — just time passing. Two
attributes exist to express that, and both are on every board row:

* `since` — when the current holder took it (a lease timestamp), or when the
  card last changed.
* `quiet_for` — seconds since the owner last said anything. `null` when
  somebody is actively holding it. This is what makes `stalled` actionable: not
  a guess about why, a fact.

A `reviewing` row carries a third, because that card has TWO leases held by two
actors: `review_since` — when the VERIFIER's lease was acquired. `since` on the
same row is still the work lease's, and the worker may well be alive beside the
verifier, so the two are not interchangeable: counting the review lease down
from `since` yields a floor that reads zero while the review is still live.

---

## 3. The entities, with every attribute

### 3.1 Card — the unit of work

The central object. This is the exact row and the exact wire format:

```json
{
  "id": "tk-a11ffa",
  "title": "invoice model",
  "spec": "the Invoice dataclass",
  "criteria": ["amounts are Decimal", "round half up"],
  "status": "open",
  "review": false,
  "priority": 1,
  "milestone": "ms-2be633",
  "parent": null,
  "after": [],
  "files": ["src/models.py"],
  "labels": ["backend", "money"],
  "assignee": "agent:berna/w1",
  "created_by": "dev:berna",
  "created": 1769999999.998,
  "updated": 1770000000.0
}
```

| attribute | type | what it is |
|---|---|---|
| `id` | string | `tk-` + 6 hex. Also the git branch name and the directory name. Stable forever. |
| `title` | string | A label, one line. **Not** the brief. |
| `spec` | string | The brief: what "done" looks like, what must not change, where to look. Free text, often long (thousands of characters), sometimes empty. The most important field. |
| `criteria` | string[] | The acceptance checklist — the other half of the spec. Usually 0–5 short lines. Often empty. |
| `status` | enum | `open` \| `done` \| `dropped`. **Only these three.** |
| `review` | bool | This card must pass review before it closes. **Default `false`** — inherited from the milestone's `reviews` flag at planning; the card's own value wins. A durable flag, never a state. |
| `priority` | int | `0` urgent → `3` someday. Default `2`. |
| `milestone` | string | `ms-` + 6 hex. Every card belongs to exactly one. |
| `parent` | string \| null | The **epic** this card is a subtask of. Forms a tree. |
| `after` | string[] | Card ids that must close before this one is workable. Forms a DAG (cycles are refused). |
| `files` | string[] | The edit surface as the planner understands it. A hint used to warn about collisions — never a lock. |
| `labels` | string[] | Free tags for routing and search, e.g. `backend`, `money`. |
| `assignee` | string | Who the card is **for**, `""` when it is in the open pool. Note: this is *not* a claim — see `holder`. |
| `created_by` | string | Actor id. |
| `created` / `updated` | float | Unix seconds. |

**`assignee` vs `holder` is a real distinction, not a synonym.** `assignee` is
durable ("this is yours"); `holder` is live ("somebody is on it this minute").
A card can have an assignee and no holder — that is exactly `stalled`.

### 3.2 Milestone — the chapter

```json
{
  "id": "ms-2be633",
  "title": "MVP facturador",
  "goal": "read a bank CSV and issue invoices with VAT",
  "rules": ["Decimal, never float"],
  "criteria": ["a bank CSV in, a valid invoice out, end to end"],
  "reviews": false,
  "branch": "ms/mvp-facturador",
  "status": "open",
  "created": 1770000000.0
}
```

| attribute | type | what it is |
|---|---|---|
| `id` | string | `ms-` + 6 hex. |
| `title` | string | The chapter's name. |
| `goal` | string | **Why** this chapter exists. One or two sentences; travels into every worker's context. |
| `rules` | string[] | Constraints that hold for **every** card in the chapter, e.g. "Decimal, never float", "no migrations in this milestone". 0–5 short lines. |
| `criteria` | string[] | What the **chapter** is accepted against — `rules`' sibling. Travels into every take like `rules`, and is shown to the human when the milestone lands, which refuses until they answer `criteria_met=true`. Never judged by the machine. |
| `reviews` | bool | Cards planned into this chapter default to `review: true`. A default, not a rule — per-card `review` always wins. Default `false`. |
| `branch` | string | `ms/<slug>`, the integration branch. Computed once at creation and stored; renaming the milestone never moves it. |
| `status` | enum | `open` \| `done` \| `dropped`. |

Several milestones can be open at once. When they are, the board deliberately
refuses to pick one and names them all.

### 3.3 Actor — who is speaking

Two shapes, and the grammar is strict:

| form | role | example |
|---|---|---|
| `dev:<name>` | orchestrator (human) | `dev:berna` |
| `agent:<dev>/<name>` | worker (AI) | `agent:berna/w1` |

A worker's name is bound to the **run** of a card, not to a person and not to a
slot: `w1` today is not `w1` yesterday, and an agent with no card is history,
never "free" — there is no roster and no capacity anywhere in this system
(`ARCHITECTURE.md` §11). Names are lowercase `[a-z0-9._-]`, 1–40 chars.

### 3.4 Lease — the live claim

```json
{
  "task": "tk-a11ffa",
  "actor": "agent:berna/w1",
  "branch": "tk-a11ffa",
  "acquired": 1770000000.0,
  "expires": 1770000900.0
}
```

15-minute TTL, renewed by every call the holder makes. `null` when nobody holds
the card. This single row is what makes a card `doing`.

A card can carry a **second lease of the same shape — the review lease** — held
by a *different* actor at the same time: the worker stays alive while the
verifier reads. That second row is what makes a card `reviewing`, and it lapses
by the same non-mechanism.

### 3.5 Event — the thread

Every card has a complete, ordered, never-truncated history. An event:

```json
{
  "id": "2703b9e65c56d8da5619df95548c866d",
  "task": "tk-a11ffa",
  "actor": "agent:berna/w1",
  "kind": "comment",
  "body": { "text": "Decimal or float?", "mentions": ["dev:berna"] },
  "ts": 1770000000.0
}
```

Thirteen kinds (`core/types.py::KINDS` is the registry), each with its own
`body`:

| kind | body | reads as |
|---|---|---|
| `created` | `{card: {…}}` | the card was planned |
| `edited` | `{field, to}` | a field changed (`spec`, `files`, `assignee`, …) |
| `claimed` | `{branch}` | a worker took it |
| `released` | `{note}` | a worker handed it back, with how far it got |
| `status` | `{to, reason?, no_code?}` | closed, dropped or reopened |
| `comment` | `{text, mentions?}` | somebody said something |
| `commit` | `{sha, subject, files, branch}` | a real git commit landed on it |
| `merged` | `{into, sha}` | integrated into the milestone branch |
| `milestone` | `{op, …}` | chapter-level fact |
| `project` | `{op, …}` | a board-level fact about the REPO (`op=remote`: where it lives on the web), on `task: "project"` |
| `submitted` | `{note}` | the worker handed the card in for review |
| `reviewed` | `{verdict, note}` | a verdict: `pass` or `changes`, with the reviewer's words |

A **mention** is not its own kind — it is an optional `mentions: string[]` on a
`comment` body.

A `commit` does not need a card: **a commit made outside any card is still
recorded**, on the board-level thread (`task: "project"`). Nobody is forced to
take a card to commit — the board just knows that sha happened, and that is all
it knows about it.

---

## 4. The board — nine groups, ordered by the move each one needs (plus `done`)

The board's whole organising principle: **cards are grouped by what should
happen to them next**, not by status. The order below is the order of urgency.

| group | contains | the move |
|---|---|---|
| `merge` | done, not yet integrated | integrate it into the milestone branch |
| `mentions` | somebody addressed **you** and you have not answered | answer on that card |
| `review` | handed in, nobody checking | spawn a verifier |
| `changes` | a reviewer asked for changes, nobody on it | back to its worker |
| `stalled` | it has an owner, nobody is running it | hand it to somebody else |
| `take` | ready — no blockers, no owner | assign it to a worker |
| `doing` | somebody holds it right now | nothing; this is healthy |
| `reviewing` | a verifier is on it right now | nothing; this is healthy |
| `blocked` | waiting on a dependency | close the blocker |

The payload carries a tenth key, `done`, LAST and deliberately not a move: it is
the only place finished, already-integrated work is visible at all — capped and
newest-first, because a chapter is bounded and a board is not (`verbs/pulse.py`).

`review` sits above `stalled` because finished work nobody is checking is more
blocking than work nobody has started; `changes` right after it, because the
fix is usually seconds of an agent's time and it unblocks a merge. The three
review groups only ever appear on a board that turned review on.

A **card row** in any group:

```json
{
  "id": "tk-a11ffa",
  "title": "invoice model",
  "priority": 1,
  "assignee": "agent:berna/w1",
  "holder": "agent:berna/w1",
  "since": 1770000000.0,
  "quiet_for": null,
  "files": ["src/models.py"],
  "labels": ["backend", "money"]
}
```

`blocked` rows carry one extra: `waiting_on: string[]` — the card ids in the
way. A `changes` row carries `text` — the reviewer's words, verbatim — and a
`reviewing` row's `holder` is the verifier.

A **mention row** is shaped differently — it carries what was *said*, not the
card's own metadata:

```json
{
  "id": "tk-a11ffa",
  "title": "invoice model",
  "by": "agent:berna/w1",
  "text": "Decimal or float?",
  "ts": 1770000000.0
}
```

Mentions are **per viewer**: the orchestrator sees what was addressed to
`dev:berna`, each worker sees its own. They are also the one group that ignores
the milestone filter — a mention addresses a person, not a chapter. A mention
clears itself the moment its recipient writes anything on that card. There is
nothing to mark as read.

The board payload also carries:

* `milestone` — the focused chapter, or `null`.
* `milestones` — every open chapter (`id`, `title`, `goal`, …), for when there
  is more than one.
* `team` — presence: `[{actor, seen, ago}]`, everyone seen in the last 24h.
* `hours` — optional, only when a time window was requested: worked seconds per
  actor, per calendar day.
* `pulse` — the one-line heartbeat that also rides at the foot of every single
  agent response:

```json
{
  "milestone": "MVP facturador",
  "goal": "read a bank CSV and issue invoices with VAT",
  "counts": { "doing": 1, "ready": 1, "blocked": 1, "stalled": 0, "done": 0 },
  "mentions": 1
}
```

---

## 5. The card view — everything about one card

Opening a card returns a complete dossier. Every field, with real values:

| field | type | what it is |
|---|---|---|
| `card` | Card | the object from §3.1 |
| `state` | string | the **derived** state: `ready` \| `doing` \| `blocked` \| `stalled` \| `review` \| `reviewing` \| `changes` \| `done` \| `dropped` |
| `milestone` | Milestone | the chapter, resolved — including its `goal` and `rules` |
| `epic` | object \| null | the parent card **resolved**: `{id, title, spec, status}` |
| `history` | Event[] | the entire thread, oldest first, never truncated |
| `resume` | string | the previous worker's handover note, verbatim. `""` if none |
| `commits` | object[] | `[{sha, subject, files, branch}]` — real commits bound to this card |
| `merged_into` | string | the milestone branch it reached, or `""` |
| `seconds` | float | time actually worked on it, derived from event timestamps |
| `blockers` | object[] | `[{id, title, status, assignee}]` — what it waits on |
| `blocks` | object[] | same shape — what waits on it |
| `subtasks` | object[] | same shape — its children |
| `collisions` | object[] | `[{id, title, files, holder, started}]` — other **live** cards claiming the same files |
| `elsewhere` | object[] | `[{id, title, holder, milestone}]` — who else is working right now |
| `standing` | object \| null | where it stands with its reviewer: `{submitted_at, submitted_by, verdict, verdict_by, note}` — `null` unless it was handed in |
| `lease` | Lease \| null | who holds it and until when |
| `branch` | string | `tk-a11ffa` |
| `worktree` | string | `.taskops/trees/tk-a11ffa` |

**The order in which these are presented is itself load-bearing**, because the
agent-facing version is read top-down and may be abandoned early. Things that
change *what you do before you start* come before the spec: collisions, the
resume note, the epic, the chapter's rules. This ordering exists because in the
previous system a collision warning placed below a long spec was skipped, and
the cost was two agents rewriting each other's work.

---

## 6. Git: every card is a branch, and every branch is a directory

This is the GitHub half, and it is literal.

```
main ──────────────────────────────▶  the HUMAN decides: a PR, or landing the milestone whole
  └─ ms/mvp-facturador ──┬────┬────▶  the ORCHESTRATOR integrates, card by card
                         │    │
                   tk-a11ffa  tk-d34294   ← one WORKER each, one DIRECTORY each
```

Branches are **inhabited, never switched**. Each card's branch is pinned to its
own directory for life:

```
<repo>/                             main            the human's checkout, never moved
<repo>/.taskops/trees/_ms-mvp/      ms/mvp          integration
<repo>/.taskops/trees/tk-a11ffa/    tk-a11ffa       worker w1 lives here
<repo>/.taskops/trees/tk-d34294/    tk-d34294       worker w2 lives here
```

Two agents on two cards are two directory trees that share nothing, which is
why they cannot overwrite each other. The worst case when two cards touch the
same file is a merge conflict at integration time — never lost work. That is
what `collisions` warns about.

### 6.1 On rendering the worktree

**Yes — each card has exactly one branch and one directory, and that mapping is
total and permanent.** Every card exposes both today (`branch`, `worktree`), so
they can always be shown.

What the board can show about that tree **right now, with no new machinery**:

* the branch name and the absolute/relative worktree path;
* every commit on it — `sha`, `subject`, and **the exact list of files each one
  touched**;
* whether it has been integrated, and into which branch (`merged_into`);
* the planner's intended edit surface (`files`) versus what the commits actually
  touched — a genuinely useful comparison that needs no new data at all.

**Diffs ARE available, and by the second of those two routes** (decided
2026-08-08, `ARCHITECTURE.md` §16): the board still stores events and never a
repository, but the window is served by `taskops ui`, which by construction
stands inside a checkout — so it mounts a read-only `/git` door
(`http/gitdoor.py`, `gitwork/diff.py` + `gitwork/patch.py`) and the dossier draws **Files changed**
for the card as a PR, plus each commit's own patch. Nothing is stored: the door
derives on demand. A host that is NOT in a checkout (`taskops serve`) mounts no
such door and says so, and the UI falls back down one declared cascade
(`ui/src/links.tsx::cascade`): numstat from the event → the patch → the forge
link → one honest sentence.

Still **not** available: live `git status`, and any ref this reader's own clone
has not fetched — that one is answered in words, naming the `git fetch origin
tk-<id>` that brings it, never fetched on the reader's behalf.

---

## 7. What the interface can do, and the one thing it must not

The board's write surface is deliberately narrow. Managing work is what the
agents' tools are for; a second way to move a card is a second way for the two
to disagree.

**Read** — everything in §4 and §5, live. The connection is a signal, not a data
feed: when anything changes the interface is poked and refetches, so it can
never display something the board never said.

**Write** — exactly one thing exists today, and it is not moving a card: a
**comment box with a mention picker**. A human watching the board can address a
working agent by name, and that agent sees it on its very next action. This is
the human's channel into a room of running agents.

**Never**: moving a card between states by hand, editing a spec, merging, or
flipping `review` — on a card or on a milestone. Requiring review is a decision
about the work, so it is made where the work is planned (`taskops_plan`) or
changed (`taskops_update`), by an agent, through the same door as everything
else. The interface *shows* the three review groups and the reviewer's verdict;
it does not decide them.

---

## 8. Everything at a glance

```
Milestone  id · title · goal · rules[] · criteria[] · reviews · branch · status
  └─ Card  id · title · spec · criteria[] · status · priority · parent · after[]
           files[] · labels[] · assignee · review · created_by · created · updated
       ├─ derived:  state (ready|doing|blocked|stalled|review|reviewing|changes|done|dropped)
       ├─ Lease     actor · branch · acquired · expires        ← makes it `doing`
       ├─ Event[]   created|edited|claimed|released|status|comment|commit|merged
       │             |milestone|project|submitted|reviewed
       ├─ Worktree  branch tk-<id> · directory .taskops/trees/tk-<id>
       └─ relations blockers · blocks · subtasks · epic · collisions

Actors     dev:<name> orchestrator (human)  ·  agent:<dev>/<name> worker (AI)
Board      9 move groups: merge · mentions · review · changes · stalled · take · doing · reviewing · blocked
           + done (history, capped, newest first — not a move)
Pulse      milestone · goal · counts{doing,ready,blocked,stalled,done} · mentions
```
