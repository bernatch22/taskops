# Context: the standing facts, and the slice each card gets

Where a project is heading, what may never break, and what has already been decided — kept as
**events**, scoped per card, and delivered to agents instead of accumulated in a file nobody
finishes reading.

---

## 1 · The problem this replaces

Most projects keep their direction in `CLAUDE.md` or `AGENTS.md`. It works, and then it does not,
for two measured reasons:

**Standing instructions decay.** The 2026 consensus is that frontier models reliably follow roughly
**150–200 standing instructions** before compliance degrades. A file that grows every time somebody
learns something is a file that is followed less every week. It does not announce the moment it
stops working.

**Agents working from different definitions cannot be reconciled by a supervisor.** When two agents
hold different ideas of what "done" or "the priority" means, no orchestrator on top can fix it — the
disagreement is upstream of the coordination.

The fix both point to is the same: treat context as **infrastructure** — versioned, owned, and
delivered per task in slices — rather than as prose that accumulates.

## 2 · Three kinds of fact

```sh
taskops context objective  "ship the refund flow before the audit"
taskops context invariant  "never a Co-Authored-By trailer in a commit"
taskops context decision   "queues over cron: retries are the whole reason, see tk-9c1e02"
```

| | What it is | Lifetime |
|---|---|---|
| **objective** | what we are chasing now | one at a time — a new one **supersedes** the old |
| **invariant** | what must never break | long-lived; **every** agent gets **every** invariant |
| **decision** | what was decided and *why* | permanent; exists to stop agents re-litigating settled questions |

```sh
taskops context show     # what is in force
taskops context log      # …and everything we ever believed, retired ones marked
taskops context retire <id>
```

`retire` **appends**; it does not delete. An event log has no eraser, and a superseding event is the
honest way to say "we changed our mind" — which is also the only way the log stays a record of how
the project actually thought.

## 3 · Why events, and not a file

Because everything else follows for free:

- **They replicate.** Facts travel with `push`/`pull` and through git, like cards and reports. A
  teammate's new invariant arrives with their work.
- **They have history.** `context log` shows the objective from three weeks ago, and when it changed.
- **They converge deterministically.** The current objective is the latest by `(ts, id)`. The `id` is
  a content hash, identical on every machine, so **a same-timestamp tie elects the same winner
  everywhere**. The test feeds two clones the same two events in *opposite order* and asserts they
  agree — a tie that resolved differently per machine would be a split brain nobody would notice
  until the two sides were pursuing different objectives.
- **They show up where you already look.** `taskops status` prints the objective in force.

## 4 · The slice is the point

An agent does not receive the whole book. `taskops_context` returns, for a specific card:

```
every invariant          ← never filtered. Your RULE 0 reaches every worker, always.
the current objective    ← so a worker knows what the work is FOR
the decisions that match its labels or its edit surface
```

That is the whole mechanism against decay: the file stops growing because nothing has to be in one
file. A collector working on `src/data/**` gets the schema decisions and not the sixty lines about
the frontend, so what it does receive stays inside the budget where it is actually followed.

Unscoped decisions reach everyone. Scoping is opt-in, because a decision nobody can see is worse
than one that is slightly off-topic.

```markdown
# what a worker actually receives with its card

## objective
ship the refund flow before the audit

## invariants
- never a Co-Authored-By trailer in a commit
- migrations are forward-only

## decisions (matching this card)
- queues over cron: retries are the whole reason, see tk-9c1e02
```

## 5 · Context vs. acceptance criteria

They answer different questions and both belong on the work:

| | Scope | Question |
|---|---|---|
| **context** | the project | *"what is true here, whatever I am doing"* |
| **acceptance** | one card | *"what would make THIS done"* |

Acceptance criteria are written in **EARS** — `WHEN <trigger> THE SYSTEM SHALL <response>` — because
lines in that shape map almost one-to-one onto test cases:

```
WHEN a lease expires THE SYSTEM SHALL return the card to ready
WHEN the request times out THE SYSTEM SHALL retry exactly once
```

Validation is deliberately **lax**: a criterion that does not read as EARS is kept with a warning,
never rejected. A card whose criteria are prose is far better than a card that was refused and
never written.

`done` is then checked against them — which criteria were met, and what proves each. That is what
`taskops-verifier` opens first.

## 6 · What this is for, as a team

The context layer is where a project's *judgement* lives, as opposed to its state:

- **A new teammate's agents inherit it on the first `pull`.** They do not need to be told the
  conventions; the invariants arrive with the board.
- **Decisions stop being re-argued.** "Why not cron?" has an answer with a card id attached, and the
  agent reads it before proposing cron again.
- **The objective is visible where work is picked.** `taskops status` shows it above the columns, so
  "is this card still what we should be doing" is answerable without asking anybody.
- **Invariants are the team's non-negotiables, enforced by delivery rather than by hope.** They
  cannot be scoped out of a slice, so no agent can end up not having been told.

Write few of them, and write them as *rules*, not as background. The whole value is that what
arrives is short enough to be followed.
