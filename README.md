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
* **A repo**: joined to one board. `taskops remote add` once per checkout, then
  every command runs bare.
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
taskops join [<name>] [--invite|--github] join a board, install the hooks
taskops remote add <url>                  the host this checkout operates, like git's origin
taskops serve                             host boards — an events API, no dashboard
taskops server init                       bootstrap THIS host: its owner and their ssh key
taskops board create|ls|push              the boards on a host
taskops board visibility|forge            who may read one · who GitHub lets in
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
taskops remote add https://host:8787      # once per checkout
taskops join my-project                   # your key is registered: that is the credential
taskops join my-project --invite <id>     # first time: the invite enrols your key too
taskops join my-project --github          # first time, no invite: GitHub vouches for you
taskops join my-project                   # no key + public board: read-only window
```

Keys exist so tokens do not travel: what lands on disk is a session that renews
itself, never a token anybody copies. Flags: `--key <path>` overrides the
discovered key · `--as <actor>` when your unix user is not the principal's name ·
`--discard-local` when this repo already has a local board with events. The old
full-URL form (`taskops join "<url>?token=…"`) keeps working — boards joined
before keys existed never rot.

**`--github` works only on a board that declared a forge** (below), and only for
the first join: having `push` on that repo stands in for an invite, your ssh key
is enrolled, and every call after it is the ordinary signed session — GitHub is
the introduction, never the credential. The token is used for one server-side
call and stored nowhere, which is why it is **not** a flag value: `--github`
takes none, and the token comes from `gh auth token`, else `$GITHUB_TOKEN`, else
a hidden prompt.

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
```

And the admin surface for any board on that host, from anywhere:

```sh
taskops board ls
taskops board visibility <name> public|private     # owner only
taskops board forge <owner>/<repo> [--need push|admin]   # owner only: GitHub opens it
taskops board forge --clear                        # invite-only again
taskops invite <who> [--board <name>]
taskops revoke --key SHA256:… | --invite <id>      # a GitHub-enrolled key too
```

**Declaring the forge** — the repo whose membership opens a board — is a board
fact, `op=forge` with `{host, repo: <owner>/<name>, need: push|admin}`, absent
until an owner records it and cleared again by recording `repo=""`. A board that
never recorded one is invite-only and its `/join/github` door does not exist.

**The board says so out loud.** The declared forge rides on the `board` payload
— derived per read from the one event that declared it, never a second copy —
so anybody who can read the board can see what opens it, and the dashboard
draws it under the board's own identity as
`github.com/<owner>/<repo> · push`. Before that, the only two parties who knew
were the owner who typed the command and the stranger the door refused. A board
with no forge sends no such key at all, which is what keeps every older reader
working unchanged.

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

**After a verified push there is exactly ONE source.** The config flips only once
the server has the history and the counts agree, and `.taskops/board/` is RENAMED
to `.taskops/board.local-<date>` — a dead archive nothing reads again. There is no
`--force`, ever.

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
taskops_comment    say something on ANY open card, including one somebody else
                   holds. mentions=[…] addresses it to them
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
full width, read out of **your own clone** at that sha — the dashboard never
asks the server for the bytes, and there is nothing to serve: a host running
`taskops serve` answers `/git` with a 404, whole.

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
  a boundary and not a preference. A `text/plain` report is not framed at all.
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
