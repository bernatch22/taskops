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
uv tool install --from ~/taskops-v2 taskops
```

**Local — one machine, no server.** For solo work, or before you trust the
thing enough to host it:

```sh
cd your-project
taskops init                # .taskops/board/ (log + 2 sqlite files), 2 git hooks, .mcp.json
```

**Remote — a team, one shared board.**

```sh
# once, ON THE HOST — the only ssh in this design: it is where trust enters
taskops server init --root ~/taskops-boards --key ~/.ssh/id_ed25519.pub
taskops serve --root ~/taskops-boards &              # host: /rpc, /feed, /healthz — no dashboard
```

That is the last shell on the box. Everything after it runs **from your laptop**,
signed by the key `server init` registered — creating the board included:

```sh
cd your-project
taskops remote add https://host:8787   # once per checkout — git's `remote add origin`
taskops board create                   # the directory's name, or `board create my-project`
taskops board push                     # a LOCAL board becomes that one
```

**No URL and no `--key` after the first line**, on purpose: the host is recorded
in this checkout (`.taskops/remote.json`, uncommitted — git keeps origin in
`.git/config` for the same reason), the board's name is recorded by `board
create` so you never type it twice, and the key is **discovered** the way ssh
discovers one — `~/.ssh/id_ed25519`, `~/.ssh/id_ecdsa`, `~/.ssh/id_rsa`, in that
order. `--key <path>` is the override, exactly as `ssh -i` is, and `--as
<principal>` names who the key belongs to when it is not your unix user. The
explicit `taskops board create https://host:8787/my-project` keeps working
unchanged — it is the URL form, as in git.

**After a verified push there is exactly ONE source.** The config flips only
once the server has the history and the counts agree, and then `.taskops/board/`
is RENAMED to `.taskops/board.local-<date>`: a dead archive, which no process
reads or writes again. Nothing syncs, nothing is kept in step — this repo now
reads the hosted board and only that. Delete the archive whenever you like; it
is there so the bytes that were pushed are still findable the day after.

The rest of the admin surface, from the same laptop and with the same session:

```sh
taskops board ls                                     # every board on the host
taskops invite ana --board my-project                # one-time link, 7 days
taskops revoke --invite <id>                         # or --key SHA256:… to retire a key
taskops board visibility public                      # anyone may WATCH it
```

**A board is PRIVATE until its owner publishes it**, and public is GitHub's
word for GitHub's thing: anonymous READ, and a write that always needs a
registered key. There is no third state. Anyone may then
`taskops join https://host:8787/my-project` with no invite at all — config
written, nothing minted, no key registered — and `taskops ui` opens a viewer's
window whose comment box says so instead of offering a form it cannot send.
An anonymous crawl of a public board leaves `events.jsonl` and `live.sqlite`
byte-identical: reads renew no lease and record no presence for `anon`, which
is pinned as a hash comparison in `tests/test_topology.py`.

Ana, in **her own** checkout of the same repo:

```sh
taskops join "https://host:8787/my-project?invite=<token>" --key ~/.ssh/id_ed25519
```

`--key` is what turns the credential into something nobody has to look after:
the invite and the PUBLIC half of that key travel in the same call, the server
burns the invite and registers the key, and the key signs Ana in on the spot.
From then on `remote.json` is a SESSION cache — when the token runs out (12
hours), the next call signs in again by itself, with nobody asked for anything.
Delete the file and it comes back. Without `--key` the join is the one it always
was and the token is a standing one, which is why every board joined before this
keeps working untouched.

**A key works on every one of these verbs, and it is what makes the FIRST one
runnable.** A fresh laptop has no session, and the owner of a brand-new host has
nothing to join — the invite `join` wants is minted by `taskops invite`, for a
board nobody has created yet. So the discovered key (or `--key <path>`) signs
you in on the spot, `--as <principal>` names who that key belongs to when it is
not your unix user, and the login is remembered: the second command needs no
flags at all. The refusal when there is no key anywhere lists what it tried.
(On `revoke` the signing key is `--sign-key`, because there `--key` is already
the fingerprint being retired.)

That same session is what `board create`, `board ls`, `board visibility`,
`invite` and `revoke` travel on: they are **server-scope** calls to the host's own `/rpc`
(`src/taskops/http/admin.py`), authorized by the principal's role — owner,
member, anon — and not by a board credential, which says nothing about the host.
A member calling an owner verb is refused naming the role that may. The host is
taken from `remote.json` — written by `taskops remote add` or by the join that
registered the key — so no address is repeated, and there is deliberately **no
host-alias registry**: a TABLE of names would be a third place a server's
address lives, and the first to drift. One host per checkout, in the file that
already holds it, is git's answer and it is this one.

**Break-glass, and it is not deprecated.** `--root <dir>` runs `invite` and
`revoke` against the files, on the machine that holds them — for the day the
server is down or the owner's key is lost. A system whose only door is its own
API cannot be repaired when that API is what broke.

The login is OpenSSH's own mechanism, the same one signed commits use: the
server answers a random single-use challenge, `ssh-keygen -Y sign` signs it, and
`ssh-keygen -Y verify -f allowed_signers` is what decides. No pip dependency and
no crypto of ours. One limit, stated: `-Y sign` wants the private key FILE, so a
key that lives only inside a running ssh-agent cannot sign yet — taskops says so
in a sentence rather than failing obscurely.

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
It **always serves right there**, in the checkout you ran it from (blocking,
ctrl-c stops it; an agent runs it in the background) and opens the browser with
a minted local token; run it again and it just reopens the running one.

A board on a server changes exactly one thing: who answers `/board/rpc`. The
window forwards it, with the credential `join` saved in `.taskops/remote.json`,
and the page never sees that credential — it holds only the local token. It used
to redirect you to the server's own `/ui/` instead, and that page is served by a
machine with no repository, so every diff in it fell through to a link.

**The server no longer serves a dashboard at all.** `taskops serve` answers
`/rpc`, `/feed` and `/healthz`; its `/ui/` answers one sentence naming
`taskops ui`, at `410 Gone`, and there is no flag that puts a bundle back on it.
The bundle still ships inside the wheel — that is what `taskops ui` serves. A
board host having no clone is not an accident to work around: a dashboard shows
diffs, a diff is read from the reader's own clone, so a window served from the
server could only ever be a degraded one. The binary serves the window; the
server serves the truth (`src/taskops/http/static.py` carries the post-mortem).

The diffs the dossier shows — **Files changed** on a card, the patch under a
commit — come from **your own clone**, read on demand by the host `taskops ui`
started inside it; nothing is stored on the board, in either mode. A host with
no checkout (`taskops serve`, which sits in a directory of boards) mounts no
such door and says so, and the page falls back to the GitHub link when the repo
has an origin, or to one plain sentence when it does not.

On a shared board most branches belong to other people's cards, and a card's
branch reaches `origin` when it closes. Until you fetch, it is simply not on
your disk — so the pane says exactly that and names the command:

```
tk-91a27e is not in your clone yet — `git fetch origin tk-91a27e` brings it.
```

Nothing is ever fetched for you: that would move a branch under a worktree
somebody is sitting in.

### How code travels between two devs

**The board carries references; git carries objects.** A shared board is an
events API and nothing else — it never holds a repository, a clone or a git
credential, so a sha on a screen is a *name*, and the bytes it names live in
git. The meeting point is whatever `origin` is: GitHub, GitLab, a bare repo on
a box, it makes no difference.

So the two halves are:

1. Berna closes a card — `taskops_update task=tk-91a27e status=done note="…"`.
   The board records the commit that closed it, and the client that made the
   call (the one machine with the repo) pushes `tk-91a27e` to `origin`.
   **Best effort, never a gate**: no origin, no network, a protected branch —
   the card is closed either way and the board carries the sha regardless.
2. Ana, in her own clone of the same repo, fetches it and reads it locally:

   ```sh
   git fetch origin tk-91a27e
   git log --oneline main..FETCH_HEAD
   git diff main...FETCH_HEAD
   ```

   Her `taskops ui` shows the same diff without leaving the browser, because it
   reads *her* clone — and until she fetches, it says so and names that exact
   command instead of pretending the branch is empty.

The same push happens at the other two lifecycle moments that already existed:
integrating a card into its milestone branch, and landing a milestone. Push
failures are silent by design and are never recorded on the board — a push is
infrastructure, not a board fact, and the next lifecycle moment pushes again.
Pinned against a real HTTP board and a real `origin` in
`tests/test_mcp.py` ("code travels by git, and the board is REMOTE").

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

Four tabs, in Nova's order — **Monitor** (`ui/src/pages/Monitor.tsx`, the
default), **Board** (`ui/src/pages/Board.tsx`), **Actors**
(`ui/src/pages/Actors.tsx`, one card per DEV with its agents as lines inside it,
each opening into a full overlay that groups the window into a pane per calendar
day, newest first, with an hour that folds open to its sessions)
and **Worktrees**
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

## Deployed — how a real host actually runs

`taskops.bernardocastro.dev` runs this, four boards, since 2026-08-08. A board
host is **not** a code tree, so it does not ship with a code-rsync deployer: it
is one wheel installed into a venv, plus a directory of board logs the install
must never overwrite.

```sh
uv build --wheel                                    # in this repo
scp dist/taskops-*.whl <host>:/tmp/                 # ship the artifact, not the tree
ssh <host> 'python3 -m venv ~/taskops-v2-app/.venv
            ~/taskops-v2-app/.venv/bin/pip install /tmp/taskops-*.whl'
```

Then one process, pointed at the boards directory — every immediate
subdirectory of `--root` is a board, reachable as `/<name>`:

```sh
~/taskops-v2-app/.venv/bin/taskops serve \
    --root ~/taskops-v2-server --host 127.0.0.1 --port 2181
```

It binds loopback on purpose; TLS and the public name are a reverse proxy's
job, and the proxy must pass `Upgrade`/`Connection` through or the dashboard's
live feed silently degrades.

**That is the last ssh.** The two commands above — install and `server init` —
are where trust enters, because authorising a remote bootstrap would need a
credential the host does not have yet. Every operation after them is a `taskops`
command run from wherever you are, signed by the key `server init` registered —
**the first board included**, which is the one case that used to send you back
to the box: a laptop with no session signs in with the key ssh itself would use:

```sh
# a laptop that never joined records the host once, then everything goes bare
taskops remote add https://<host>             # git's `remote add origin`, per checkout
taskops board create <name>                   # and now a board exists (key: discovered)
taskops board ls https://<host>               # every board here, with size and last activity
taskops invite <who> --board <name>           # the join line, minted by the host that honours it
taskops revoke --invite <id> | --key SHA256:… # take one back (--sign-key signs YOU in)
taskops board visibility <host>/<name> public|private   # owner only — public means
                                              # anonymous read, never anonymous write
```

**A local board becomes a hosted one with one command**, and it is the same
four above plus a fifth — never a file copy:

```sh
taskops remote add https://<host>   # once, if this checkout has no remote yet
taskops board create               # an empty board, on the host — its name is remembered
taskops board push                 # the history crosses, verified, and the config flips
```

Run from the repo whose `.taskops/board/` holds the history. The order is the
safety and the config flips LAST: the target must be empty, nobody may be
holding a lease, the whole log is streamed through the server's `board.ingest`,
the counts are compared per event kind — and only then does `board.json` point
at the host, with the local board renamed to `.taskops/board.local-<date>/`
rather than deleted. A failure anywhere above leaves the repo exactly as it
was, and the command is simply run again: event ids are `sha256` of their own
content, so an interrupted push re-runs to a no-op and continues. There is no
`--force`, deliberately — a non-empty target means two histories, and putting
them in an order they never had would be fabricating a timeline.

Add `--invite <token>` the first time, so the host registers the key in the same
call. And `taskops join` REFUSES onto a repo whose local board has events,
naming both ways out (`board push`, or `--discard-local` to archive it and join
anyway) — before this, the join silently made that history invisible forever.

There is no `scp` of an `events.jsonl` in this file and there must not be one:
storage is an implementation detail, and a file name in an instruction is that
detail leaking into the interface.

**A host serves no dashboard.** `/rpc`, `/feed` and `/healthz` are the whole
public surface; `https://<host>/<board>/ui/` answers `410` and one sentence.
Everybody on the team opens the board the same way, and it is not a URL you
send them — it is a command they run in their own checkout of the repo:

```sh
taskops join "https://<host>/<board>?invite=<token>"   # once
taskops ui                                             # every time
```

That window is served from their laptop, reads the board over `/rpc` from this
host, and reads every diff from their own clone. Nothing about it needs the
host to know what a repository is.

### Upgrading a host

The boards are outside the install, so an upgrade is the package and nothing
else — no migration, no rsync, nothing on disk to rewrite. If an upgrade path
ever wants to touch a board directory, that is a decision to take to a human,
not a step.

```sh
uv build --wheel                                    # from the commit you mean to ship
python3 -c "import zipfile,sys
w = zipfile.ZipFile(sys.argv[1]).read('taskops/ui/app.js').decode()
print({m: w.count(m) for m in ('chapter-goal', 'markdown-inline')})" dist/taskops-*.whl
# THE ROLLBACK, first — the wheel that is installed NOW, named for when it was:
ssh <host> 'cp /tmp/<the wheel installed now>.whl ~/taskops-v2-app/rollback/taskops-<version>-<when>-preupgrade.whl'
ssh <host> 'mkdir -p /tmp/<card>'                   # a dir per upgrade, never bare /tmp
scp dist/taskops-*.whl <host>:/tmp/<card>/
ssh <host> '~/taskops-v2-app/.venv/bin/pip install --force-reinstall /tmp/<card>/taskops-*.whl'
ssh <host> 'pm2 restart taskops-v2'
```

**Ship into a directory named for the upgrade, not into bare `/tmp`.** Earlier
runs leave their wheels there, so `pip install /tmp/taskops-*.whl` expands to
several paths and pip refuses the lot with `Invalid wheel filename (wrong number
of parts)` — which the shell reports *after* `pm2 restart` has already run in the
same chain, i.e. a restart onto the OLD code that looks like a deploy. And do not
rename a wheel on the way: pip parses the filename, so `taskops-<card>.whl` is
refused before it is ever opened.

Three things that are not optional, in this order:

1. **Record the rollback before replacing anything** — keep the wheel that is
   installed now, under a name that says when it was installed. If the new one
   fails to serve, put it back first and report second: an outage is worse than
   a stale render. **And prove it is the pre-upgrade one**, because a leftover
   `/tmp` wheel is a guess: compare every `taskops/*.py` inside it against
   site-packages by md5, and check it still carries whatever the upgrade
   withdraws (for the 410 upgrade: `taskops/http/static.py`). An upgrade that
   withdraws nothing — most of them — proves the same thing from the other
   side: the rollback wheel must NOT carry what the new one ADDS (for the
   owner upgrade: `taskops/http/login.py`). Either way the claim is that the
   wheel you kept is the one from *before*, not merely a wheel.
2. **The wheel must carry the built dashboard** — the check above, on the
   artefact, before it goes anywhere. Not for the host, which serves no
   dashboard and never reads those bytes: it is the SAME wheel a teammate
   `pip install`s to get `taskops ui`, so a wheel built over a stale
   `src/taskops/ui/` ships everybody a stale window. `tests/test_ui.py` names
   the markers.
3. **Verify by CONTENT at the real domain.** A 200 is not the claim, and there
   is no page to look at — so the claim is the DATA: call `/rpc` through the
   public name (the `curl` below) and reconcile the counts against what the
   board actually holds. What the dashboard renders is verified where the
   dashboard runs: `taskops ui` in a checkout joined to this host.

Two things a host must have that no exit code will tell you:

* `GET /healthz` answers `{"ok": true, "seq": 0, "data": {"boards": N}}` — **N is the number of
  boards this process has opened SO FAR**, not how many exist: a board is
  mounted the first time somebody addresses it, so a freshly restarted process
  honestly says `1` after one request and `4` once all four have been asked
  for. It catches a server that came up beside its data instead of on it —
  touch each board first, then read it. **`/rpc` is what mounts a board**, and
  even a refused one does: `/<board>/ui/` is answered by `http/static.py` before
  any store is opened, so hitting all four `/ui/` leaves the count at 1.
* A credential per board. `taskops invite <who> --board <name>` prints a
  one-time link — over the API, from anywhere, no shell on the box (`--root
  <dir>` is the break-glass path, run ON the host, for when the API is what
  broke); `taskops join` on the other end burns it and mints that machine's
  token into `.taskops/remote.json` (0600, gitignored), a SESSION when the join
  carried `--key`.
  Verify a fresh host by **counts through the real domain**, never by the
  deploy's exit status:

```sh
curl -s -H "Authorization: Bearer <token>" -H 'Content-Type: application/json' \
     -d '{"verb":"board","actor":"dev:<you>","args":{}}' \
     https://<host>/<board>/rpc
```

Migrating a **v1** board is `scripts/migrate_v1.py <v1 events.jsonl> <v2 board
dir>` — `--dry-run` first, and reconcile its counts against the v1 `db.sqlite`
before anything is switched. That script is for v1 boards and nothing else: a v2
board that is local and should be hosted is `taskops board push`, above.
`ARCHITECTURE.md` §17 is the record of doing exactly that against production,
and the order it was done in.

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
| `taskops_merge` — integrate a done card into its milestone branch; `tasks=[…]` or `done=true` integrates the whole chapter in one call, stopping at the first failure | `taskops_review` — the verdict on a submitted card: `pass` or `changes` with a note |
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
`src/main.tsx` bundles through `react-dom/server` — the nine Monitor panes, a
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
