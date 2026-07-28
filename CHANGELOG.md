# Changelog

## Unreleased — a card remembers which sessions worked it

- **`taskops report range` y `taskops report all` — el reporte deja de ser de UN día.** Lo
  reportó Berna con una pregunta que el producto no sabía contestar: *"si quiero evaluar todo,
  no solo un dia, como hago?"*. Se contestaba leyendo treinta archivos diarios, que es como
  nadie lo contesta. Ahora `report all` narra el proyecto entero desde el primer evento del log
  hasta hoy, `report range --last 7d|2w|1m` la semana o el mes, y `--from/--to` un tramo
  explícito. `report day` sigue existiendo y su salida es **byte-idéntica** a la de antes (hay
  un golden que lo fija): es el caso de UN día del mismo reporte, no un segundo camino.
  - Un solo contrato: `DayReport` es hoy un alias de `PeriodReport`, que gana `from_date`,
    `to_date` y `label`. Dos shapes hubieran driftado la primera vez que alguien agregara un
    campo al que estaba leyendo.
  - Un solo ensamblado: `engine.day.period_report` corre sobre cualquier span y `day_report` es
    `period_report(store, date, date)`. La ventana sigue siendo de medianoche local a medianoche
    local vía `mktime`, así que el día del cambio de hora dura 23 o 25 horas también en un rango.
  - Los selectores se parsean **estricto**, como `parse_window`: `--last 3fortnights` se rechaza
    nombrando las formas legales en vez de ensancharse en silencio a algo plausible. Y mezclar
    `--last` con `--from`, o pasarle `--last` a `report day`, es un error — no una preferencia
    que se resuelve por el orden de los `if`.
  - `--write` nombra el archivo por el label: `.taskops/reports/2026-07-22..2026-07-28.md`,
    `all.md`. `all` se llama `all` y no por sus fechas a propósito: es UN documento que se
    mantiene al día, no un rastro de reportes casi iguales cuyo fin de rango cambió.
  - En un rango, `## Cerrado` agrupa las cards **por día, el más nuevo primero**, con su propio
    conteo — cien cards bajo un solo encabezado es un muro que nadie scrollea. Y el cap es
    honesto: si el rango cierra más de `MAX_CLOSED` cards, el reporte dice cuántas no muestra en
    vez de truncar callado, la misma regla que sigue la vista de actividad.
  - MCP: `taskops_report` gana `kind=range` con `last`/`from_date`/`to`. Sin ninguno de los tres
    cubre el proyecto entero, que es justo lo que un agente al que le piden "evaluá todo esto"
    necesita conseguir sin adivinar cuál de tres campos quería la tool.

- **`taskops report day --digest` — el reporte narrado, en un comando.** El dossier ya decía qué
  pasó; lo que faltaba era qué SIGNIFICA, y hasta ahora sólo existía como un skill que alguien
  tenía que acordarse de invocar dentro de una sesión. Ahora es un flag: escribe el reporte del
  día y llama al binario `claude` con el que ya estás logueado para que lo lea y escriba la
  sección `## Narración`. Sin SDK, sin dependencia nueva y **sin API key** — reusa
  `worker.DROPPED_ENV`, la misma constante que impide que un worker gaste la key, así que la
  narración la paga la suscripción y no el token. El modelo ve SÓLO el dossier: ni transcripts
  ni diffs, así que no puede filtrar una conversación a un archivo committeado ni inventar un
  hecho que el log no tenga. Si `claude` no está instalado o no hay login, falla nombrando cuál
  de las dos cosas es — y los hechos quedan en disco igual, porque el archivo se escribe ANTES
  de llamar al modelo.

- **A dispatched worker no longer inherits your Anthropic API key.** `taskops run` spawned
  `claude` with the full environment, and the CLI prefers an exported `ANTHROPIC_API_KEY` over
  the logged-in subscription — so every worker silently billed per token while the plan the
  developer already pays for sat unused, and nothing in the output said so. `engine.worker`
  now names the variables it removes (`DROPPED_ENV`: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_BASE_URL` — a proxy base url is the same class of surprise) and `_process.spawn`
  grew a `drop` argument, because merging dicts can override a variable but cannot UNSET one and
  an empty string is still a value the child sees. The capability is not lost: `taskops run
  --use-api-key` keeps them, with help text that says it bills per token. **CLI only** — no MCP
  tool can point a fleet at an API balance, the same rule that keeps `spawn` off the tool surface.
  The run warning now says the workers open a new session against the subscription's limits and
  names the flag for the other mode. Tests assert on the environment handed to `spawn` with a key
  exported, in both modes: this is the kind of bug that can only regress in silence.
- **`taskops tasks edit <id> [--title] [--spec] [--priority]` — a card can finally be
  corrected.** Until now a spec was whatever the planner typed and nothing could change it:
  an agent reading a brief that had since turned out to be wrong had no door back, and the
  workaround was cancelling the card and planning a new one, which threw away its thread and
  its commits. Each changed field records its own `edited` event (`{field, from, to}`), never
  one event carrying three — replay applies each on its own merits, so two people editing two
  different fields of one card converge on both instead of clobbering each other. Replay
  arbitrates with the same newer-wins rule `status` uses (`event ts` vs `task.updated`), so
  the fix reaches a teammate's clone through the log; an e2e test drives two real clones
  through a bare remote and asserts both agree. An edit that changes nothing records nothing,
  because a no-op event bumps `updated` and would let a redundant edit here beat a real edit
  elsewhere. A `done` or `cancelled` card REFUSES — "closed cards are history — open a new
  card referencing it" — since the log is the record of what was delivered and rewriting a
  finished spec rewrites that record. **No MCP change, on purpose**: the tool surface stays
  as it was, because correcting a brief is a human act and an agent that can rewrite its own
  spec can talk itself into having finished.
- **`taskops tasks` groups the task list, and `--help` lists six commands instead of nineteen.**
  The flat list mixed three audiences and gave no hint which was which: a person's task list, the
  agent protocol (`next`, `update`, `ask`, `plan`, `dispatch`, `log`), and the plumbing typed only
  by a git or Claude Code hook (`guard`, `ingest`, `brief`, `inbox`, `track`, `checkout`, `hook`).
  Somebody looking for "show me my tasks" had to read past `guard` and decide. What is listed now
  is `init`, `ui`, `tasks`, `report`, `recover`, `sync`; everything else is registered, parses and
  runs exactly as before, just unlisted — it is written into hooks and scripts that already exist,
  and the help page was what was failing, not the commands.
- **`taskops run [ids… | --count N]` — the spawn path under a name that says what it does.**
  It existed as `dispatch --spawn`, a flag on a hidden command, so the one thing in taskops that
  spends money was the hardest to find and the easiest to hit by accident. `run` is listed in
  `--help` as *experimental, billed*, prints `⚠ each worker is a NEW billed Claude session — for
  free parallelism dispatch sub-agents from a session (taskops_dispatch)` to stderr, and asks
  before starting anything; `--yes` is for unattended callers, `--dry-run` previews for free and
  never prompts, and no stdin (a hook, CI) counts as no. `dispatch` stays hidden and unchanged
  with its `--spawn` help now marked deprecated, and the flags are declared once so the two
  cannot drift. The MCP surface is untouched: a model still cannot make this package spawn.
- **`taskops tasks list | show | add | plan | done | release | log | search`**, each a wrapper over
  the verb it replaces rather than a reimplementation — `tasks done` IS `update --status done`, so
  the commit guard cannot be skipped through the new door. `tasks add` creates one card from flags
  and goes through `plan`, keeping a single `created` event shape in the log. Bare `taskops tasks`
  lists, because the list is what you want nine times out of ten.

- **`taskops studio` is now `taskops ui`**, and the TS source directory moved from `studio/` to
  `ui/` to match the bundle path it has always written (`transports/http/ui/`). "Studio" named one
  screen; the surface is a board, an activity timeline and reports, and a command called `ui` is
  the one somebody guesses without reading anything. The old name is kept as a hidden alias with
  every flag identical — it prints `taskops studio is now taskops ui` to stderr and then serves —
  because a rename that breaks a line in somebody's shell history buys nothing.
- **`taskops report day --write` — the day, filed and committed.** The dossier lands in
  `.taskops/reports/YYYY-MM-DD.md` with a fingerprint on line 1
  (`<!-- taskops:report date=… max_seq=… generated=… -->`) and an empty `## Narración`
  section for a human — or `/taskops:digest` — to fill in. It REFUSES to overwrite an
  existing report unless `--force`, because by then the file may carry a narration nobody can
  regenerate and a report somebody cited must not change under them. `max_seq` and not a
  timestamp: staleness ("did anything land after this was written") becomes an integer
  comparison with no clock skew in it, and `GET /api/report?date=…` answers it as `stale` plus
  `missing_events` — counted inside the day's own window and ignoring heartbeats, or a live
  agent would make today's report stale within a minute. `reports/` is COMMITTED, and the
  `.gitignore` block now carries a comment saying so, so the next tidy-up does not untrack it
  (`init` appends that comment to projects written before this existed).
- **New skill `/taskops:digest`** — generate the day's file if it is missing, read it, and
  write the narration from it: what needed a human first, then what moved, the decisions and
  the risks the log actually shows. Never a fact the dossier does not carry; a gap named is
  information, a gap filled in is a lie with a timestamp on it.
- **`taskops report day` — the deterministic daily dossier.** One CALENDAR day, cut at local
  midnight rather than 24 hours back, so the same date asked for tomorrow is the same report.
  Per card closed that day: who closed it, how long it was held (last claim -> done, because a
  card released and picked up again was not being worked on in between), every commit with its
  subject, files and **diff size**, and the last thing said on it — then what is still in
  flight, the whole conversation, and a roll-up per actor. The sizes come from ONE batched
  `git log --numstat --no-walk` for every commit in the report, and degrade to zeros rather
  than raising, like the rest of `gitio`. Heartbeat events never reach it: a busy day has
  thousands, and counting them would rank the agent with the plugin above the one that closed
  four cards.
- **`taskops_report` dropped `burndown` and `fleet` from what a model may ask for.** One was
  never implemented and answered with a sentence saying so; the other answers "who is free",
  which stopped being a question the day workers became disposable — the studio dropped that
  panel for the same reason. An unknown kind is now REFUSED rather than falling through to the
  board, which would hand an agent a report about something else with no way to tell. `fleet`
  survives as a use case, on the CLI and in the HTTP api, where a human does want to see which
  claim has gone quiet.

- **The conversation viewer found nothing for interactively-worked cards.** A card's transcript was
  located by path plus a `gitBranch` filter, which identifies a dispatched agent (it makes a branch)
  and loses the most ordinary case there is: a person who claims a card in their own terminal and
  never leaves `main`. Every one of their entries failed the filter. The `PostToolUse` hook now
  stamps its session id onto the leases the actor holds, and a transcript named by a recorded session
  id is read whole, whatever branch it was on. Nothing passed a session before — the tool accepted
  one and no caller supplied it, so every `claimed` event in a real project carried an empty string.
- **An empty pane now says which kind of nothing it is.** "No conversation found" plus a path reads
  as a broken viewer, and was reported as one. Three cases are now distinguished: no transcript
  directory at all (check `$CLAUDE_CONFIG_DIR`), a directory with no session recorded against this
  card (normal, nothing to show), and a recorded session whose entries are missing.

Cards worked before this shipped stay unrecoverable, and that is a real limit rather than a bug: with
no session id and entries on `main`, there is no evidence tying them to a card.

- **The conversation panel is gone from the studio.** Even correctly attributed, a raw transcript is
  the wrong thing for a board to show: it is hundreds of kilobytes fetched per card click to render a
  replay nobody reads, and what a person actually wants from a finished card — what was decided, what
  was touched, how it ended — is the thread and the commits, which were already there. The `/api/log`
  route, the studio's `Conversation` view and its wire types are removed; `taskops log <task>` keeps
  working in the terminal, which is where reading a whole session belongs.
- **A new activity view: the log as a history.** `events.jsonl` has held every fact about what
  happened here since the first release, and nothing outside a terminal could read it. The studio
  now has a second view — a timeline newest-first, filterable by actor, kind and text over a window
  you pick, with the task titles sent alongside so a hundred rows are not a hundred requests — and
  next to it a roll-up per actor: tasks touched, commits, closes, when they were last seen. Ranked
  by tasks rather than events, because forty comments on one card is less work than four cards
  closed. Nothing is stored for it; it is a projection like the board, over `/api/activity`.
  - Two bugs it surfaced before anybody saw the screen: `events.since()` with a `LIMIT` returns the
    OLDEST rows in the window, so a capped history would have shown entirely the wrong end of
    itself (`newest_since` orders descending to take the tail); and a close is its own event kind
    rather than a `status` with a payload, so counting `status` events reported zero closes on a
    project where thirty had landed.
- **The fleet rail is gone, and the board is full width.** "Who is free" is not a question when
  agents are created on demand — there is no pool to manage — and "who holds this card" was already
  on the card, next to the work it is about. What is worth keeping from it is history rather than
  availability, and that belongs in the activity view, not in a sidebar that repeats the board.
- **Empty columns can be folded away, by choice.** A toggle beside the search hides the columns with
  no cards. Off by default and remembered per browser: an empty column is information the first time
  somebody sees it, and clutter once they know the board.
- **`done` is grouped instead of listed.** Nothing ever leaves that column, so on a board a few weeks
  old it is longer than every other column combined and pushes the ones needing attention off the
  screen. Groups are by date (Today / This week / This month / Older), with a toggle to group by
  feature — the parent task or the first label, both of which the cards already declare, rather than
  a similarity guessed from titles. The newest group is open, the rest are folded, and each says how
  many it holds. The date buckets cut on calendar midnight rather than a rolling 24 hours: "today"
  meaning "within a day" files last night's work under today, which is the exact distinction the
  grouping exists to make.

## 0.1.0 — the engine, the enforcement, and the plugin

First release. The coordination substrate works end to end: an agent can claim work nobody else
will start, commit against it under enforcement, close it only with something to show, and hand
a message to another developer's agent.

**The claim is a lease.** Two agents racing for one task are two `INSERT`s on one primary key,
settled by SQLite — no lock files and no retry loop. Verified with 50 real threads on separate
connections: exactly one winner. Every taskops call renews the holder's lease, so the TTL bounds
a crashed process rather than a slow task, and a dead agent's work returns to the queue instead
of sitting there looking claimed.

**Commits are bound to tasks, and it is enforced.** A `PreToolUse` hook denies a commit with no
claim and returns `updatedInput` to *rewrite* the agent's own `git commit -m …` with the
`Task:` trailer — the agent never writes it and never sees a failure about it. A `post-commit`
hook records everything the guard never saw: a human's terminal commit, a `--no-verify`, a
rebase landing on a task branch. `done` is refused without a commit bound to the task, unless
`no_code` is passed with a written justification, which is recorded.

**Multi-developer with no server.** `.taskops/events.jsonl` is committed and append-only with
content-hash ids, so two clones converge through `git pull` and importing the same event twice
is a no-op. Verified with two real clones and a bare remote. The SQLite file is a cache and is
gitignored.

**Agents talk to each other.** `taskops_update` with `mentions` reaches another actor's inbox,
delivered by a `PostToolUse` hook on their very next tool call. Delivery is tracked per
`(actor, event)` rather than by a timestamp cursor, because hooks fire in an order nobody
controls and a cursor would silently skip a message that arrived late.

**Five MCP tools, and no sixth.** `next`, `update`, `ask`, `plan`, `report`. The `inputSchema`
of each is generated from its TypedDict, so a parameter cannot exist on the wire without
existing in the dispatch. Messaging is `update` with `mentions` on purpose — a message about a
task belongs in that task's thread, where it is still findable in three weeks.

**A plugin.** `plugin/` ships the MCP server, four hooks and four skills (`claim`, `plan`,
`standup`, `handoff`), plus the agent-facing `GUIDE.md` that `taskops init` writes into the
repository — one document for agents and humans, because two drift.

### Architecture

Zero runtime dependencies. Seven layers with 13 executable invariants (`tests/architecture`),
copied from megabrain-v3 with three deliberate differences, each documented where it is made:

- **WAL, not a rollback journal.** megabrain's choice is a property of its workload — rare
  writes, so readers never wait. Here a hundred agents write continuously while the board
  reads, so the trade flips.
- **The file budget counts CODE lines** (≤70, docstrings excluded) with a raw ceiling of 160,
  rather than 100 raw. Counting raw punishes the one thing this codebase is built on and
  rewards deleting the explanation to fit.
- **`ruff format` is not run.** It puts a collection either on one line or one per line, which
  spends the file budget on style. megabrain does not run it either: 221 of its 300 files would
  be reformatted.

### Found by the tests, not by review

Recorded because they are the decisions only a running system produces:

- `BEGIN IMMEDIATE` must be a transaction's first statement — sqlite3 opens one implicitly on
  the first write, and the heartbeat wrote first. The whole claim is one transaction now.
- `claimed → done` was missing, so `in_progress` was mandatory: one extra call in the lifecycle
  of every task in exchange for nothing the commit does not already prove.
- Git hooks must embed `sys.executable`. Hooks run with git's environment, which routinely
  cannot see the virtualenv — a bare `taskops` resolved to nothing and the hook did nothing,
  silently, because every line ends in `|| true`.
- `rev-parse --abbrev-ref HEAD` fails on an unborn HEAD, so in a repository with no commits the
  guard told an agent that the task branch it was standing on was not a task branch.
  `symbolic-ref` instead, which also reports a detached HEAD honestly.
- `git log --grep commit` was read as a commit: the parser looked for the word near the front
  instead of resolving the actual subcommand.

### Not in this release

The Studio — the live web board — is designed (`PLAN.md` §8) and unbuilt. `taskops_report
burndown` answers "not implemented yet" rather than returning an empty chart.
