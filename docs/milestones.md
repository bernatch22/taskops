# Milestones — the model

A design note, written before the code.

---

## 1 · The shape

```
  Project ──has_many──▶ Rule            permanent.  Outlives every milestone.
          ──has_one───▶ Policy          a value the ENGINE obeys, validated
          ──has_many──▶ Decision        a dev may add one at project level
          ──has_many──▶ Milestone
                            │
                            ├──has_many──▶ Task (card)
                            ├──has_many──▶ Rule       ── only while this milestone is in force
                            ├──has_many──▶ Decision
                            ├──has_many──▶ Note
                            └──has_many──▶ DevObjective   at most one per dev
```

**A rule exists at both levels, and that is the whole answer to "does a rule survive?".** It
survives if you put it on the PROJECT and it dies with the chapter if you put it on the MILESTONE
— so the lifetime is declared where the fact is written, by the person who knows which it is. No
triage at close time, no default to guess at, and nothing that decays into the wrong bucket
because somebody was in a hurry.

```
  "cero dependencias fuera de la stdlib"     ──▶ Project.  True in 2027.
  "esta tanda la escribimos sin async"       ──▶ Milestone. True until it ships.
```

**Every card belongs to exactly one milestone.** That is the new invariant, and it does two jobs.
It makes a milestone a todo-list rather than a slogan — its cards ARE its items, so "how far along
is it" is a count and not an opinion. And it is what BOUNDS a worker's slice: the facts a worker
reads are its own card's chapter's, one of them, whatever number of chapters the board is running.
The bound is a property of the reader, not of the board.

---

## 2 · The states

A milestone moves exactly like a card, and it is the same argument: whoever did the work does not
get to be the one who says it is done.

```
   ┌───────────┐   start      ┌────────────┐   review     ┌────────────┐
   │  PLANNED  │─────────────▶│  IN_FORCE  │─────────────▶│   REVIEW   │
   └───────────┘  an agent may└────────────┘  an agent    └────────────┘
                                    ▲          may            │      │
                                    │                    done │      │ reject
                             reject sends it back             ▼      ▼  a person,
                             a person, with a reason    ┌─────────┐   back to
                                                        │ REACHED │   IN_FORCE
                                                        └─────────┘
   cancel — a person, from PLANNED / IN_FORCE / REVIEW ────────────▶  ABANDONED
```

- **An agent may create, start, update and report.** Planning one, beginning it, working under it
  and saying it is finished are all an agent's job.
- **Only a `dev:` actor may verify (`done`), send back (`reject`) or abandon (`cancel`).** `done`
  on a card already requires somebody who is not its author; this is that rule one level up. No
  count of closed cards can mean "we shipped it".
- **A milestone in REVIEW is still active.** Its cards keep their home and its facts keep reaching
  them. Nothing archives on an agent's word — the chapter closes on the human's.
- **`reject` requires a reason.** Sending one back without saying what is missing leaves whoever
  reported it with nothing to do.
- **SEVERAL may be active at once**, and that is the normal case rather than an allowance. The
  invariant that used to protect the slice — one chapter — was protecting it by the wrong
  mechanism; the card's own chapter does that now, and it does it without telling anybody they may
  not work on two things.

```
    #1 REACHED     ── verified by dev:berna, 2026-07-28
    #2 REACHED     ── verified by dev:ana,   2026-08-12
    #3 IN_FORCE    ── "que una clienta suba su CSV y vea el reporte"   by 08-20
                        7 cards · 3 done · 2 review · 2 ready
    #4 IN_FORCE    ── "que pueda facturar desde el CRM"                by 09-10
                        4 cards · 0 done · 4 ready
    #5 REVIEW      ── "que el reporte se mande por mail"
                        3 cards · 3 done  ·  agent:ana/w1 reported it, waiting for a person
    #6 PLANNED     ── "que la clienta pueda exportar a Excel"
```

---

## 3 · How it enters the prompt

This is the part that decides whether the model is worth anything, because a model a session does
not read is a schema. Four blocks, and the ORDER is the argument:

```
taskops — You are the ORCHESTRATOR of this board. You do not implement: …
You are `dev:berna` in this project.

## Rules — the project's. Every card, every milestone, no exceptions.
· cero dependencias fuera de la stdlib
· todo evento es append-only
· los tests no tocan la red

## Settings the engine enforces (not advice)
- `reviewer: peer`

## Milestones active — 2
   ◆ que una clienta suba su CSV y vea el reporte    by 2026-08-20   7 cards · 3 done · 2 review
       rules       esta tanda la escribimos sin async
       decisions   sqlite y no postgres                            [db]
       notes       el importador tiene tres etapas…                 [importador]
   ◆ que pueda facturar desde el CRM                by 2026-09-10   4 cards · 0 done · 4 ready
       decisions   los comprobantes se numeran por serie           [facturacion]

   yours       el parser de fechas, sin sorpresas de locale
   next        #6 que la clienta pueda exportar a Excel

## Waiting on a decision (this is where you start)
VERIFY — hand each to the verifier
  tk-269195  el lector de CSV
```

Five things about that shape, each one load-bearing:

- **Project rules come FIRST and outside every chapter.** They are true whatever anybody is
  working on, so they read before the thing anybody is working on. Printed inside a milestone block
  they would look like they expire with it.
- **Each chapter carries its own count.** `7 cards · 3 done` is what makes it a todo-list to a
  reader who cannot see the board, and it is one query, not an opinion. Keyed per chapter, because
  with several running "how far along" is a question per chapter.
- **THIS is the ORCHESTRATOR's view — every active chapter.** It is the one reader that chooses
  between them: it plans into one and dispatches from one, and it cannot do either blind.
- **A WORKER sees ONE chapter — its card's — and never this list.** That is the bound: the project
  block, plus its own card's chapter, plus `yours`. It does not grow with the team, with the year,
  or with the number of milestones running.
- **`next` is one line of titles.** A planned milestone must be visible — "where is this going" is
  a real question — and must not read as something to work on. A title with no facts and no cards
  cannot be mistaken for the work.

A chapter in REVIEW says so, because that is the one state where a session must not start new work
under it:

```
   ◆ REVIEW, waiting for a person — que el reporte se mande por mail
       agent:ana/w1 reported it finished 20m ago.  3 cards · 3 done.
       → verify: taskops milestone done 7c1a44b2   ·   send back: … reject 7c1a44b2 -m "…"
       Nothing new belongs under this chapter until a person closes or returns it.
```

And that same fact goes to `taskops attention`, under a group only a person can clear — which is
where the board already puts everything of that kind.

---

## 4 · The tools

Two MCP tools and not three. Every tool costs every connected agent context on EVERY call, so a
third one has to earn it — and the dev's own facts do not need one: with the project's north being
a milestone, `state=objective` can only mean the caller's own, so the ambiguity is gone by
construction rather than by a flag.

```
  taskops_milestone                       EVERY active chapter, with counts, + planned titles
  taskops_milestone  milestone=<id>       one chapter: its facts AND ITS CARDS
  taskops_milestone  create=…  horizon=…  an agent may.  planned=true to not start it
                     planned=true
  taskops_milestone  start=<id>           a planned one becomes active.  an agent may
  taskops_milestone  update=<id> text=…
  taskops_milestone  review=<id> m=…      an agent reports it finished
  taskops_milestone  done=<id>            REFUSED to an agent — a person verifies
                     carry=… into=…
  taskops_milestone  reject=<id> m=…      REFUSED to an agent
  taskops_milestone  cancel=<id> m=…      REFUSED to an agent

  taskops_context                         the slice: project block + chapter + yours
                     task=tk-…            the slice for ONE card
                     milestone=<id>       a chapter's facts
                     state=rule|decision  level=project for permanent.  REFUSED to an agent
                     state=note           always the chapter's.        REFUSED to an agent
                     state=objective      the CALLER'S OWN.  an agent may: it is its own person
                     retire=<id>
```

`milestone=<id>` answering with the chapter's CARDS is what makes "how do I get to its cards" one
call instead of two — and with several chapters running, that question is asked constantly.

From a terminal there are three nouns, because a flag that can mean "mine" or "the project's" is
the flag that once wrote a dev's objective as the project's and erased the team's north in silence:

```sh
taskops milestone new "que una clienta suba su CSV" --horizon 2026-08-20 [--planned]
taskops milestone start  <id>
taskops milestone review <id> [-m "…"]                    # an agent or a person
taskops milestone done   <id> [--carry 1,3] [--into <id>] # a person only
taskops milestone reject <id> -m "…"                      # a person only
taskops milestone cancel <id> -m "…"                      # a person only
taskops milestone show <id>  ·  list [--all]

taskops context [--task tk-… | --milestone <id>]          # bare = the slice
taskops context rule     "…" [--project]
taskops context decision "…" [--labels a,b] [--files x] [--project]
taskops context note     "…" [--labels a,b]
taskops context log  ·  retire <id>

taskops me                                                # your page
taskops me objective "…" [--horizon …]  ·  decision "…"  ·  note "…"  ·  retire <id>
```

---

## 5 · What the refactor touches

```
  contracts/   Milestone (new).  Task gains `milestone`.  Fact gains `milestone` + `level`.
  storage/     the milestone fold; Task.milestone on the row; one index
  engine/      the state machine for a milestone, beside the card's — same module, same shape
  usecases/    milestone.py (new).  plan() attaches every card.  _contextslice reads the chapter
  transports/  the MCP tool, the CLI verbs, the rpc rows, the HTTP route
  render/      the four-block prompt above, `taskops context`, the statusline word
  ui/          the strip says which milestone; a chapter per section; cards grouped by milestone
```

**Every card belongs to a milestone** is the one that reaches furthest: `plan` has to attach, and
a board with no milestone yet cannot plan — so creating the first one becomes part of `init`'s
story rather than an extra step somebody forgets.

### No migration

The boards are reset rather than migrated. Every existing objective, decision and note predates
this model and there is no honest answer for which milestone they belonged to — inventing one
would fill a fresh design with facts nobody attached. Reset is the cheaper truth, and it is only
available because this is early.

**What that means, precisely, needs one answer from you before anything is deleted:** the local
demo boards under `/tmp` are free to wipe, and so is this repository's own `.taskops/`. The three
on the server — `agenda`, `axion`, `notas` — are not mine to reset, and one of them has 336 events
of real history.
