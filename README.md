# taskops v2

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

## Install

```sh
uv tool install --from ~/taskops-v2 taskops
```

Install into the interpreter you will actually run `init`/`join` from: the git
hooks pin `sys.executable` at that moment, so a `python3` without `taskops`
importable leaves commits un-stamped, silently.

## The CLI

```
taskops init                              a local board in this repo
taskops join <url>                        join one (?token= or ?invite=), install the hooks
taskops remote add <url>                  the host this checkout operates, like git's origin
taskops serve                             host boards — an events API, no dashboard
taskops server init                       bootstrap THIS host: its owner and their ssh key
taskops board create|ls|push|visibility   the boards on a host
taskops invite <who>                      a single-use link
taskops revoke --key|--invite             a key or an invite stops working
taskops tidy                              remove worktrees whose work is in the trunk
taskops ui                                the dashboard: serve if needed, open the browser
taskops hook …                            internal: what the installed hooks call
```

### Starting a board

```sh
taskops init                              # local: .taskops/board/ + 2 git hooks + .mcp.json
taskops join "<url>?invite=<token>" --key ~/.ssh/id_ed25519
```

`join` flags: `--key <path>` registers that key and signs you in on the spot ·
`--as <actor>` when your unix user is not the principal's name ·
`--discard-local` when this repo already has a local board with events.

**Restart your Claude Code session after either** — MCP servers load once, at
session start, from `.mcp.json`.

### Hosting

Install the wheel and bootstrap the owner. **These two acts are the only ssh in
this design** — it is where trust enters, and nothing else on a host is ever
administered over a shell:

```sh
uv build --wheel                                    # in this repo
scp dist/taskops-*.whl <host>:/tmp/                 # ship the artifact, not the tree
ssh <host> 'python3 -m venv ~/taskops-app/.venv
            ~/taskops-app/.venv/bin/pip install /tmp/taskops-*.whl'
ssh <host> '~/taskops-app/.venv/bin/taskops server init \
                --root ~/boards --key -' < ~/.ssh/id_ed25519.pub
```

Then one process, pointed at the boards directory — every immediate subdirectory
of `--root` is a board, reachable as `/<name>`. It binds loopback on purpose; TLS
and the public name are a reverse proxy's job:

```sh
taskops serve --root ~/boards [--host 127.0.0.1] [--port 8787]
```

Everything after that runs **from your laptop**, signed by the key `server init`
registered:

```sh
taskops remote add https://host:8787 [--replace]   # once per checkout
taskops board create [<name>]                      # defaults to the directory's name
taskops board push                                 # this repo's LOCAL board becomes that one
taskops board ls
taskops board visibility <name> public|private     # owner only
taskops invite <who> [--board <name>]
taskops revoke --key SHA256:… | --invite <id>
```

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

## The nine MCP tools

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
```

`plan`, `assign` and `merge` are the orchestrator's (`dev:<name>`); `take` is a
worker's (`agent:<dev>/<name>`). Reading and commenting are open to everyone —
only taking, closing and releasing belong to the holder.

Three states are stored — `open`, `done`, `dropped`. `ready`, `doing`, `blocked`,
`stalled`, `review`, `reviewing`, `changes` and `mention` are all derived per read,
which is why there is no `recover` verb and no mark-as-read.

## Developing

```sh
./scripts/lint                    # ruff + pyright strict
./scripts/test                    # the whole suite
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
