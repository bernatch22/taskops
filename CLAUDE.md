# taskops v2 — how this works

A shared work board (milestones → cards → subtasks) for teams of coding agents
working in parallel, with a human who decides. Rewrite of `~/taskops` (v1,
~340 files) as **97 Python files / ~10.900 lines under `src/taskops`**, plus the
dashboard — **45 TypeScript files / ~11.700 lines under `ui/src`**, whose built
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
until the human answers `criteria_met=true`. Its **third notch was added by the
GitHub-visible chapter and lives in `ARCHITECTURE.md` §16, not in fan-out.md**
(that file is a dated paper trail, pinned to the tree it was written against):
two workers independently created `src/taskops/gitwork/remote.py`, same path,
complementary halves, because both their specs said "check `git remote get-url
origin`". A CONCEPT named by two cards is a seam — land it serialized first.
The module's own docstring is the post-mortem.

Status: built and green end to end. `./scripts/lint && ./scripts/test` →
**388 passed** (no skips once `npm ci` has run in `ui/` — otherwise
`tests/test_ui.py`'s harness half skips and it is 387+1; see below), ruff +
pyright strict clean. Deployed: `taskops.bernardocastro.dev` has served v2's
four boards since 2026-08-08 and runs **this tree** since 2026-08-09
(tk-df8e64, ARCHITECTURE.md §17) — `/<board>/ui/` answers 410 on all four
boards and the boards' `events.jsonl` are md5-identical across the upgrade.

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
0  _errors _ids _clock _json _locate _version _wire   stdlib only
1  core/    types actors event replay machine graph    PURE: no I/O at all
            hours mentions review scope challenge
2  store/   log cache live reviews creds stores       the ONLY SQL
            server pubkeys  (the HOST's own identity)
3  verbs/   plan take update card pulse assign         + the REGISTRY
            record report review _mentions _waiting project events   no git, no render, no net
4  board.py LocalBoard | RemoteBoard   routing decided ONCE, at open()
   gitwork/ run trees remote trailer bind install diff sig  the ONLY subprocess
   session.py  the CLIENT half of the ssh login: sign in, cache, refresh
5  mcp/     server hello tools gitmoves schema render dossier before brief thread boards fields
   http/    server mounts watcher rpc admin scoped grants ingest auth login
            feed static gitdoor upstream
6  cli/     commands (init join hook) · watch (the viewer's join) · serving
            (serve ui) · operate (board invite revoke) · push (board push)
            · admin (server init + break-glass) · claude wording
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

<root>/server.sqlite   the HOST itself: principals (owner | member) + pubkeys
<root>/allowed_signers DERIVED from it, whole, on every change — the exact
                       file `ssh-keygen -Y verify` consumes. Never hand-edited,
                       never read back into the store (`store/server.py`).
```

A board is created by an explicit act and never by being asked for: an unknown
name is 404 with NO directory left behind (`http/mounts.py::stores` carries the
post-mortem; `Mounts.create` is the only door that makes one).

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

The CLI is like git: `init join serve tidy ui` + the six that OPERATE a host
over its own API, keyed (`board create` · `board ls` · `board push` ·
`board visibility` · `invite` · `revoke` — `http/admin.py` and
`http/grants.py`, and `--root <dir>` is the break-glass path that still runs
them against the files ON the box, now in `cli/admin.py`) + `server init` (bootstrap
a HOST's owner from an ssh pubkey — the one command meant to run over ssh) +
`join --key ~/.ssh/id_ed25519` (the invite AND the pubkey in one call: the key is
registered, it signs in on the spot, and `remote.json` becomes a session cache
that refreshes itself — ARCHITECTURE.md §5) +
`hook` (the two git hooks, `trailer` and `commit`, plus the delivery hook
`claude`). **`taskops board push <host>/<name>` is how a LOCAL board becomes a
hosted one** — the scp is dead: empty target, no live lease, the log streamed
through `board.ingest`, counts compared per kind, and only THEN the config flip
with `.taskops/board/` renamed rather than deleted (`cli/push.py`,
`http/ingest.py`). No force flag, ever. And `join` refuses onto a repo whose
local board has events, naming `board push` and `--discard-local`.
**`taskops board visibility <host>/<name> public|private`** is GitHub's flag,
owner only, and public means exactly what it means there: ANONYMOUS READ, a
write that always needs a registered key, and no third state. `taskops join
<url>` with no invite against a public board is then a READ-ONLY join —
config written, nothing minted, no key registered, and no `project` event
recorded either, because that would be the anonymous write the rule forbids
(`cli/watch.py`). Reads by `anon` renew no lease and record no presence:
`store/live.py::renew` is the ONE place that decides it, and a full anonymous
crawl leaves `events.jsonl` and `live.sqlite` byte-identical.
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
  TypeScript, esbuild); `cd ui && node build.mjs` writes `index.html`, `app.js` and
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

1. ~~Run `scripts/migrate_v1.py` against the v1 boards on axion.~~ DONE
   (tk-5fd8a0, 2026-08-08): the script was first fixed against the real bytes —
   it silently lost the milestone, the criteria, the rules and every released
   note (`tests/test_migrate_v1.py` pins each fix against verbatim fixtures in
   `tests/fixtures/axion-v1/`) — then run: 926 v1 events → 845 v2 events + 81
   named drops into `~/axion-v3/.taskops/board`, verified count by count.
   Mentions: 82 in v1, 17 survive, and that is correct (MENTIONS.md §5).
   The other three v1 boards followed on the deploy (item 2): agenda 43 → 35,
   notas 59 → 48, probe 31 → 17, each reconciled against its own v1
   `db.sqlite`. `~/axion-v3`'s v1 `remote.json` is gone and that clone is
   re-joined against v2.
2. ~~Deploy and point `taskops.bernardocastro.dev` at v2.~~ DONE (tk-5d3ccc,
   2026-08-08). The domain serves v2 with all four boards; v1's process and
   install are removed. **Not via `shipway`** — a board host is a wheel plus a
   directory of board logs, not a code tree to rsync: `ARCHITECTURE.md` §17 is
   the deploy, the order it was done in, and how to upgrade it. The four v1
   board directories are still on the box, untouched, as the last backup.
3. The React dashboard is BUILT — the milestone "Monitor — Nova, panel by panel"
   closed it. It has its data layer, its chrome (header, the milestone picker,
   tabs, KPI rail) and the card dossier drawer — which renders the acceptance
   criteria no v1 screen ever drew, and carries the dashboard's ONE write, the
   comment box with its mention picker. **Four views, in Nova's order: Monitor,
   Board, Actors, Worktrees** — an "Attention" screen that is in no Nova section, and an
   "Hours" tab that in Nova is the Throughput panel *inside* Monitor, were built
   by mistake and deleted. Monitor — Nova's first and central section, and the
   DEFAULT tab — kept its SEAM (`components/monitor/panels.ts`, where every
   panel's props are a declared interface rather than a comment, the fix
   `docs/fan-out.md` prescribes), and its NINE panes are filled, one card each
   — the ninth, Swarm, drawing who is attached to what right now from slices the
   board already sends (ARCHITECTURE.md §15). Chapter in focus no longer
   apologises when several chapters are open: it lists every OPEN one as a
   foldable row, first expanded, and each row's `focus` calls the header
   picker's own `setMilestone` — a door, not a second selection.
   The Event stream — the last pane still empty, because nothing returned the
   log — is fed: `events` is a read verb and the pane pages it by keyset on
   `seq` (`store/cache.py::page`), through the ONE fetch in this dashboard that
   is not `useBoard`, with no second socket (`ui/src/useEvents.ts` says why the
   rule is narrowed and not broken). The smoke harness
   (`ui/smoke/run.mjs`) and `tests/test_ui.py` are green; `npm run check` runs
   every step including the `git diff` clause, which is green now that the
   chapter-close rebuild has cleared the wave's bundle drift.

   And it **points at the code** (`ARCHITECTURE.md` §16): commit shas, cards as
   PR diffs and chapters as compares all link out to the forge, commit events
   carry their `numstat`, and branches reach `origin` by best-effort pushes at
   done / integrate / land. The whole switch is `git remote get-url origin` —
   **without one, nothing pushes, nothing links, and nothing degrades**, which
   is this repo's own board, so that is the case the harness pins.

   And the window it is served in is ALWAYS local (§16, decided 2026-08-08):
   `taskops ui` serves the bundle and mounts `/git` from the checkout it stands
   in whether the board is this repo's or a server's, and the ONLY difference is
   that `/board/rpc` is forwarded to `<url>/rpc` with the bearer from
   `remote.json` (`http/upstream.py`, `http/rpc.py::answered`). The routes never
   change, so the committed bundle knows nothing about it. It used to redirect a
   remote board to the server's own `/ui/` — a page on a machine with no clone,
   where every diff fell through to a link. The live signal there is a POLL of
   the remote `seq` poking the socket already served, never a relayed
   WebSocket, and a ref this clone has not fetched says so and names the `git
   fetch origin tk-<id>` that brings it — it is not an error and nothing is
   fetched for the reader.

   It also shows the **real diff, read from your own clone** (§16's amendment,
   decided 2026-08-08): the dossier gained **Files changed** — the card as a PR,
   `compare/ms/<slug>...tk-<id>`, +/− per file, each file's patch on expand —
   and every commit row folds open its own. The content comes from a read-only
   `/git` door that `taskops ui` mounts because it sits in a checkout;
   `taskops serve` sits in a directory of boards, mounts nothing and says so.
   Nothing is stored: `events.jsonl` still holds references and measures only,
   and the door derives on demand. One cascade decides what a reader gets —
   `ui/src/links.tsx::cascade`: numstat → the patch → the forge link → one
   honest sentence — and `components/card/Patch.tsx` only draws the step it is
   handed. All four steps are pinned headlessly (`ui/smoke/main.tsx`, the `cascade`
   assertions, from the door's OWN payload); `useGitDiff`'s effect firing is not reachable under
   `react-dom/server` and is covered against a real server in
   `tests/test_topology.py` instead.

   **Worktrees is now two screens** (ARCHITECTURE.md §15/§16, decided
   2026-08-08). The index is an INDEX OF PULL REQUESTS — two 50/50 columns, *In
   progress* and *Merged*, two sub-blocks each, and a tile carrying branch,
   title, who carries it and which chapter; the five-column table and its
   sourceless commit cell are gone. Clicking a tree no longer opens the card
   drawer at all: it opens THIS view's own full-width diff page
   (`pages/WorktreeDiff.tsx`), which hands the whole compare range to the SAME
   `FilesChanged`. No verb, no stored key and no change to the /git door bought
   that. The dossier keeps its own Files changed pane, untouched — a second
   surface, not a replacement. That page now READS like one: the patch folds
   into two columns (`components/card/split.ts`, pure — anything it cannot parse
   returns `[]` and the unified view is drawn instead, which is the whole safety
   of the feature), the measurements are a prop (`PatchSize = "drawer" | "page"`,
   so the drawer's pane is byte-for-byte what it was), a column with nothing in
   it is not drawn at all — one populated column is one full-width panel, both
   empty is one centred sentence and no shell — and the page carries **the card's own
   thread** — the same `Thread`, the same `CommentBox`, the same `update
   comment=`. There is no worktree comment and there must never be one: a
   worktree has no identity apart from its card (`gitwork/trees.py` pins
   `tk-<id>` as branch, directory and id at once), so a second thread would be
   two places to say one thing and the reader of the CARD would see half of it.

   **Actors is the fourth view, and it is a page about DEVS** — an agent is a
   LINE inside one. It shipped once as a grid of ACTOR tiles: sixty-seven of
   them, sixty-six being ephemeral sub-agents that had died with their cards,
   which contradicts the chapter's own goal (an actor is a name bound to the RUN
   of a card). The top level is the dev, the durable identity, and two devs are
   two cards each with its own agents. A dev card says how many of its agents
   are on a card right now WITHOUT being opened, plus its figures over the
   window and the most recent few agent names with the rest as a count. A dev's
   totals are dev + agents, refused whole rather than summed over a subset when
   one member cannot say its own. There is NO worker-slot roster and there must
   never be one: taskops allocates no worker (`ui/src/pages/Actors.tsx` and
   `components/monitor/panels.ts` both carry the post-mortem).
   A dev opens into a **full overlay** (`components/actors/DevPanel.tsx`) that
   REUSES `shared/Overlay` — the same portal, the same `overlayStack` that owns
   Escape, one `width` prop apart — with `DevDetail` exported beside it exactly
   as `Dossier` is beside `Drawer`, so the harness reads the document a portal
   cannot render. Inside it, **`components/actors/Daysheet.tsx`** is a pane per
   calendar DAY — newest FIRST and only the newest open, the day's counted total
   on its header — and inside a day, one row per hour it actually SPANS, each
   folding open to that hour's sessions (`HH:MM – HH:MM`, the duration, the card
   and its title, each a door to the dossier). That is the SECOND design of the
   panel: the first drew ONE LANE PER AGENT on a shared wall-clock axis with a
   table of per-agent rows under it, and an "Hours worked today" panel of bars
   beside it on the page. Both are DELETED, not restyled — a bar chart and a
   lane comparison exist to compare things, and an agent is a name bound to the
   RUN of a card, so they compared labels. `tests/test_ui.py::RETIRED_TIMESHEET`
   asserts the committed bundle carries no marker of either.
   A session belongs to the hour its START falls in and is never split
   (splitting would invent intervals `core/hours.py::sessions` never produced),
   and an hour with nothing counted is DRAWN and says so — that is where the
   dropped gaps are, and why a day's total is smaller than last-minus-first. A
   gap over 30 minutes is dropped whole, never capped; the gaps are counted and
   measured under the hours and the rule is on screen in `core/hours.py`'s own
   words.

   And the SERVER stops serving it (ARCHITECTURE.md §16, "API ONLY is now
   literal"). `taskops serve` answers `/rpc`, `/feed` and `/healthz`;
   `/<board>/ui/` answers **410** and one sentence naming `taskops ui`, and the
   `--ui` flag is removed rather than left dead. `Mounts.ui` is `repo`'s shadow:
   one construction-time switch mounts `/git` and the bundle, and only a process
   standing in a checkout has either. The bundle still ships inside the wheel —
   what went is the server-side mount, because a dashboard reads diffs from the
   viewer's clone and the server deliberately has none. `http/static.py` is the
   post-mortem. Production runs it since 2026-08-09 (tk-df8e64): all four of
   `taskops.bernardocastro.dev`'s `/<board>/ui/` answer 410 with that module's
   sentence, and the window that replaces them is `taskops ui` in your clone.
