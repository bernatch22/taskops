# taskops — architecture

Every rule here is executable. `tests/architecture/test_invariants.py` fails the build when
one is broken, because prose alone is enforced by whoever happens to review the diff.

The shape is copied from [megabrain-v3](https://github.com/bernatch22/megabrain), and where
it deviates the deviation is documented in the module that makes it.

---

## The layers

```
  L0  _types  _errors  _ids  _clock  _version
      the vocabulary. imports NOTHING from the package, so any layer may use it freely.
                              │
  L1  contracts/              every payload that crosses a boundary, as TypedDicts.
      ZERO logic. imports only L0, so it can never introduce a cycle.
                              │
  L2  storage/                the ONLY package that writes SQL. one SQLite file per repo.
                              │
  L3  engine/                 the decisions: machine, scheduler, projections, git, bus.
                              │
  L4  render/                 contract → string. no I/O, ever. pure functions.
                              │
  L5  usecases/               one module per verb. sync. returns contracts.
                              │
  L6  transports/             cli · mcp · hooks · http. thin: they may NOT import L2 or L3.
```

The load-bearing rule is the last one. A transport that reached into `storage` would be a
fourth place where a decision lives, and the CLI, MCP and HTTP answers would start
disagreeing about what `done` requires. That is the failure this whole shape exists to
prevent, and `test_transports_never_reach_past_the_use_cases` is the fence.

## One transport per audience

```
  cli/     a PERSON            `taskops <cmd>`                        8 commands, 8 listed
  mcp/     an AGENT            `python -m taskops.transports.mcp`     7 tools
  hooks/   git + Claude Code   `python -m taskops.transports.hooks`   nobody types it
  http/    a BROWSER           `taskops ui` · `taskops serve`         the live board
```

`serve` is not a fifth transport, and that is worth saying because it looks like one. It is the
SAME http transport with a different mount: `transports/http/projects.py` splits the first path
segment, finds the project it names under a server root, and hands the request to the router
that already exists with the prefix trimmed. A project is therefore literally today's board,
mounted — every endpoint, the SSE feed and the websocket work under `/<project>/` without one of
them learning that prefixes exist. `taskops ui` serves the repository you are standing in;
`serve` serves a directory of them, over a network, and each has its own token.

Three consequences of that shape, all of them load-bearing:

- **Isolation is structural.** A mounted router is bound to one root and only ever sees a path
  with the prefix already removed, so a request that arrived under `/axion/` has no way to name
  another store. The project name is validated against `[a-z0-9-]{1,40}` **before** a path is
  built, so traversal is refused as syntax rather than caught later by a resolve.
- **The event bus is process-global; the cursor is not.** A write in one project wakes every
  other project's `follow`, and what each then reads is its OWN sqlite cursor — so the wake-up
  yields nothing. That is the line that makes one process safe for many boards, and
  `tests/transports/test_serve.py` pins it. The exception, written down rather than hidden: a
  `WireMessage` (a narration delta) carries no project, so it DOES reach every open board.
  Closing that needs a field on the wire contract.
- **No ambient trust.** `taskops ui` may be open on loopback because a laptop is a laptop; this
  faces a network, so every project's token is required for everything including reads, a
  project without a `token` file is not served at all rather than served open, and a miss is a
  bare 404 that names nothing — a listing would hand an unauthenticated caller every board on
  the host, which is the enumeration the per-project token exists to prevent.

The separation used to be declared and not real. `taskops --help` listed seven commands and
hid thirteen, and both `.git/hooks/*` and the plugin's `hooks.json` invoked
`taskops.transports.cli.main` — so git and Claude Code entered through the developer's door
and the CLI's surface was being decided by three audiences at once.

`hooks/` exists because of a physical limit, not a preference: a Claude Code hook is a
`{"type": "command"}` entry and a git hook is a shell script, so both EXECUTE something, and
git has no MCP client. Something runnable has to exist. What changed is that it stopped being
the thing a person types. Its subcommands are named after the EVENT — `pre-tool-use`,
`post-tool-use`, `session-start`, `stop`, `commit`, `ingest`, `sync` — because the reader of
those names is somebody staring at a hook line, not at a menu of verbs.

The exit codes there are the contract, and they are why the CLI's `main` no longer forwards an
int: `commit` answers **2** to deny with its reason on stderr (that is what Claude Code shows
the model), the Claude Code events answer **0** always with the decision inside the JSON, and
everything fails OPEN. Every git hook line ends in `|| true`, so a command that does not exist
fails in complete silence — `tests/e2e/test_hook_wiring.py` commits in a real repository and
asserts the binding happened, which is the only thing that catches a bad rename.

## The invariants, and what each one is protecting

| Invariant | The failure it prevents |
|---|---|
| SQL only in `storage/` | A second place that knows the column order — always the one nobody updates. |
| `contracts/` import only L0 | The wire format depending on the database; no generated TS mirror. |
| Transports never import `storage`/`engine` | Three surfaces drifting on what a rule means. |
| The state machine has one home | A transition table plus one convenient `if status ==` is two state machines, and the convenient one forgets the guard. |
| Only `_clock` reads the clock | A lease-expiry test that has to sleep fifteen real minutes is a test nobody runs. |
| `render/` is pure text | A rendering bug you cannot reproduce without a database. |
| The engine is sync | An async twin of every function, and two of them to keep correct. |
| No `assert` in shipped code | `python -O` deletes them, and the value it swore was fine flows on. |
| ≤70 **code** lines per module | See below. |

### Why the budget counts code, not lines

megabrain-v3 caps raw lines at 100. That rule punishes the one thing both codebases are
built on — a written reason for every decision — and a file stays under it by deleting the
explanation, which is the opposite of the intent.

Here `MAX_CODE_LINES = 70` excludes docstrings, comments and blanks, with a raw ceiling of
160 to stop a file becoming a document with some code in it. The budget then says what it
means: no module may hold more than ~70 lines of logic, and it may carry as much reasoning
as that logic needs. It cannot be gamed the other way either — logic does not fit in a
docstring.

Three splits in this codebase exist because of that budget, and all three improved the
design: `storage/_ddl` (the schema is data, the migration is logic),
`transports/mcp/_descriptions` (the tool prose is data), and `usecases/_entry` (reading what
a model wrote is not building a graph).

## The two storage layers, and which one is the truth

```
  .taskops/events.jsonl     COMMITTED. append-only. content-hash ids.  ← THE TRUTH
  .taskops/db.sqlite        gitignored. WAL. rebuildable from the log. ← a cache
```

Multi-developer sync with no server falls out of this: appending to different ends of a file
is the one edit git merges without help, and a content-hash id makes importing the same
event twice a primary-key no-op. There are no conflicts to resolve, because events are facts
about the past — the union of two logs *is* the correct log.

**WAL, unlike megabrain.** That engine documents its rollback-journal choice as a property
of its workload: writes are rare there, so readers already never wait. Here a hundred agents
renew leases and append events continuously while the UI reads the board, so a reader
must never block behind a writer. Same reasoning, opposite conclusion.

## Concurrency: leases, not locks

A boolean `assigned_to` cannot express "an agent said it was working on this and then its
process was killed", so a board built on one accumulates tasks nobody is doing and nobody
can take.

```
  claim = BEGIN IMMEDIATE ─▶ sweep expired ─▶ INSERT INTO leases (task PRIMARY KEY)
                              │
              two agents racing for one task are two INSERTs on one key; SQLite decides.
```

`BEGIN IMMEDIATE` must be the transaction's first statement — sqlite3 opens one implicitly
on the first write, and `BEGIN IMMEDIATE` inside one raises. That is not a footnote: it was
a real bug, found by the end-to-end test, where a heartbeat wrote first. The lock has to be
taken before the sweep *reads*, or two agents both see the same dead lease as sweepable.

Every taskops call renews the caller's leases, so the TTL bounds a **crash**, not a slow
task. An already-expired lease is never revived — by then another agent may hold the task,
and quietly handing it back would produce two holders and no error.

## Git-binding

```
  branch:   tk/<task-id>/<slug>          what a human sees, checkable BEFORE a commit exists
  trailer:  Task: tk-4f2a9c              survives a squash, a rebase, a cherry-pick
```

Both, not either. A branch name is gone the moment the branch is deleted, which is the normal
end of a branch's life; a trailer cannot be checked before the commit is written.

```
  PreToolUse(Bash≈git commit) ─▶ …hooks pre-tool-use   can DENY (the JSON says so)
  a hook line asking directly ─▶ …hooks commit         can DENY (exit 2, stderr → the model)
  post-commit                 ─▶ …hooks ingest commit  records everything, including what
                                                       the guard never saw (--no-verify, a
                                                       human's terminal commit, a rebase)
```

The guard **fails open**. A coordination tool that blocks commits because its database was
locked has broken the thing it exists to support, and `post-commit` will usually record the
commit anyway.

Git hooks embed `sys.executable -m taskops.transports.hooks`, not a bare `taskops`. Hooks run
with git's environment, which routinely cannot see the virtualenv taskops is installed in — a
bare command resolves to nothing and the hook silently does nothing, because every line ends
in `|| true`. `taskops init` REWRITES the line it wrote last time rather than reporting
"already installed", so re-running it is what repairs a repository set up by an older version.

## Agent-to-agent messaging, honestly

Claude Code cannot be pushed to mid-turn. A session only listens when a hook fires, and this
is stated plainly rather than dressed up:

```
  SessionStart  ─▶ …hooks session-start   the agent starts knowing its tasks and messages
  PostToolUse   ─▶ …hooks post-tool-use   anything new lands in its NEXT tool call
  Stop          ─▶ …hooks stop            its work becomes a comment, unprompted
```

So "real time" between agents means *within one tool call of the sender writing it* — seconds
for a working agent. The human-facing real time is `taskops ui`, which sees an event as soon as
it is committed.

Delivery is tracked per `(actor, event)`, never by a timestamp cursor: hooks fire in an order
nobody controls and timestamps come from different machines, so a cursor would silently skip
a message that arrived late.

## What is deliberately NOT here

- **No agent spawning.** Claude Code's Agent Teams and git worktrees already do that well.
  taskops is the shared truth they lack, and re-implementing the fleet would mean owning a
  process supervisor.
- **No LLM anywhere in the engine.** Zero runtime dependencies, and no model call on the path
  of a commit. Evaluating a diff against its spec is a future opt-in worker, not a guard.
- **No FTS5.** It is a compile-time option missing from some distro pythons, and a task list
  is thousands of rows. A LIKE scan that always works beats an index absent on a teammate's
  machine.
- **No `ruff format`.** This codebase is hand-wrapped; a formatter that puts a collection
  either on one line or one-per-line spends the file budget on style. megabrain-v3 plainly
  does not run it either — 221 of its 300 files would be reformatted.
