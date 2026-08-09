# taskops v2 — how to work in this repo

A shared work board (milestones → cards → subtasks) for teams of coding agents
working in parallel, with a human who decides. Zero runtime dependencies.

**[ARCHITECTURE.md](ARCHITECTURE.md) is the reference** — what exists, how it
fits, and why. §11 is the index of banned things and §14 the rules the code is
held to. Every rule below is a v1 failure that cost real time, and the
post-mortem for each one is inline in the docstring of the module that carries
it: **read the module before changing its decision, not after.**
[README.md](README.md) is install-and-run.

## Commands

```sh
./scripts/lint                          # ruff + pyright strict
./scripts/test                          # the whole suite
cd ui && npm run check                  # typecheck + build + smoke + bundle diff
cd ui && node build.mjs                 # rebuild the committed bundle only
uv run python -m taskops.cli ui         # the dashboard, token included
```

Prefer a single test file over the whole suite while iterating:
`uv run pytest tests/test_verbs.py -q`.

## Architecture — the four ideas

**1. Derive, don't write.** Three stored statuses: `open`, `done`, `dropped`.
`ready`, `doing`, `blocked`, `stalled`, `mention`, `review`, `reviewing` and
`changes` are all computed per read. A row survives the process that wrote it; a
lease does not — which is why there is **no `recover` verb and must never be
one**. Closing a blocker frees its dependents by definition; a dying worker
releases its card by definition. A stalled card is handed over with
`taskops_assign`.

**2. Branches are inhabited, not switched.** `git switch` appears nowhere.

```
main ────────────────────────────▶ the HUMAN decides: a PR, or taskops_merge milestone=
  └─ ms/<slug> ──┬──────┬───────▶ the ORCHESTRATOR integrates, card by card
              tk-a11  tk-b22     ← one WORKER each, one worktree each
```

Each branch is pinned to a directory for life; "changing branch" is `cd`. Work
reaches the trunk through `taskops_merge`, **never a merge you run by hand** —
the hook refuses one, and a squash makes the work unfindable.

**3. Two roles, enforced by the server** (`verbs/__init__.py` declares `kind`
and `roles` once, and every refusal names the call that works):

```
dev:<name>          plans · dispatches · merges · NEVER holds a card
agent:<dev>/<name>  takes · works · updates · NEVER plans or merges
```

**Pass `actor=` on EVERY MCP call.** The host runs ONE MCP server per session
and every sub-agent shares it, so a spawned worker without `actor=` IS the
orchestrator and `take` is unreachable.

**4. Context travels in the answer**, not in a hook that decides: the MCP
`instructions`, `taskops_board` on demand, and the pulse line on every result.
One Claude hook exists and it only DELIVERS (a pending mention, and the
MERGE/REVIEW/STALLED counts to a `dev:`). It may never decide, store or write.

Reading and commenting are open to everyone; only taking, closing and releasing
are the owner's. Any agent may `taskops_comment` on ANY open card — that
asymmetry is the whole communication channel between parallel agents.

## Layers — imports only point DOWN

```
0  _errors _ids _clock _json _locate _version _wire   stdlib only
1  core/     PURE: no I/O at all
2  store/    the ONLY SQL
3  verbs/    + the REGISTRY.  no git, no render, no net
4  board.py · session.py · identity.py · gitwork/   the ONLY subprocess
5  mcp/ · http/    peers: neither imports the other
6  cli/
```

`tests/test_architecture.py` enforces all of it by AST: import direction, SQL
only in `store/`, `subprocess` only in `gitwork/run.py`, the clock only in
`_clock.py` + `core/hours.py`, ≤200 lines per module, no `assert` in `src/`.
**A rule with no test is a suggestion** — if you split a module to fit the
budget, split it where it is cohesive, never relax the rule. Zero headroom is a
finding, not a pass: re-derive it rather than trusting a number here.

```sh
find src/taskops -name '*.py' -exec wc -l {} + | awk '$2!="total" && $1>=190' | sort -rn
```

**A leading `_` means "plumbing for the layer above", not "private"** — a
three-zone convention. The package ROOT (`_errors _ids _clock _json _locate
_version _wire` are level 0; `board.py`, `session.py`, `identity.py` are that
layer's doors) and `verbs/` (`_args _cards _context _facts _mentions _rows
_waiting` are helpers — the un-prefixed files are the registry's entries, one
per verb). Nowhere else carries it: every module under `core/ store/ gitwork/
http/ mcp/ cli/` is internal to its layer, and `import taskops` exposes five
errors and a version, so module names are a contract with nobody. Do NOT rename
a package to `_core/` to resemble a library — that underscore marks the half of
a *library* users must not import, and taskops has no such half.

## Storage

```
<board>/events.jsonl   THE TRUTH — append + fsync BEFORE the cache
<board>/cache.sqlite   derived, disposable (delete it, it rebuilds)
<board>/live.sqlite    leases + presence — separate file ON PURPOSE
<root>/server.sqlite   the HOST: principals + pubkeys
<root>/allowed_signers DERIVED from it, whole, on every change
```

Event ids are `sha256(canonical)[:32]`, so the log is idempotent. Replay sorts
by `ts` with a STABLE sort — breaking ties by id reordered claims against
releases. A board is created by an explicit act and never by being asked for.

## Working here

- **Mutation-check every fix**: break it on purpose, watch the test fail, put it
  back. **One site at a time** — a batch mutation proves *something* is pinned,
  never *which*. Two tests here looked green with the fix removed.
- **Do not guess a cause.** Debug it or ask. A retrieval hit is a location, not
  an understanding. Follow the concept UPSTREAM to the file that derives it: the
  correct fix site often contains none of your query's words.
- **Never edit a test that pins existing behaviour** to make a change pass. If
  it has to change, justify that it pinned implementation, not contract.
- **Do not duplicate.** Search first. Extend rather than modify; a family of
  interchangeable variants gets one interface plus implementations.
- **Docs must not lie.** `ARCHITECTURE.md`, `README.md` and this file are part
  of the diff — counts, "pending" and status tables all expire. Prefer a command
  somebody can re-run over a number that rots silently.
- **Name a throwaway probe after the card**: `tk-<id>-probe.mjs`, never
  `probe.tsx`. Worktrees are separate but the scratchpad is shared, and a worker
  once ran a sibling's identically-named probe for two turns. Delete it before
  the card closes.
- **Report what happened.** Failing test → paste the output. Skipped step → say
  so. Speed is not a goal; never trade understanding for fewer turns.

## The dashboard

Source in `ui/` (React + TypeScript, esbuild); `node build.mjs` writes into
`src/taskops/ui/`, and **that output is committed** — that is what makes
`pip install taskops` serve a dashboard with no node toolchain. React is
bundled, never a CDN. `npm run check` closes the loop with a `git diff
--exit-code` on the bundle; that clause goes red while a wave of `.tsx`-only
cards is in flight and green again at the chapter-close rebuild — that drift is
what it exists to report, not a fault.

- **A smoke section is a FILE, never an append**: `ui/smoke/sections/<slug>.tsx`,
  named by what it pins — slugs, NEVER numbers, since the §-numbering was itself
  the collision. The index is regenerated from a `readdir` and gitignored, so it
  cannot conflict.
- **Do not run browser/UI demos unless asked.** The UI is tested headlessly
  through `react-dom/server`, no browser and no jsdom.
- One card rebuilds the bundle at the end of a wave. N cards rebuilding it is
  N-1 conflicts by construction.

## Never re-introduce

Each has its line in ARCHITECTURE.md §11 saying what it cost and where it is
enforced: a reviewer ROLE, a stored review STATUS, or automatic reviewer
assignment · `land` or automatic merges to main · git replication between clones
· Claude hooks **that decide or store** · a stored `doing` · a slug in a branch
name · a `recover` · a mark-as-read/ack verb · per-request SIGNING · hand-rolled
crypto or a pip crypto dependency · a `--force` on `board push` · and ANONYMOUS
WRITES in any form, including the invisible one (a `presence` row on a public
read).

**Legacy bearer tokens are a fleet, not a detail.** Production's four boards
were joined before keys existed: no principal, no pubkey, an empty
`allowed_signers`. Anything touching auth, `/feed`, the MCP handshake or the
`taskops ui` forward is checked against that state and not against a fresh keyed
board — the `test_a_legacy_*` tests in `tests/test_topology.py` are the proof.
