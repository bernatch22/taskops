# taskops — how to work in this repo

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
uv run ruff check src tests             # lint
uv run pyright                          # types, strict
uv run pytest                           # the whole suite
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
releases its card by definition. A card is handed over with `taskops_assign` —
**including one whose lease is still live** (2026-08-11, ARCHITECTURE §12):
the lease's only heartbeat is MCP traffic, so the clock cannot tell a dead
worker from one that has been editing quietly for twenty minutes, and it was
wrong in both directions at once. `stalled` is a report, never a mechanism;
the orchestrator that spawned the process is the authority on whether it is
alive, and the card goes to a NAMED replacement in the same call. Which is
still not a `recover`: nothing is resurrected, and nothing is taken by the
passage of time.

**2. Branches are inhabited, not switched.** `git switch` appears nowhere.

```
master ──────────────────────────▶ the HUMAN decides: a PR, or taskops_merge milestone=
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
are the owner's. Any agent may `taskops_comment` on ANY card — that asymmetry is
the whole communication channel between parallel agents. **A CLOSED card is
included**: the log is append-only, so a postscript is accepted and does not
reopen it. Only DELIVERY stops at the close — a `mentions=` written on a closed
card pages nobody, silently (`verbs/_facts.py::pending_mentions` argues why).

**ONE introduction per side, ONE credential** (2026-08-11, ARCHITECTURE §19).
A key gets enrolled either by burning an invite (`POST /<board>/invite/redeem`)
or by the OWNER's forge sync (`members.enroll`, a batch) — and both end in the
same `login.register`, so what persists is a pubkey and an `allowed_signers`
line, never a GitHub token. **GitHub is the INTRODUCTION, never the credential,
and it is the OWNER's business alone**: `taskops board forge <owner>/<repo>`
declares the repo AND syncs its team — collaborators with the declared access →
their PUBLIC `github.com/<login>.keys` → one `members.enroll` batch.
`cli/github.py` asks GitHub (the owner's token lives in ONE header, per page, and
never reaches the host), `cli/team.py` runs the flow and prints the report. A
board opts in with `op=forge` (`core/forge.py` owns the shape); absent — the
state every board is born in — it is invite-only. `--clear` takes it back — the
owner's move, both ways (`core/scope.py`).

The sync **adds only**: a principal who lost access is named with the exact
`taskops revoke --key`, never revoked, because an invite-enrolled principal is
not a GitHub login. Nobody is dropped in silence — a collaborator with no
published key is named with `taskops invite <login>`.

**The DEV types `taskops join` and nothing about GitHub** (§19.1). There was a
door on their side for one day — `POST /<board>/join/github`, a `--github` flag,
a token discovered inside `join` — and it is DELETED: it made every dev's own
credential travel for a fact the owner already holds. Their key was already
enrolled by the sync, so the bare join signs a challenge with it and is in. What
survived the flag is the rule about the TOKEN (`cli/github.py::token`: `gh auth
token`, else `$GITHUB_TOKEN`, else a hidden prompt — **never a flag value**, the
shell writes those into the history file before the process starts).

And the board SAYS which forge opens it: the declared fact rides on the `board`
payload, derived per read exactly as `visibility` is, so a reader finds the door
instead of bumping into it. **A board with no forge sends no key at all** —
never `null`.

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
layer's doors) and `verbs/` (`_args _cards _chapter _context _facts _mentions
_rows _stories _waiting _windows` are helpers — the un-prefixed files are the registry's entries, one
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

## The CLI surface — it connects, it never manages

Eleven top-level commands, and `board` is the only one with actions of its own.
Moving a card from the terminal does not exist: that is MCP. Re-derive both
lists rather than trusting this paragraph — `--help` is the source:

```sh
uv run python -m taskops.cli --help | sed -n '/^usage/,/^$/p'   # the eleven
uv run python -m taskops.cli board --help                       # its actions
```

`board` today: `create · ls · push · pull · rm · visibility · forge`. The four that move
a whole history are one lifecycle, and each says what it destroys:

```
init ──▶ board create + push ──▶ board pull ──▶ board rm
 —          the local board       nothing:       the host's board, and ONLY
            is RENAMED, not       the host       with --discard-history if
            deleted               keeps its      this checkout does not
                                  copy           already hold that history
```

`push` and `pull` are the same five steps in opposite directions and both flip
`board.json` LAST, so a failure anywhere above leaves the repo as it was and the
command is re-run. `rm`'s guardrail is judged on the HOST against the board's
real event ids (`core/holding.py`, one comparison, both callers) — a wall the
client enforces is a convention. There is no `--force` on `push` or on `rm`, and
`--discard-history` is not an alias for one. ARCHITECTURE.md §20 argues all of it.

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

**The hosted page is at the board's OWN address** — `https://<host>/<board>/`
(and `/<board>`), its assets beside it, the machine doors under
`/<board>/api/{rpc,git,feed}`. 0.5.0's spellings (`/<board>/ui/`,
`/<board>/rpc`, `/<board>/git/…`, `/<board>/feed`) still answer and are a
contract, not a legacy — ARCHITECTURE §16, "The board's own address IS the
page". The page derives its base from its own location
(`ui/src/client.ts::baseOf`) and hardcodes neither. `sh smoke.sh` re-derives all
of it against the live host, plus the credential rule a browser exposed:
**an `Authorization` header with no value is the ABSENCE of a credential, a
header with a wrong value still refuses loudly** (`http/auth.py::token_in`).

## Never re-introduce

Each has its line in ARCHITECTURE.md §11 saying what it cost and where it is
enforced: a reviewer ROLE, a stored review STATUS, or automatic reviewer
assignment · `land` or automatic merges to the trunk · a SECOND trunk (2026-08-10: `main` and `master` both existed, `trees.base_ref` cut every chapter from `origin/main`, and a one-sided push refspec was quietly landing card merges there — three facts that only became a bug together) · git replication between clones
· Claude hooks **that decide or store** · a stored `doing` · a slug in a branch
name · a `recover` · a mark-as-read/ack verb · per-request SIGNING · hand-rolled
crypto or a pip crypto dependency · a `--force` on `board push` **or on `board
rm`** (nor a confirmation prompt in its place: a prompt asks whether you meant
it, possession asks whether the history survives you) · a STORED GitHub token,
a GitHub login as a second credential type, **or a GitHub door on the DEV's side**
(a `/join/github`, a `--github`, a token discovered at join time: the owner
already knows the team, so nobody else's credential has to travel) · a report's CONTENT in
`events.jsonl` or a reports TABLE beside it (the log holds `{path, title,
milestone, sha}` and the list is a fold) · `allow-scripts` **beside**
`allow-same-origin` on the report frame, or a `sandbox` a caller can pass — that
pair is not two permissions, it is the absence of the sandbox, and this origin
holds the token · and ANONYMOUS WRITES in any form, including the invisible one
(a `presence` row on a public read).

**Legacy bearer tokens are a fleet, not a detail.** Production's four boards
were joined before keys existed: no principal, no pubkey, an empty
`allowed_signers`. Anything touching auth, `/feed`, the MCP handshake or the
`taskops ui` forward is checked against that state and not against a fresh keyed
board — the `test_a_legacy_*` tests in `tests/test_topology.py` are the proof.
