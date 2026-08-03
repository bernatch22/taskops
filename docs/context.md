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

## 2 · The MILESTONE, and the facts under it

The project's north is not a fact. It is a **milestone**: a chapter with a state, which a person
closes. That is the difference the model turns on — an objective was superseded by a newer sentence
and nothing recorded whether it was ever reached, so a board with eight of them could not answer
"what have we shipped".

```sh
taskops milestone new "ship the refund flow before the audit" --horizon 2026-09-01
taskops milestone review 31b0b89a -m "las tres cards cerradas"    # an agent REPORTS
taskops milestone done   31b0b89a                                 # a PERSON verifies
```

Everything else is a fact filed under a chapter, or under a person, or over the whole project.

```sh
taskops context rule     "never a Co-Authored-By trailer in a commit" --project
taskops context decision "queues over cron: retries are the whole reason, see tk-9c1e02"
taskops context note     "el importador tiene tres etapas: leer, validar, cargar"
taskops me objective     "the date parser, no regex"       # yours, and nobody types their own id
taskops me note          "I run pytest -x, not the whole suite"
```

| | What it is | Lifetime |
|---|---|---|
| **milestone** | what we are shipping now | until a PERSON says it was reached. Several active at once |
| **rule** | what must never break | `--project` makes it outlive every chapter; **every** agent gets it |
| **decision** | what was decided and *why* | its chapter's, unless `--project`. Stops agents re-litigating |
| **note** | standing, and neither of those | always its chapter's — a permanent note is a rule |
| **me objective** | what one PERSON is chasing | one each, and a newer one supersedes theirs alone |

```sh
taskops context                      # what is in force: the project's rules, then each chapter
taskops me                           # your page
taskops context --milestone c5df2915 # what ONE chapter settled — including a closed one
taskops context log                  # …and everything we ever believed, retired ones marked
taskops context retire 0829cfb9      # a prefix is enough — the eight characters printed
```

## 2b · Three dimensions of scope

`--labels` / `--files` narrow a fact by SUBJECT. The noun narrows it by PERSON: `taskops me` files
it under whoever ran it, and it reaches their sessions and nobody else's. And the chapter narrows it
by TIME: a fact belongs to the milestone open when it was written.

    a project rule               ──▶ everybody, forever
    a decision in this chapter   ──▶ every card in it — and NOBODY once it is reached
    a decision  [db]             ──▶ cards in its chapter that touch the database
    ana's own objective          ──▶ ana's sessions and her agents
    ana's note                   ──▶ ana

**The chapter is what stops a context growing with the YEAR.** A decision taken in March leaves
every slice the day somebody verifies the March chapter, and nobody had to retire it. That is the
one form of decay a per-card slice could not fix on its own: subject scope keeps a context
relevant, and only a lifetime keeps it small.

A worker is handed the project's facts **plus its own developer's**, so a slice grows by ONE
whatever the size of the team — which is the whole reason `owner` is a filter rather than a
label. Three developers each with an objective does not make every agent read four; past
~150-200 standing instructions compliance decays, and a page that grew with the team would make
every agent slightly worse each time somebody joined.

An agent reads what the person who spawned it set: `agent:ana/w1` inherits `dev:ana`'s, the same
"one person with two hands" comparison `reviewer: peer` makes.

`retire` **appends**; it does not delete. An event log has no eraser, and a superseding event is the
honest way to say "we changed our mind" — which is also the only way the log stays a record of how
the project actually thought.

## 3 · Why events, and not a file

Because everything else follows for free:

- **They replicate.** Facts travel with `push`/`pull` and through git, like cards and reports. A
  teammate's new decision arrives with their work.
- **They have history.** `context log` shows what we believed three weeks ago, and when it changed;
  `taskops milestone list --all` shows every chapter this board has ever had, reached or abandoned.
- **They converge deterministically.** The current objective is the latest by `(ts, id)`. The `id` is
  a content hash, identical on every machine, so **a same-timestamp tie elects the same winner
  everywhere**. The test feeds two clones the same two events in *opposite order* and asserts they
  agree — a tie that resolved differently per machine would be a split brain nobody would notice
  until the two sides were pursuing different objectives.
- **They show up where you already look.** `taskops status` and the session's bottom bar print the
  milestone in force.

## 4 · The slice is the point

An agent does not receive the whole book. `taskops_context` returns, for a specific card:

```
the project's rules      ← never narrowed. Your RULE 0 reaches every worker, always.
its MILESTONE            ← one chapter — the card's own, never all of the active ones
the facts under it       ← the decisions and notes matching its labels or its edit surface
your own objective       ← whose? the card's AUTHOR's. See below
```

That is the whole mechanism against decay: the file stops growing because nothing has to be in one
file. A collector working on `src/data/**` gets the schema decisions and not the sixty lines about
the frontend, so what it does receive stays inside the budget where it is actually followed.

Unscoped decisions reach everyone. Scoping is opt-in, because a decision nobody can see is worse
than one that is slightly off-topic.

**Whose owned facts ride along: the card's AUTHOR's.** For a card being worked that is its holder.
For a card in `review` it is whoever handed it over — read from the log, because routing writes the
chosen *reviewer* into `assignee`, so the field no longer names the author by then. A verifier from
another developer therefore reads the objective the work was done for, and only that one: the slice
still grows by one person, never by the reader as well.

```markdown
# what a worker actually receives with its card

## Rules — the project's. Every card, every milestone, no exceptions.
· never a Co-Authored-By trailer in a commit
· migrations are forward-only

## ◆ Milestone in force — ship the refund flow before the audit      by 2026-09-01
   4 card(s) · 1 done · 2 ready
   decisions   queues over cron: retries are the whole reason, see tk-9c1e02
   yours       the date parser, no regex
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
  conventions; the standing decisions arrive with the board.
- **Decisions stop being re-argued.** "Why not cron?" has an answer with a card id attached, and the
  agent reads it before proposing cron again.
- **The objective is visible where work is picked.** `taskops status` shows it above the columns, so
  "is this card still what we should be doing" is answerable without asking anybody.
- **Unscoped decisions are the team's non-negotiables, enforced by delivery rather than by hope.** They
  cannot be scoped out of a slice, so no agent can end up not having been told.

Write few of them, and write them as *rules*, not as background. The whole value is that what
arrives is short enough to be followed.
