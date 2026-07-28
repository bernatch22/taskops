<!-- taskops:report date=all max_seq=66 generated=2026-07-28T13:09:49 -->

# all — 9 closed · 1 in flight · 0 blocked · 11 commit(s) · 8 actor(s)

## Cerrado (9)

✓ **tk-dc436a** — Rename studio -> taskops ui (command, dir, docs)
  agent:berna/v21 · held 8m · 2 commit(s) · +146 -75
  `276bbbef6145` rename: taskops studio is now taskops ui, and studio/ is ui/ (+143 -72)
    .gitignore, ARCHITECTURE.md, CHANGELOG.md, README.md +45 more
  `2442773e2690` ui: the read-only and token refusals name the command that prints the URL (+3 -3)
    src/taskops/transports/http/policy.py
  1 comment(s) · last: Renamed taskops studio -> taskops ui. (1) git mv studio/ -> ui/ and commands/studio.py -> ui.py; the subparser register…

✓ **tk-a21435** — report day: the deterministic daily dossier (engine + render + CLI +…
  agent:berna/v22 · held 10m · 1 commit(s) · +793 -48
  `931a00ac73ab` report day: one calendar day in full, with each commit's diff size (+793 -48)
    CHANGELOG.md, README.md, USAGE.md, docs/flujos.html +23 more
  1 comment(s) · last: report day shipped: contracts/day.py (DayReport/ClosedCard/CommitStat), engine/day.py (local-midnight window via mktime…

✓ **tk-66b0c9** — Regroup the CLI: taskops tasks domain, hook group hidden, agent group
  agent:berna/v21 · held 6m · 1 commit(s)
  `69a69e9` cli: a tasks domain for people, and the plumbing steps out of --help (+0 -0)
    CHANGELOG.md, USAGE.md, src/taskops/render/__init__.py, src/taskops/render/_text.py +6 more
  1 comment(s) · last: Regrouped the CLI: new `taskops tasks` domain (list/show/add/plan/done/release/log/search), each subcommand a wrapper o…

✓ **tk-9bcbb0** — report day --write + digest: reporte del dia persistido en .taskops/r…
  agent:berna/v21 · held 7m · 2 commit(s) · +5 -1
  `288ee1a` report day --write: the dossier filed under .taskops/reports/, fingerprinted, plus /taskops:digest (+0 -0)
    CHANGELOG.md, USAGE.md, plugin/skills/digest/SKILL.md, src/taskops/__init__.py +16 more
  `9d69017788a4` report: the day helper takes the Path the caller already had (+5 -1)
    .taskops/events.jsonl, src/taskops/transports/cli/commands/report.py
  1 comment(s) · last: report day --write persists .taskops/reports/YYYY-MM-DD.md with a max_seq fingerprint and an empty ## Narracion section…

✓ **tk-74c6fb** — taskops run: dispatch --spawn renombrado como experimento, con la adv…
  agent:berna/v22 · held 4m · 1 commit(s)
  `38b46b6` taskops run: the spawn path under a name that says what it costs (+0 -0)
    CHANGELOG.md, src/taskops/transports/cli/commands/dispatch.py, src/taskops/transports/cli/commands/run_.py, src/taskops/transports/cli/main.py +3 more
  1 comment(s) · last: taskops run added as a visible command (= usecases.dispatch spawn=True) with the billing warning, confirmation, --yes f…

✓ **tk-1726d3** — tasks edit: editar spec/title/priority de una card (evento edited + r…
  agent:berna/v21 · held 6m · 1 commit(s)
  `7dabd1a` tasks edit: a card's title, spec and priority can be corrected (+0 -0)
    CHANGELOG.md, USAGE.md, src/taskops/_types.py, src/taskops/contracts/__init__.py +11 more
  1 comment(s) · last: tasks edit shipped. New `edited` event kind (one event per changed field), TaskTable.set_field guarded by an EDITABLE_F…

✓ **tk-588e0a** — taskops tasks lists a finished project instead of saying nothing
  agent:berna/fix2 · held 4m · 1 commit(s) · +306 -30
  `8a9709eaf1c9` tasks: a finished project lists its closed cards instead of nothing (+306 -30)
    src/taskops/render/_tasklist.py, src/taskops/render/tasklist.py, src/taskops/transports/cli/commands/_tasks_args.py, src/taskops/transports/cli/commands/tasks.py +2 more
  1 comment(s) · last: tasks now falls back to the closed cards when nothing is open (heading, newest-updated first, capped at 10 with +N more…

✓ **tk-85e55b** — A worker must never spend the API key — strip ANTHROPIC_* from the sp…
  agent:berna/fix1 · held 5m · 1 commit(s) · +151 -20
  `35291bbaf31e` A worker must never spend the API key (+151 -20)
    CHANGELOG.md, USAGE.md, src/taskops/assets/GUIDE.md, src/taskops/engine/_process.py +5 more
  1 comment(s) · last: Workers no longer inherit the Anthropic credentials. engine/worker.DROPPED_ENV (ANTHROPIC_API_KEY/AUTH_TOKEN/BASE_URL)…

✓ **tk-60cac8** — The Reports view in the UI — reading reports is not a terminal job
  agent:berna/rep2 · held 8m · 1 commit(s) · +795 -26
  `02acca70a8cd` ui: reports are read on a screen, rendered, not dumped as ASCII (+795 -26)
    CHANGELOG.md, USAGE.md, pyproject.toml, src/taskops/contracts/__init__.py +17 more
  1 comment(s) · last: Reports view shipped: third tab beside Board/Activity. Left rail lists .taskops/reports/ newest first (stale +N badge,…

## En vuelo / bloqueado

- ◐ tk-6f3536 — Reports over a RANGE, not one day — report range --last 7d | --from -…

## Conversaciones (9)

**agent:berna/v21** on tk-dc436a: Renamed taskops studio -> taskops ui. (1) git mv studio/ -> ui/ and commands/studio.py -> ui.py; the subparser registers as `ui` with help "serve the live web…

**agent:berna/v22** on tk-a21435: report day shipped: contracts/day.py (DayReport/ClosedCard/CommitStat), engine/day.py (local-midnight window via mktime, so a DST day is 23 or 25h and never st…

**agent:berna/v21** on tk-66b0c9: Regrouped the CLI: new `taskops tasks` domain (list/show/add/plan/done/release/log/search), each subcommand a wrapper over an existing run — tasks show/search…

**agent:berna/v21** on tk-9bcbb0: report day --write persists .taskops/reports/YYYY-MM-DD.md with a max_seq fingerprint and an empty ## Narracion section; refuses overwrite unless --force (new…

**agent:berna/v22** on tk-74c6fb: taskops run added as a visible command (= usecases.dispatch spawn=True) with the billing warning, confirmation, --yes for unattended callers, free --dry-run, E…

**agent:berna/v21** on tk-1726d3: tasks edit shipped. New `edited` event kind (one event per changed field), TaskTable.set_field guarded by an EDITABLE_FIELDS whitelist (SQL stays in storage/),…

**agent:berna/fix2** on tk-588e0a: tasks now falls back to the closed cards when nothing is open (heading, newest-updated first, capped at 10 with +N more), plus --all and --status <s> (refused…

**agent:berna/fix1** on tk-85e55b: Workers no longer inherit the Anthropic credentials. engine/worker.DROPPED_ENV (ANTHROPIC_API_KEY/AUTH_TOKEN/BASE_URL) + a drop param on _process.spawn that PO…

**agent:berna/rep2** on tk-60cac8: Reports view shipped: third tab beside Board/Activity. Left rail lists .taskops/reports/ newest first (stale +N badge, ✎ for narrated); right pane renders the…

## Por actor

| actor | tasks | commits | comments | closed |
|---|---|---|---|---|
| dev:berna | 11 | 0 | 0 | 0 |
| dev:me | 6 | 7 | 0 | 0 |
| agent:berna/v21 | 4 | 3 | 4 | 4 |
| agent:berna/v22 | 2 | 1 | 2 | 2 |
| agent:berna/fix1 | 1 | 0 | 1 | 1 |
| agent:berna/fix2 | 1 | 0 | 1 | 1 |
| agent:berna/rep1 | 1 | 0 | 0 | 0 |
| agent:berna/rep2 | 1 | 0 | 1 | 1 |

## Narración

Nada pide atención humana: no hay tarjetas bloqueadas, y la única en vuelo (tk-6f3536, reports sobre un rango en vez de un solo día) es la continuación natural de lo que se cerró hoy.

El día fue una reorganización de la superficie de comandos más el nacimiento del reporte diario, de punta a punta: motor, CLI, persistencia y pantalla.

**El reporte diario, completo en un día.** `report day` armó el dossier determinista (`contracts/day.py`, `engine/day.py`, ventana de medianoche local vía `mktime`, tamaño de diff por commit) — 793 líneas nuevas. Encima se le agregó `--write`, que archiva `.taskops/reports/YYYY-MM-DD.md` con un fingerprint `max_seq` y una sección `## Narracion` vacía, se niega a pisar sin `--force`, y trae el skill `/taskops:digest`. Y se cerró con la vista Reports en la UI: tercera pestaña junto a Board y Activity, listado por fecha con badge de stale y ✎ para los narrados, renderizado en pantalla en vez de ASCII volcado a la terminal.

**Los nombres del CLI.** `taskops studio` pasó a ser `taskops ui` (y `studio/` a `ui/`); las negativas de read-only y de token ahora nombran el comando que imprime la URL, que antes mandaba a un comando inexistente. Se creó el dominio `taskops tasks` (list/show/add/plan/done/release/log/search) como cara para personas, con el grupo de hooks fuera del `--help`. Se sumó `tasks edit` para corregir título, spec y prioridad: un evento `edited` por campo cambiado, con `set_field` limitado por una whitelist `EDITABLE_FIELDS` y el SQL quedándose en `storage/`. Y el camino de spawn salió a la luz como `taskops run`, con la advertencia de facturación, confirmación, `--yes` para llamadores desatendidos y `--dry-run` gratis.

**Dos bugs que reportó el usuario.** Un worker ya no hereda las credenciales de Anthropic: `DROPPED_ENV` saca `ANTHROPIC_API_KEY`/`AUTH_TOKEN`/`BASE_URL` del entorno del proceso hijo. Y un proyecto terminado ya no responde con silencio: `tasks` cae a las tarjetas cerradas cuando no hay ninguna abierta (más recientes primero, tope de 10 con "+N more"), con `--all` y `--status`.
