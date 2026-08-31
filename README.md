# taskops

A shared work board — milestones → cards → subtasks — for teams of coding agents
working in parallel, with a human who decides. Zero runtime dependencies.

The truth is an append-only event log; the cache is disposable and the leases are
not. Agents stay out of each other's way by mechanism, not by prompt: a lease (one
row, one winner), a worktree (one directory each), a branch pinned to that
directory for life. `main` is written by a person.

**The CLI behaves like git: it connects, it never manages.** Moving a card from the
terminal does not exist — that is MCP. (v1 grew 35 management commands, each one a
second way to do something the tools already did, and the two ways drifted.)

**Why any of it is shaped this way: [ARCHITECTURE.md](ARCHITECTURE.md).** How to
work in this repo: [CLAUDE.md](CLAUDE.md).

## How it fits together

One server, many boards, one board per repo. Read this once and nothing below
can be misread:

```
        ONE host, set up ONCE in its life            YOUR LAPTOP, per repo
   ┌──────────────────────────────────────┐
   │  taskops serve --root ~/boards       │      ~/code/tienda   ──┐
   │                                      │      ~/code/api      ──┼─ each joined
   │    ~/boards/tienda/   ← a board      │◀─────~/code/landing  ──┘   to one board
   │    ~/boards/api/      ← a board      │       (no ssh, ever)
   │    ~/boards/landing/  ← a board      │
   └──────────────────────────────────────┘
```

* **The host**: one process, one port, every board you will ever make. You ssh
  into it exactly once, to install it and register your key.
* **A board**: one directory on that host. Created from your laptop with
  `taskops board create`.
* **A repo**: joined to one board. A clone carries the board's address
  (`.taskops/board.json`, committed), so `taskops join` is the whole step;
  `taskops remote add` covers a checkout that carries none.
* **Your agents**: they never touch any of this — they talk to the board through
  the eleven MCP tools.

## Install

```sh
uv tool install taskops-cli        # or: pipx install taskops-cli · pip install taskops-cli
```

The PyPI distribution is `taskops-cli`; the command it installs is `taskops`.
Install into the interpreter you will actually run `init`/`join` from: the git
hooks pin `sys.executable` at that moment, so a `python3` without `taskops`
importable leaves commits un-stamped, silently.

## The CLI

```
taskops init                              a local board in this repo
taskops join [<name>] [--invite <id>]     join a board, install the hooks
taskops remote add <url>                  the host this checkout operates, like git's origin
taskops serve                             host boards — the page and /git open per declared forge
taskops server init                       bootstrap THIS host: its owner and their ssh key
taskops board create|ls|push|pull|rm      the boards on a host
taskops board visibility|forge            who may read one · which repo's team is enrolled
taskops invite <who>                      a single-use link
taskops revoke --key|--invite             a key or an invite stops working
taskops tidy                              remove worktrees whose work is in the trunk
taskops ui                                the dashboard: serve if needed, open the browser
taskops hook …                            internal: what the installed hooks call
```

### Starting a board

```sh
taskops init                     # local: .taskops/board/ + 2 git hooks + .mcp.json
```

Joining a hosted one is bare, like every other verb — the host is recorded once
and the key is discovered the way ssh discovers one:

```sh
taskops join                              # a clone: board.json carries the address, done
taskops join my-project --invite <id>     # first time by invite: it enrols your key too
taskops remote add https://host:8787      # no carried address? record the host once…
taskops join my-project                   # …and name the board
taskops join my-project                   # no key + public board: read-only window
```

Keys exist so tokens do not travel: what lands on disk is a session that renews
itself, never a token anybody copies. Flags: `--key <path>` overrides the
discovered key · `--as <actor>` when your unix user is not the principal's name ·
`--discard-local` when this repo already has a local board with events. The old
full-URL form (`taskops join "<url>?token=…"`) keeps working — boards joined
before keys existed never rot.

**A dev never types anything about GitHub.** On a board that declared a forge
(below), the owner's `taskops board forge` has already enrolled the team from
their published ssh keys, so the bare `taskops join` above finds your key, signs
a challenge with it and is in. No token of yours travels anywhere — there is no
flag that would carry one.

**Restart your Claude Code session after either** — MCP servers load once, at
session start, from `.mcp.json`.

### Hosting — ONE server for ALL your projects

Set a host up once, ever. **One process serves every board you will ever make**
— there is no server per project and no server per board. The author's host
runs six boards on one port.

`--root` is the only thing to decide, and it is just **a directory you pick on
the server where the boards get stored**. `~/boards` below is an example, not a
convention: any path works. Every immediate subdirectory of it IS a board,
served at `/<its name>`:

```
~/boards/                     ← --root: you chose this path
├── server.sqlite             the host itself: who may sign in, and their ssh keys
├── allowed_signers           derived from it, whole, on every change
├── live.sqlite               the sessions this host has handed out
├── mi-proyecto/              ← a board, served at https://host:8787/mi-proyecto
│   ├── events.jsonl              THE TRUTH: append-only, this is the board
│   ├── cache.sqlite              derived — delete it and it rebuilds
│   └── live.sqlite               who holds which card right now
└── otro-proyecto/            ← another board, same process, same port
    └── …
```

Nothing else is in there, and nothing outside it is touched. To move the host
to another machine you copy that one directory.

Three commands on the box, one time in its life. **This is the only ssh in the
design** — after it, nothing on a host is ever administered over a shell:

```sh
ssh <host> 'pip install taskops-cli'
ssh <host> 'taskops server init --root ~/boards --key -' < ~/.ssh/id_ed25519.pub
ssh <host> 'taskops serve --root ~/boards --host 127.0.0.1 --port 8787'   # under pm2/systemd
```

`server init` writes `server.sqlite` + `allowed_signers` and makes YOU its
owner; `serve` is the long-running process. It binds loopback on purpose — TLS
and the public name are a reverse proxy's job.

### Per project — no ssh, ever again

From your laptop, signed by the key `server init` registered. This is the part
you repeat per repo; the host above is never touched again:

```sh
taskops remote add https://host:8787 [--replace]   # once per checkout
taskops board create [<name>]                      # defaults to the directory's name
taskops board push                                 # this repo's LOCAL board becomes that one
taskops join <name>                                # or: a teammate connects to an existing one
taskops board pull [<name>]                        # the reverse: it comes back down, verified by id
```

### A board's whole life, and what each step destroys

```
  taskops init         board create+push       board pull            board rm
 ┌──────────┐        ┌──────────────┐       ┌──────────────┐      ┌──────────────┐
 │ a LOCAL  │  ───▶  │ LIVE on the  │  ───▶ │ a SNAPSHOT   │ ───▶ │ off the host │
 │  board   │        │     host     │       │ back in here │      │  altogether  │
 └──────────┘        └──────────────┘       └──────────────┘      └──────────────┘
  destroys            destroys nothing:      destroys nothing:     DESTROYS the host's
  nothing             the local board is     the host keeps its    board — the only step
                      RENAMED to .taskops/   board byte for byte   that destroys anything,
                      board.local-<date>     and goes on moving    and it says so in the
                                                                   name of its own flag
```

Both transfers flip this checkout's config **last**: stream the history, prove
every event id arrived, then change what the repo reads. A failure above that
leaves the repo as it was and the command is simply run again.

What a pull leaves you is a **snapshot that stops moving** — nothing syncs
afterwards, so a card taken on the host a second later never appears here, and
the command prints that sentence itself every time. `remote.json` keeps its
login, so `board create` and `board push` still go to the same server.

And the admin surface for any board on that host, from anywhere:

```sh
taskops board ls
taskops board visibility <name> public|private     # owner only
taskops board rm <name>                            # owner only — see below
taskops board forge <owner>/<repo> [--need push|admin]   # owner only: declare AND sync the team
taskops board forge --clear                        # invite-only again
taskops invite <who> [--board <name>]
taskops revoke --key SHA256:… | --invite <id>      # a GitHub-enrolled key too
```

`board rm` **refuses** unless this checkout already holds that history, and names
both ways out — take the history down first, or say out loud that you are
destroying it. The judgement is the host's, against the board's real event ids:

```sh
taskops board rm <name>                      # refused: 402 of the host's 402 events are not here
taskops board rm <name> --discard-history    # destroys it anyway
```

There is no `--force` and there will not be one: a flag that does not name what
it overrides is how somebody destroys a history they meant to keep.

**Declaring the forge** — the repo whose team works on a board — is a board
fact, `op=forge` with `{host, repo: <owner>/<name>, need: push|admin}`, absent
until an owner records it and cleared again with `--clear`. A board that was
never opted in is invite-only, exactly as before.

**The board says so out loud.** The declared forge rides on the `board` payload
— derived per read from the one event that declared it, never a second copy —
so anybody who can read the board can see what opens it, and the dashboard
draws it under the board's own identity as
`github.com/<owner>/<repo> · push`. Before that, the only two parties who knew
were the owner who typed the command and the stranger the sync had not enrolled.
A board with no forge sends no such key at all, which is what keeps every older
reader working unchanged.

**And declaring it SYNCS the team, in the same command.** `taskops board forge
<owner>/<repo>` lists that repo's collaborators with the declared access (one
authenticated call to GitHub, paginated, with the owner's own token — `gh auth
token`, else `$GITHUB_TOKEN`, else a hidden prompt), reads each one's published
ssh keys from the PUBLIC `https://github.com/<login>.keys`, and enrols them all
in one batch. Re-run it to re-sync; a run that changes nothing writes nothing.

```
bernatch22/taskops — 4 collaborator(s) with push
  enrolled  ana, dan, leo
  keys      3 added
  no ssh key published on GitHub — 1, not enrolled:
    mia            github.com/mia.keys is empty — taskops invite mia
  on this host but NOT a collaborator any more — 1, nothing revoked:
    tomas          taskops revoke --key SHA256:…
    a principal introduced by invite belongs here legitimately — revoking is yours
```

It **adds only**. Somebody who lost push is reported with the exact `revoke`
command and nothing else happens: a principal introduced by an invite is not a
GitHub login and a pruning sync would retire them for existing. The owner is
never in that list. The token is spent on the collaborator pages and on nothing
else — it never reaches the taskops host, which receives principals and ssh key
lines and does not know what GitHub is.

### The whole flow, and why cloning is not enough

Cloning the repo gives you the board's ADDRESS — `.taskops/board.json` is
committed and travels with the code — but the host has never seen you: it is a
different server from GitHub, sharing no session and no cookie with it. The
owner's sync is what closes that gap, before you ever type anything, and then
`taskops join` — no URL, no flag, no token — is the whole of your side.

```
        GitHub                                the board HOST
   <owner>/<repo>, private                principals + allowed_signers
          |                                          |
 0. taskops board forge <owner>/<repo>   ← the OWNER, once, from their laptop
    |                                                |
    |-- their own token (gh auth token, else $GITHUB_TOKEN, else a hidden
    |   prompt — never a flag value: the shell writes those into
    |   ~/.zsh_history before the process starts) lists the collaborators
    |   with <need>, and github.com/<login>.keys — PUBLIC — gives their keys
    |                                                |
    |-- POST /rpc members.enroll ------------------->|
    |      { members: [{principal, keys}, …] }       |
    |                                    it writes two rows per person:
    |                                      principals:      <them>, member
    |                                      allowed_signers: <them> ssh-ed25519 …
    |
    the token dies with that command. It reaches neither disk nor the host.
          |                                          |
 1. git clone  ->  the code, and .taskops/board.json (the address).
                   remote.json is 0600 and gitignored: no credential travels.
          |                                          |
 2. taskops join   (the carried address, and the key ssh already discovered)
    |                                                |
    |-- POST /login: your key signs a challenge ---->|
    |                            checked against allowed_signers -> 12h session

    from here on GitHub never participates again, and it never saw you join:

    every session:  your key signs a challenge  ->  the host checks it
                    (~/.ssh/id_ed25519)             against allowed_signers
                                                    -> a 12h session
```

The alternative — the host re-checking GitHub, or each dev POSTing their own
token to be verified at the door — would mean somebody's credential travelling
for a fact the owner already holds. That is the whole category of problem this
removes: there is no token to steal because there is none stored, and now none
that leaves the owner's machine either.

**One consequence, stated plainly: access is granted automatically and taken
back by hand.** Losing push on the repo does not close the board, because the
credential is no longer GitHub — it is the enrolled key. Remove it with
`taskops revoke --key SHA256:…`, which is the same verb an invite-enrolled key
takes.

No URL and no `--key` after `remote add`: the host is recorded in the checkout,
`board create` records the name, and the key is **discovered** the way ssh
discovers one — `~/.ssh/id_ed25519`, `id_ecdsa`, `id_rsa`, in that order.

Shared flags on the board/invite/revoke verbs: `--key <path>` overrides the
discovered key (on `revoke` it is `--sign-key`, since `--key` there is the
fingerprint being retired) · `--as <principal>` names who the key belongs to ·
`--root <dir>` is the break-glass path that runs against the files ON the box,
for the day the server is down or the owner's key is lost.

`<host>/<name>` also works anywhere `<name>` does — the URL form, as in git.

**Public means GitHub's thing:** anonymous READ, a write that always needs a
registered key, no third state. Anyone may then `taskops join <url>` with no
invite — a read-only join that mints nothing and registers no key.

**After a verified push there is exactly ONE source** — `.taskops/board/` is
renamed to `.taskops/board.local-<date>`, a dead archive nothing reads again, and
there is no `--force` on a push either.

## The eleven MCP tools

The only management interface. Every tool takes `repo_path=` and `actor=`.

```
taskops_board      THE pulse: what the board is waiting for, grouped by the move
                   each card needs. Open every turn with this
taskops_card       one card in full — spec, thread, graph, collisions, worktree;
                   or query=<text> to search titles and specs
taskops_plan       the whole tree in ONE call: a milestone and its cards, deps
                   included. `after`/`parent` take an index into this call
taskops_assign     assign cards, cut a worktree each, return a brief per card
taskops_merge      integrate DONE cards into the milestone branch (--no-ff);
                   milestone= lands a finished chapter. main is never touched
taskops_take       claim your card and get everything back
taskops_update     change the CARD: close, hand in for review, hand back, drop,
                   retitle, re-spec, re-prioritise, declare a dependency
taskops_review     the verifier's one door: claim a submitted card, then
                   verdict=pass|changes note=…
taskops_comment    say something on ANY card, including one somebody else holds
                   and a closed one. mentions=[…] addresses it to them — on an
                   OPEN card: a closed thread delivers nothing
taskops_activity   a whole chapter's story in ONE read: every card's standing,
                   commits with numstat, where it merged, the reports filed on
                   it. since=<seq> returns only what moved; depth=full adds each
                   spec and thread. Never a diff — follow branch and sha into git
taskops_filed      register a report you already COMMITTED under
                   .taskops/reports/: path, title, sha. The board keeps the
                   pointer, never the prose
```

`plan`, `assign` and `merge` are the orchestrator's (`dev:<name>`); `take` is a
worker's (`agent:<dev>/<name>`). Reading and commenting are open to everyone —
only taking, closing and releasing belong to the holder.

Three states are stored — `open`, `done`, `dropped`. `ready`, `doing`, `blocked`,
`stalled`, `review`, `reviewing`, `changes` and `mention` are all derived per read,
which is why there is no `recover` verb and no mark-as-read.

## Reports — the narration a machine cannot regenerate

A report is what an agent understood, and until now it died in a chat
transcript. It joins the board the way a commit does: **the file lives in git,
the board holds a pointer.** Four steps, in this order, and the order is the
whole design — the file is committed BEFORE it is registered, because a pointer
to bytes that are not in history yet is a pointer to nothing.

```
1. read the chapter    taskops_activity milestone=ms-… depth=full
2. write the file      .taskops/reports/<something>.html   (or .md, .txt)
3. COMMIT it           git add + git commit — in your own worktree
4. register it         taskops_filed path=… title=… sha=<that commit> milestone=ms-…
```

Then `taskops ui` lists it under the chapter's **Reports** tab and renders it
full width, read out of **your own clone** at that sha — the local dashboard
never asks the server for the bytes. A host running `taskops serve` answers
`/git` too, from a bare read-only mirror of the board's DECLARED forge — the
hosted window, for the reader with no clone. A board that never declared one
refuses with a sentence naming `taskops board forge <owner>/<repo>`.

**The hosted page is at the board's OWN address.** `https://<host>/<board>/`
IS the dashboard — not a sub-path under it — and the machine doors sit under a
prefix that can never collide with a page asset:

```
https://<host>/<board>/            the page          (also /<board>, no slash)
https://<host>/<board>/app.js      its assets        style.css, index.html
https://<host>/<board>/api/rpc     the verbs         also /<board>/rpc
https://<host>/<board>/api/git/…   diffs from the mirror   also /<board>/git/…
https://<host>/<board>/api/feed    the live feed     also /<board>/feed
https://<host>/healthz             the host itself
```

The right-hand spellings are 0.5.0's and they keep answering, unprefixed and
un-redirected — including `/<board>/ui/`, which was the page's address for one
day. Links were pasted, agents and the MCP client are configured against them,
and `taskops ui`'s upstream forward speaks them, so they are a contract now
rather than a legacy. Re-derivable at any time with `sh smoke.sh <host>
<board>`.

**Reading one, from the other side.** Everything above is the author's half; a
reader needs no ceremony at all. Three doors onto the same bytes:

```sh
taskops ui                             # the Reports tab: the chapter's list, rendered
```
```
taskops_activity milestone=ms-…        # the same list as data: {path, title, sha}
                                       # newest first, with the honest total beside it
```
```sh
git pull && $EDITOR .taskops/reports/<name>.md    # it is a committed file, nothing more
```

Which one you want depends on what you are: a human wants the tab, an agent
wants `activity` and then opens the file in its own worktree. There is no
`read_report` tool and there is not going to be one — the bytes are already in
the clone, and a tool that returned them would be a second way to do what
opening a file does, with the whole chapter's prose pushed through context.

The one failure worth naming: **the report renders blank or 404s when your
clone does not have that sha yet** — the pointer is fine, your git is behind.
`git fetch --all` and reload. The board deliberately cannot help you here; it
never had the bytes.

The rules that shape it, each of them the reason a step exists:

* **The log stores a reference, never the prose.** The `report` event body is
  `{path, title, milestone, sha}` and nothing else, so a 200KB report grows
  `events.jsonl` by a few hundred bytes. Same rule that keeps diffs out of the
  log: a commit is recorded as a sha and a numstat, never a patch.
* **`.taskops/reports/` is a shape, not a convention.** `core/reports.py::under()`
  is the one place that decides whether a path is a report path, and both ends
  ask it — the verb that registers one and the `/git` door that later reads it.
  A traversal, an absolute path or the bare directory is refused, never
  repaired. The door is for reports; it is not a file server.
* **A report is untrusted HTML, and it is read in a sandbox.** It renders inside
  `<iframe sandbox="allow-scripts" srcdoc=…>`. Scripts run — a panorama report
  is a self-contained page and rendering it dead ships a broken document — but
  never beside `allow-same-origin`, which together are not two permissions but
  the absence of the sandbox. The frame gets an opaque origin: no parent, no
  `localStorage`, no cookie. The dashboard's token is in that origin, so this is
  a boundary and not a preference. A Markdown report is served as
  `text/markdown` and rendered by the dashboard's own markdown renderer
  (`ui/src/markdown.ts`) — it emits no HTML, so it cannot run anything and
  needs no frame. A `text/plain` report is not framed at all.
* **The list is a fold, never a table.** "Which reports does this chapter have"
  is answered from the `report` events on every read, newest first, capped with
  the honest total beside it.

## Developing

```sh
uv run ruff check src tests       # lint
uv run pyright                    # types, strict
uv run pytest                     # the whole suite
cd ui && npm ci                   # once
cd ui && npm run check            # typecheck + build + smoke + committed-bundle diff
uv run python -m taskops.cli ui   # the dashboard, token included
```

The dashboard is built, not hand-written: source in `ui/`, and `node build.mjs`
writes the bundle into `src/taskops/ui/`, **which is committed** — that is what
makes `pip install taskops` serve a dashboard with no node toolchain.

`tests/test_architecture.py` pins the layering by AST — imports only point down,
SQL only in `store/`, `subprocess` only in `gitwork/run.py`, the clock only in
`_clock.py` and `core/hours.py`, 200 lines per module. A rule with no test is a
suggestion.
