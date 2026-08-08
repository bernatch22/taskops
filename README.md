# taskops v2

A shared work board — milestones → cards → subtasks — for teams of coding
agents working in parallel, with a human who decides.

* **The truth is an append-only event log.** The cache is disposable; the
  leases are not.
* **Agents do not step on each other by mechanism, not by prompt**: a lease
  (one row, one winner), a worktree (one directory each), and a branch pinned
  to that directory for life.
* **The only management interface is MCP** — nine tools ([below](#the-nine-tools)).
  The CLI behaves like git: it connects, it never manages.
* **`main` is written by a person**, through a pull request. taskops stamps a
  commit trailer, records the commit on its card, and integrates finished cards
  into the milestone branch. Nothing else.

What exists and why: [ARCHITECTURE.md](ARCHITECTURE.md). How to work in this
repo: [CLAUDE.md](CLAUDE.md). Mentions: [MENTIONS.md](MENTIONS.md).

## Quickstart

Install once, into an interpreter you'll actually run `init`/`join` from — the
git hooks pin `sys.executable` at that moment, so a `python3` that does not
have `taskops` importable leaves commits un-stamped, silently (the hook prints
the error but never blocks the commit, by design):

```sh
uv tool install --from ~/taskops-v2 --force taskops   # --force: replaces v1 if it's on PATH
```

**Local — one machine, no server.** For solo work, or before you trust the
thing enough to host it:

```sh
cd your-project
taskops init                # .taskops/board/ (log + 2 sqlite files), 2 git hooks, .mcp.json
```

**Remote — a team, one shared board.**

```sh
taskops serve --root ~/taskops-boards &              # host; the dashboard ships inside the package
taskops invite ana --board my-project                # one-time link, 7 days (--revoke <id>)
```

Ana, in **her own** checkout of the same repo:

```sh
taskops join "https://host:8787/my-project?invite=<token>"
```

Either way you get the same two files: `.taskops/board.json` (the address —
committed, it travels with the code) and, for `join`, `.taskops/remote.json`
(0600, gitignored — the credential never does). Both write the two git hooks,
`.mcp.json`, and the one Claude hook (`.claude/settings.json`, merged) — the
delivery hook that carries a pending `✉` mention into a working agent's very
next tool call, and — to the orchestrator only — the `◆` groups it is sitting
on, done-but-unmerged, handed-in-but-unchecked, owned-but-stalled
([MENTIONS.md](MENTIONS.md) §9 and §9f; read-only, deletable, never decides).
**Restart your Claude Code session in that project after** — MCP
servers load once, at session start, from `.mcp.json`; from then on
`taskops_board` is a tool call, not a shell command.

**Then, as the orchestrator** (the main session, `dev:<name>`):

1. `taskops_board` — open every turn with this; it says what the board is
   waiting for, grouped by the move each card needs.
2. `taskops_plan` — one call writes a milestone and its cards, dependencies
   included.
3. `taskops_assign tasks=[...]` — assigns them, cuts one git worktree per
   card, and hands back a paste-ready brief per card. Spawn one sub-agent per
   brief, all in the same message — `taskops_assign` starts nothing itself.
4. If a card has `review=true` (or its milestone has `reviews=true`), it turns
   up under REVIEW once its worker hands it in. Spawn a **fresh** verifier —
   never a fork of yourself, or it inherits the assumptions it should be
   checking — its one tool is `taskops_review`: `task=<id>` claims it, and then
   `taskops_review task=<id> verdict=pass|changes note="…"`. On `pass` you
   close the card yourself; on `changes` you send the note back to the worker
   that is still alive and holds all the context. Review is OFF by default and
   nothing assigns a verifier for you.

**As a worker** (a spawned sub-agent, `agent:<dev>/<name>` — the brief names
it, and you pass it as `actor=` on **every** taskops call: sub-agents share
the session's one MCP server, whose own identity is the orchestrator's, so
the call is the only place your identity can travel. The brief's `export
TASKOPS_ACTOR=…` is for the git hooks, which do run in your shell):

1. `taskops_take task=<id> actor=agent:<dev>/<name>` — this single call
   returns everything: the milestone's goal **and its rules**, the spec and
   criteria, the whole thread, who else is working right now, file
   collisions, the previous worker's note, and the worktree to `cd` into.
   Nothing else needs reading first, and nothing in it is truncated.
2. Do the work, commit inside that worktree (the branch and the `Task:`
   trailer are already wired).
3. `taskops_update task=<id> actor=… status=done note="…"` — or
   `status=released` with a note if it's going back to the pool. To say
   something rather than change the card, `taskops_comment`.
   If the card needs review, the exit is `status=review note="…"` instead (the
   brief says so): you hand it in, keep your lease and **stay reachable**, and
   the orchestrator closes it once a verifier passed it. A `changes` verdict
   comes back to you with the reviewer's note verbatim, above the spec.

A commit that carries no card is fine and is not lost: the board records the
sha at project level. Nobody is forced to take a card to commit — but closing
a card still needs a commit bound to *it* (or `no_code=true` with a note).

Sub-agents are not optional and nothing here removes them: the whole point is
several agents holding different cards at once, each pinned to its own
worktree, none of them able to collide by construction. What changed from v1
is *how* a sub-agent gets its context (the tool response, not a hook) and why
its card never gets stuck (derived `doing`, not a stored one) — not whether
sub-agents exist.

```sh
taskops tidy      # drop worktrees whose branch is already merged into the trunk
taskops ui        # the dashboard: serves it if nothing is, opens the browser, token included
```

`taskops ui` is the whole story of the dashboard — no port, no token, no flags.
Local board: it serves right there (blocking, ctrl-c stops it; an agent runs it
in the background) and opens the browser with a minted token; run it again and
it just reopens the running one. Remote board: it opens the server's /ui/ with
the credential `join` already saved. The old `taskops open` sent you to a
paste-a-token screen holding a token the machine already had.

The diffs the dossier shows — **Files changed** on a card, the patch under a
commit — come from **your own clone**, read on demand by the host `taskops ui`
started inside it; nothing is stored on the board and nothing goes to the
network. A host with no checkout (`taskops serve`, which sits in a directory of
boards) mounts no such door and says so, and the page falls back to the GitHub
link when the repo has an origin, or to one plain sentence when it does not.

### Working on the dashboard itself

You do not need node to *run* it — the built bundle
(`src/taskops/ui/{index.html,app.js,style.css}`) is committed, and React is
bundled into it rather than fetched from a CDN, so a fresh `pip install taskops`
serves a dashboard offline. You need node only to *change* it:

```sh
cd ui
npm install
npm run build     # typecheck + esbuild -> ../src/taskops/ui/   (commit the output)
npm run check     # the closure: build + smoke + `git diff --exit-code` on the output
```

Because that output is committed, `.gitattributes` marks the three files
`-merge`: git will not text-merge a generated artifact into one no build ever
produced. **A fresh clone needs nothing for this** — `-merge` is built into
git, there is no driver to install and no `git config` to run. It means a merge
that touches the bundle stops with the path conflicted and your copy intact;
resolve it by rebuilding, never by hand:

```sh
cd ui && node build.mjs && git add ../src/taskops/ui && git commit --no-edit
```

(`docs/fan-out.md` §11 — five parallel cards each rebuilding the bundle cost a
milestone six merge round trips.)

`npm run check` is the closure and its four steps run: typecheck, build,
`ui/smoke/run.mjs` (the headless harness — `react-dom/server`, no browser and
no jsdom), then `git diff --exit-code ../src/taskops/ui`. All four steps are
green in the current tree: the wave of `.tsx`-only cards that made the last
clause red has had its one chapter-close rebuild, which is exactly the drift the
clause exists to report and to clear.

The harness runs on its own captured payload (`npm run smoke`, which needs no
Python) and on a live one — `tests/test_ui.py` builds a real board and hands it
over. It needs `ui/node_modules`; without it, or without node, that test skips.

Three tabs, in Nova's order — **Monitor** (`ui/src/pages/Monitor.tsx`, the
default), **Board** (`ui/src/pages/Board.tsx`) and **Worktrees**
(`ui/src/pages/Worktrees.tsx`, an index of pull requests in two equal columns,
In progress and Merged, where a row opens its own full-width diff page — side by
side, with the card's own thread on it — instead of the drawer) — plus the card
dossier drawer that opens over Monitor and Board (`ui/src/App.tsx`) and the header's
milestone picker. Monitor is no longer a shell: its two-column layout, the
shared pane chrome and all NINE panes are built, one card per panel — the
ninth is Swarm, who is attached to what right now, drawn from slices the board
already sends. The Event
stream — the last pane that had no verb behind it — is fed: `events` pages the
log by keyset and the pane draws real rows, so an empty pane now means an empty
log. Nothing else exists — an "Attention" screen and an "Hours" tab were built
by mistake and deleted (Hours is Nova's Throughput panel, inside Monitor).

**The board points at the code.** If the repo has an `origin`, every screen
links out to the forge: a commit sha opens `…/commit/<sha>`, a card offers its
PR-style diff (`…/compare/ms-…...tk-…`), and a chapter compares against the
trunk. A commit event carries its `numstat`, so the dossier and the Event stream
show `+/-` per file — a file git could not count is reported as a binary, never
as a zero. Branches reach `origin` by best-effort pushes at the three moments
that already exist (done, integrate, land): a failed push changes nothing about
the board action that triggered it. The host is a value, not a code path —
GitHub, GitLab and friends differ only by a row of URL shapes.

**With no `origin`, nothing pushes, nothing links, and nothing degrades.** The
switch for all of it is `git remote get-url origin`, never a local-vs-remote
mode; a board without a remote renders exactly the screens it rendered before,
with no dead anchors and no empty column reserved for one.

The source is React + TypeScript under `ui/src`, with Nova's palette in
`ui/src/theme/tokens.css` — the one file allowed to contain a literal colour.
The theme is an attribute on `<html data-tk>`, remembered in `localStorage`,
defaulting to the OS scheme.

## The shape

```
worker      ──commit──────────────▶  tk-<id>          its branch, its worktree
orchestrator──taskops_merge task=─▶  ms/<milestone>   --no-ff, in the integration worktree
human       ──PR, or taskops_merge milestone=─▶  main  one decision, on the record
```

Branches are not switched, they are inhabited: one directory per card, pinned
to its branch for life. Two agents on two different milestones are two
directory trees that share nothing.

## Three stored states, the rest derived

```
STORED (a row)        DERIVED (computed, never written)
open                  ready     = open ∧ deps closed ∧ no owner
done                  doing     = somebody holds the lease   ← the live one
dropped               blocked   = a dependency has not closed
                      stalled   = has an owner ∧ nobody is running it
                      mention   = you were named ∧ you have not written since
                      review    = handed in ∧ no verdict since   ← optional
                      reviewing = somebody holds the REVIEW lease
                      changes   = the last verdict asked for changes
```

That is why there is no "recover" command and no stuck cards: a worker that
dies stops renewing its lease, and its card leaves `doing` on its own.

## The nine tools

| orchestrator (`dev:`) | worker (`agent:<dev>/<name>`) |
|---|---|
| `taskops_board` — what the board waits for, grouped by the next move | `taskops_take` — claim a card, get its whole world back |
| `taskops_plan` — the whole tree in one call, dependencies included | `taskops_update` — change the card: close, hand in for review, hand back, drop, rewrite |
| `taskops_assign` — assign, cut worktrees, return a paste-ready brief | `taskops_card` — one card in full, or search |
| `taskops_merge` — integrate a done card into its milestone branch | `taskops_review` — the verdict on a submitted card: `pass` or `changes` with a note |
| | `taskops_comment` — say something on ANY open card (`mentions=[…]`) |

`taskops_review` is neither role's alone: a verifier is an ordinary agent
doing one bounded read, and there is no reviewer role. You may never judge
your own work, and one verifier holds a card at a time.

The server refuses a verb the caller's role may not run, and every refusal
names the call that works.

## Nobody misses a mention, and nothing marks one as read

`taskops_comment task=<id> text="which rate?" mentions=["dev:berna"]` puts a
`✉ 1 mention for you` in the pulse line at the foot of **every** result that
reader gets back next, whatever they call, and lists it on their
`taskops_board` under MENTIONS — above the cards that went quiet. It clears
itself the moment they write anything on that card, or when the card closes:
"still unanswered" is derived from the thread on every read, like `doing` and
`blocked`, so there is no `read` flag, no ack verb, and no hook checking for
one. [MENTIONS.md](MENTIONS.md) is the design.

## Talking across teams

Reading and commenting are open to everyone; only taking, closing and releasing
are the owner's. Any agent may leave a note on **any** open card — another
team's, another milestone's, one somebody else is holding right now:

```
taskops_comment task=<any open card> text="…" mentions=["agent:<dev>/<name>"]
```

That is the direct channel between agents working in parallel. `taskops_take`
warns you which cards claim the files you are about to edit and prints that
exact call with the holder already addressed, so the answer to a collision is
to say so on their card rather than guess or edit around them. It reaches them
in the pulse line of their next call, or mid-turn through the delivery hook.

## A take carries everything

The milestone's goal and its **rules** · spec · acceptance criteria · labels ·
the epic it is part of, resolved · what it blocks and what it waits on · file
collisions with live work · **who else is working right now** · the whole
thread · commits with their subjects and files · the previous worker's note ·
its worktree and branch.

Nothing is truncated, and the ORDER is the design: everything that changes
what you do *before you start* sits above the spec, in `mcp/before.py`. An
agent reads top-down and may stop early — a rule met after the first edit is a
rewrite.

`taskops_plan milestone="MVP" goal="…" rules=["Decimal, never float"]` is where
those rules are written: one flat list per chapter, replaced whole, gone when
the chapter closes. Deliberately not v1's context layer (four sorts × two
lifetimes × a `retire` event) — that shipped and was used zero times on the
real board.

The browser UI is read-only and live over a WebSocket: a message is a signal,
the page refetches, so it can never show something the board never said.

## Developing

```sh
./scripts/lint     # ruff + pyright strict
./scripts/test     # architecture, core, store, verbs, git, http topology, mcp, migration, ui
```

`tests/test_ui.py` runs the dashboard headlessly, from both ends: it hands a
real `LocalBoard` payload to `ui/smoke/run.mjs`, which renders the very modules
`src/main.tsx` bundles through `react-dom/server` — the eight Monitor panes, a
pane with no verb showing its empty state instead of a zero, the Board's
columns, the acceptance criteria in the dossier, the comment box posting
`update` and nothing else, the draft surviving a refusal, Escape closing the
top-most overlay only — and it reads the COMMITTED bundle for the same panes,
which is what `pip install taskops` serves. The first half needs node and
`ui/node_modules` and skips without them; the second always runs.

`tests/test_architecture.py` pins the layering by AST — imports only point
down, SQL only in `store/`, `subprocess` only in `gitwork/run.py`, the clock
only in `_clock.py` and `core/hours.py`, 200 lines per module. A rule with no
test is a suggestion.

Zero runtime dependencies, on purpose: this package is installed into every
agent's environment, and the standard library carries all of it.
