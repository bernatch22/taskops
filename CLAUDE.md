# taskops v2 — how this works

A shared work board (milestones → cards → subtasks) for teams of coding agents
working in parallel, with a human who decides. Rewrite of `~/taskops` (v1,
~340 files) as **77 Python files / ~7.700 lines under `src/taskops`**, plus the
dashboard — **38 TypeScript files / ~7.100 lines under `ui/src`**, whose built
bundle is committed to `src/taskops/ui/`. Re-derive both rather than trusting
these numbers:

```sh
find src/taskops -name '*.py' | wc -l ; find src/taskops -name '*.py' -exec cat {} + | wc -l
find ui/src -name '*.ts*'     | wc -l ; find ui/src     -name '*.ts*' -exec cat {} + | wc -l
```

**`ARCHITECTURE.md` is the reference** — what exists, how it fits, and §11/§14
are the index of *why*: every rule here is a v1 failure that cost real time,
and the post-mortem for each one is inline in the docstring of the module that
carries it. Read the module before changing its decision, not after.
`README.md` is install-and-run (including serving the UI); `MENTIONS.md` is
the mention design. `docs/` holds the paper trails for decisions that reversed
or extended a rule: `docs/implement-reviewer.md` (why optional review came
back), `docs/design.md` (the product, attribute by attribute), and
**`docs/fan-out.md`** — the post-mortem of the Nova UI milestone: eight
parallel cards, zero conflicts, zero stale leases, and a merged tree that came
back with two `ago()` and three `initials()` anyway. Read it before planning a
wide fan-out; it concludes that `collisions()` is not widened and taskops never
parses source — the seams just land serialized FIRST. Its two adoptions are
live (fan-out.md §10): the ordering rule is a sentence in
`mcp/server.py::INSTRUCTIONS`, and a milestone carries `criteria` next to
`rules` — shown in every take and at `taskops_merge milestone=`, which refuses
until the human answers `criteria_met=true`.

Status: built and green end to end. `./scripts/lint && ./scripts/test` →
**265 passed** (no skips — `tests/test_ui.py` runs; see below), ruff + pyright
strict clean. Not deployed yet (see "What is left").

## The four ideas everything rests on

**1. Derive, don't write.** Three stored statuses — `open`, `done`, `dropped`.
Everything else is computed:

```
ready    = open ∧ deps closed ∧ no owner
doing    = SOMEBODY HOLDS THE LEASE     ← live fact, never a row
blocked  = a dependency has not closed
stalled  = has an owner ∧ nobody is running it
mention  = you were named in a comment ∧ you have not written on that card since
review    = handed in ∧ no verdict yet          (only on a card with review: true)
reviewing = a verifier holds a live REVIEW lease
changes   = last verdict said changes ∧ nobody is on it
```

**Review is OPTIONAL, per card** (`review: true`, or `reviews: true` as a
milestone default) and adds no stored status: `submitted`/`reviewed` are
history-only events folded by `core/review.py`, the review lease is a second
mutex in `live.sqlite` (`store/reviews.py`), and a card that needs review is
refused `done` until a verdict says `pass` — then the ORCHESTRATOR closes it.
A verifier may never judge its own work, and a board that never turns review
on behaves exactly as before. A commit needs NO card: one made outside any
card is still recorded, at project level, and that is all the board knows.

A row survives the process that wrote it; a lease does not. Store `doing` and a
dead worker's card keeps claiming to be worked on — which is why v1 needed a
`recover` verb to contradict its own writes. **There is no `recover` in v2, and
there must never be one**: closing a blocker frees its dependents by
definition, a dying worker releases its card by definition. No writer, so no
race, no sweep, no repair. A stalled card is handed over with `taskops_assign`.

The same shape answers "who still owes a reply" (`core/mentions.py`,
`MENTIONS.md`): answering IS the clearing, so there is no `read` flag and **no
mark-as-read verb** — that would be `recover` again, a write whose only job is
to contradict an earlier one.

**Reading and commenting are open to everyone; only taking, closing and
releasing are the owner's.** Any agent may write on ANY open card — another
team's, one somebody else holds — with `taskops_comment task=… text="…"
mentions=[…]`. Saying something and changing a card are two tools on one verb:
`taskops_update` is the card (status, spec, criteria, deps), `taskops_comment`
is the thread — a `note=` with no status is refused, naming the other call.

That asymmetry is the whole communication channel between agents in parallel,
so it is stated in `mcp/server.py::INSTRUCTIONS`, and the collision block of
every `taskops_take` prints the exact call addressed to the holder. Locking it to the owner would leave two agents whose work meets with
nowhere to say so. `tests/test_verbs.py::test_anybody_may_write_on_a_card_somebody_else_holds`.

**2. Branches are inhabited, not switched.** `git switch` appears nowhere.

```
main ────────────────────────────▶ the HUMAN decides: a PR, or taskops_merge milestone=
  └─ ms/<slug> ──┬──────┬───────▶ the ORCHESTRATOR integrates, card by card
                 │      │           (--no-ff, in .taskops/trees/_ms-<slug>/)
              tk-a11  tk-b22     ← one WORKER each, one worktree each
```

Each branch is pinned to a directory for life; "changing branch" is `cd`. Git
itself refuses the same branch in two worktrees — a third lock nobody has to
remember. `taskops_merge task=` takes no target: merging a CARD to `main`
cannot be expressed. A FINISHED milestone lands with `taskops_merge
milestone=` — the human's explicit call, refused while any card is open or
unintegrated, recorded on the board. Raw `git merge` in the shared checkout is
never the move: the board must learn the milestone shipped.

**3. Two roles, enforced by the server.** The verb registry
(`verbs/__init__.py`) declares `kind` (read/write) and `roles` once:

```
dev:<name>          plans · dispatches · merges · NEVER holds a card
agent:<dev>/<name>  takes · works · updates · NEVER plans or merges
```

A refusal always names the call that works.

**Identity travels IN the call.** Every MCP tool takes `actor=`, and it wins
over the board's own identity (`TASKOPS_ACTOR` at server start, else the
credential's subject). Not optional plumbing: the host runs ONE MCP server per
session and every sub-agent shares it, so the brief's `export` never reaches
the process that speaks MCP — without `actor=` a spawned worker IS the
orchestrator and `take` is unreachable (found on the first real dispatch,
2026-08-07). Remote, `authorize` judges the override: a dev credential may act
as its own agents, nobody else's. The export stays in the brief for the git
hooks, which do run in the worker's shell.

**4. Context travels in the answer, not in a hook that decides.** Three
layers: the MCP server `instructions` — the role protocol **and the board as of
the handshake**, which is what a system prompt was in v1 and arrives with no
hook and no settings file to be trusted (`mcp/hello.py`) —, `taskops_board`
(the panorama on demand), and the pulse line at the foot of every tool result. Those three are
also what carry a mention — `✉ 1 mention for you` rides on EVERY result
(`MENTIONS.md`). One Claude hook exists, and only one: `taskops hook claude`
(MENTIONS.md §9, Berna's own narrowing of his own rule, 2026-08-06) — it
DELIVERS, into the turn of somebody who has not touched a taskops tool in
twenty minutes, two things and only two: a pending mention, to anybody; and
MERGE / REVIEW / STALLED — one line each, count plus the call that clears it —
to a `dev:` only (MENTIONS.md §9f, after two dispatched cards sat `stalled` and
unread for twelve minutes). It may never decide, store, or write, and both its
reads renew no lease. Delete it and nothing breaks but immediacy. `taskops_take`
returns the WHOLE world — the milestone's goal and `rules`, the card — spec, criteria, the resolved epic, the whole thread,
commits with subjects, collisions, the previous worker's `released` note, its
worktree. plus who else is working right now. **The section order is design**:
everything that changes what you do before you start lives in `mcp/before.py`
and renders above the spec. `tests/test_mcp.py` pins the order, not just the
presence.

## The layers — imports only point DOWN

```
0  _errors _ids _clock _json _locate _version      stdlib only
1  core/    types actors event replay machine graph    PURE: no I/O at all
            hours mentions review
2  store/   log cache live reviews creds stores       the ONLY SQL
3  verbs/   plan take update card pulse assign         + the REGISTRY
            record report review waiting project events    no git, no render, no net
4  board.py LocalBoard | RemoteBoard   routing decided ONCE, at open()
   gitwork/ run trees remote trailer bind install      the ONLY git (client-side)
5  mcp/     server hello tools gitmoves schema render dossier before brief thread
   http/    server mounts rpc auth feed static
6  cli/     commands (init join hook) · serving (serve invite ui) · claude wording
```

`tests/test_architecture.py` enforces all of it by AST: the direction of
imports, SQL only in `store/`, `subprocess` only in `gitwork/run.py`, the clock
only in `_clock.py` + `core/hours.py`, ≤200 lines per module, no `assert` in
`src/`. **A rule with no test is a suggestion** — if you split a module to fit
the budget, split it where it is cohesive, never relax the rule.

## Storage

```
<board>/events.jsonl   THE TRUTH — append + fsync BEFORE the cache
<board>/cache.sqlite   derived, disposable (delete it, it rebuilds)
<board>/live.sqlite    leases + presence — separate file ON PURPOSE:
                       clearing the cache must never drop a live claim
```

Event ids are `sha256(canonical)[:32]`, so the log is idempotent and a repeated
write is a no-op. Replay sorts by `ts` with a STABLE sort — ties keep arrival
order; breaking them by id was arbitrary and reordered claims against releases.

## Commands

```sh
./scripts/lint                      # ruff + pyright strict
./scripts/test                      # the whole suite
uv run python -m taskops.cli ui        # the dashboard, one command, token included
uv run python -m taskops.cli serve --root <dir>
uv run python -m taskops.cli join "http://host/<board>?token=…"
```

The CLI is like git: `init join serve invite tidy ui` + the two git hooks.
Managing cards from the terminal does not exist — that is MCP (9 tools).

## Working here

- **Mutation-check every fix**: break it on purpose, watch the test fail, put it
  back. Two tests here looked green with the fix removed until this was done.
  Break the sites ONE AT A TIME: a chapter-close card mutated five fallbacks
  together, saw the suite go red, and only a per-site pass showed that four of
  the five were not covered at all. A batch mutation proves *something* is
  pinned, never *which*.
- **Name a throwaway probe after the card**: `tk-<id>-probe.mjs`, never
  `probe.tsx`. Worktrees are separate but the scratchpad is shared, and a worker
  in this wave (tk-342486) unknowingly ran a sibling's probe of the same name for
  two turns. A probe that silently runs somebody else's code is the worst kind of
  green. Delete it before the card closes.
- **Docs must not lie.** `ARCHITECTURE.md`, `README.md`, `MENTIONS.md` and this
  file are part of the diff — counts, "not yet" and status tables all expire.
  `docs/implement-reviewer.md` and `docs/fan-out.md` are different: dated paper
  trails, each claim pinned to the tree it was written against. Keep their
  *current-tense* claims true; do not rewrite their history. `docs/design.md`
  is a live reference and is held to the same standard as this file. Prefer a
  command somebody can re-run over a number that rots silently.
- **The dashboard is built, not hand-written.** Source in `ui/` (React +
  TypeScript, esbuild); `node ui/build.mjs` writes `index.html`, `app.js` and
  `style.css` into `src/taskops/ui/`, and **that output is committed** — that is
  what makes `pip install taskops` serve a dashboard with no node toolchain.
  React is bundled, never a CDN. `npm run check` in `ui/` is the closure:
  typecheck + build + smoke + `git diff --exit-code ../src/taskops/ui`. All four
  steps run and all four are green. The diff clause goes red while a wave of
  `.tsx`-only cards is in flight and green again at the chapter-close rebuild —
  that drift is what it exists to report, not a fault.
- **Do not run browser/UI demos unless asked.** The UI is tested headlessly —
  `tests/test_ui.py` builds a real board and hands the server's own payload to
  `ui/smoke/run.mjs`, which renders the modules `src/main.tsx` bundles through
  **`react-dom/server`, with no browser and no jsdom**. That is possible because
  three seams were designed for it: `Dossier` exported beside `Drawer` (a portal
  renders nothing under `renderToStaticMarkup`), `submit()` (the send rule as a
  pure function — "the draft survives a refusal" with no DOM), and
  `overlayStack` (no listener in it). No event handler ever fires there, so a
  click that does nothing is still out of reach; everything that decides whether
  the click has something to land on is not. A second test reads the COMMITTED
  bundle for the same panes — those bytes are what `pip install taskops` serves.
- Never re-introduce: a reviewer ROLE, a stored review STATUS, or automatic
  reviewer assignment (optional per-card review exists — docs/implement-reviewer.md
  is the paper trail; what stays banned is v1's shape: a role that ate the
  budget, 14 closing rules, a `peer` graph that deadlocked); `land` or
  automatic merges to main, git
  replication between clones, Claude hooks **that decide or store** (the one
  delivery-only hook is sanctioned — MENTIONS.md §9; anything beyond delivery
  is not), a stored `doing`, a slug in a branch name, a `recover`, or a
  mark-as-read/ack verb for mentions. Each one has its line in
  `ARCHITECTURE.md` §11 saying what it cost and where it is enforced.

## What is left

1. Run `scripts/migrate_v1.py` against the v1 boards on axion. The script is
   written and tested; it has never been run on the real board, and the 66
   events carrying `mentions` want a human eye after (MENTIONS.md §5).
2. Deploy (`shipway`) and point `taskops.bernardocastro.dev` at v2.
3. The React dashboard is BUILT — the milestone "Monitor — Nova, panel by panel"
   closed it. It has its data layer, its chrome (header, the milestone picker,
   tabs, KPI rail) and the card dossier drawer — which renders the acceptance
   criteria no v1 screen ever drew, and carries the dashboard's ONE write, the
   comment box with its mention picker. **Three views, in Nova's order: Monitor,
   Board, Worktrees** — an "Attention" screen that is in no Nova section, and an
   "Hours" tab that in Nova is the Throughput panel *inside* Monitor, were built
   by mistake and deleted. Monitor — Nova's first and central section, and the
   DEFAULT tab — kept its SEAM (`components/monitor/panels.ts`, where every
   panel's props are a declared interface rather than a comment, the fix
   `docs/fan-out.md` prescribes), and its eight panes are filled, one card each.
   The Event stream — the last pane still empty, because nothing returned the
   log — is fed: `events` is a read verb and the pane pages it by keyset on
   `seq` (`store/cache.py::page`), through the ONE fetch in this dashboard that
   is not `useBoard`, with no second socket (`ui/src/useEvents.ts` says why the
   rule is narrowed and not broken). The smoke harness
   (`ui/smoke/run.mjs`) and `tests/test_ui.py` are green; `npm run check` runs
   every step including the `git diff` clause, which is green now that the
   chapter-close rebuild has cleared the wave's bundle drift.

   What the dashboard still cannot do is deploy itself: item 2 above.
