# taskops — research preliminar (2026-07-27)

MCP + SQLite + Studio (patrón megabrain-v3) para orquestar tareas de agentes Claude Code:
multi-dev, multi-agente, local y remoto, con git como fuente de verdad de la ejecución.

## 1. Estado del arte (lo que existe y qué le falta)

### Nativo de Claude Code
- **Agent Teams** (experimental, nativo): lead + teammates, shared task list con
  dependencias y auto-unblock, mailbox de mensajes directos. TODO es JSON en disco:
  `~/.claude/teams/<team>/`, `~/.claude/tasks/`, inboxes `~/.claude/<team>/inboxes/<agent>.json`.
  Sin DB, sin broker. **Gaps**: efímero (muere con el team), mono-máquina, mono-cuenta,
  cero UI, cero vínculo con git (commits/branches no quedan asociados a nada), cero
  historia/reportes.
- **Hooks**: PreToolUse (puede aprobar/denegar/modificar), PostToolUse, UserPromptSubmit,
  SessionStart (corre también en resume), Stop, SubagentStop, Notification. Config en
  `.claude/settings.json` (compartido por repo). Esto es EL mecanismo de enforcement:
  un PreToolUse puede bloquear un `git commit` si el agente no tiene task claimed.
- **Plugins**: empaquetan commands + agents + hooks + MCP servers en una unidad
  instalable (`/plugin install`). taskops debería SER un plugin: MCP server + hooks +
  skills (`/task`, `/standup`, `/claim`) en un solo install.

### Terceros (lo que hay que superar)
- **Gas Town + Beads** (Steve Yegge): lo más ambicioso. 20-30 instancias CC en roles
  (Mayor/Polecats/Refinery), work-orders "convoys", y **Beads**: issues como JSONL en
  git (`.beads/beads.jsonl`) + caché SQLite local + IDs por hash para evitar conflictos
  de merge. **Ideas a robar**: issues-in-git como capa de sync multi-dev (viaja con
  push/pull, cero servidor), identidades persistentes de agentes, merge queue (Refinery).
  **Gaps**: Go externo, no es MCP-first, no es plugin CC, UI mínima.
- **Vibe Kanban**: kanban que EJECUTA agentes (dispara runs paralelos, encadena por
  dependencia), MCP server incluido, tickets "planning" que descomponen y generan cards.
  Gap: pensado como app que controla agentes, no como sustrato que los agentes usan.
- **backlog (backloghq)**: plugin CC persistente cross-session, 24 tools MCP,
  event-sourced, dependencias, docs, handoffs. El competidor más directo en forma.
  Gaps: sin UI rica, sin git-binding, sin multi-dev remoto.
- **Shrimp Task Manager / Task Master / Agent Board / task-orchestrator (jpicklyk)**:
  MCP genéricos con DAG de dependencias, state machines, quality gates server-enforced
  (el server rechaza la llamada si el agente no produce lo que el schema pide — idea
  buena), actor attribution. Gaps: agnósticos de cliente (no explotan hooks/plugins CC),
  sin git, sin UI seria, sin multi-dev.
- **CodeAgentSwarm / Emerge Factory**: apps desktop con board que asigna tareas a
  terminales CC. Gap: GUI-céntricos, no TUI-first.

**El hueco que nadie cubre y taskops sí**: la INTERSECCIÓN de
(a) exclusivo CC (hooks+plugin+Agent Teams como músculo de ejecución),
(b) git-binding total (cada commit/branch pertenece a un task, enforced por hooks),
(c) multi-dev/multi-cuenta con agentes comentando entre sí,
(d) UI local tipo studio + modo remoto,
(e) puente futuro a megabrain (cada commit indexado/procesado).

## 2. Arquitectura propuesta (patrón megabrain-v3, calcado)

```
                        ┌─────────────────────────────────────────────┐
                        │                  taskops                     │
                        │                                              │
   Claude Code ──MCP──▶ │  transports/            usecases/            │
   (stdio, N agentes)   │   ├─ mcp/    ──┐        (TODA la lógica;     │
                        │   ├─ http/   ──┼──────▶  transports = capas  │
   Browser ──── UI ───▶ │   │  (studio)  │         finitas sin motor)  │
                        │   └─ cli/    ──┘             │               │
   git hooks ── CLI ──▶ │                              ▼               │
   CC hooks  ── CLI ──▶ │                     storage/ (ÚNICO dueño    │
                        │                     del SQL — invariante     │
                        │                     testeado como en mb-v3)  │
                        │                              │               │
                        │              <repo>/.taskops/db.sqlite       │
                        │              <repo>/.taskops/tasks.jsonl ◀── │── commiteado
                        └─────────────────────────────────────────────┘    (sync multi-dev
                                                                             estilo Beads)
```

- **SQLite = caché/query local** (rápido, transaccional, WAL para N agentes concurrentes).
- **JSONL append-only commiteado en git = fuente de verdad compartida** (viaja con
  push/pull; IDs hash → merges triviales). `taskops sync` reconcilia JSONL ↔ SQLite.
  Esto da multi-dev SIN servidor. El modo remoto (fase 2) es el mismo motor detrás de
  transports/http con token, deployado con shipway — y los dos modos coexisten porque
  el event log es el mismo.
- **Studio**: mismo esquema que megabrain (esbuild → un bundle commiteado dentro del
  paquete, `taskops studio` sirve UI + JSON API en un puerto, SSE para live updates).
  Board kanban por columnas, grafo DAG de dependencias, timeline de eventos por task,
  vista "fleet" de agentes vivos con heartbeat.

### Modelo de datos (núcleo)
- `tasks`: id (hash corto), title, spec (el brief que un agente lee y sabe TODO),
  column/status, priority, parent_id (epics), created_by (humano|agente), assignee.
- `deps`: (task, blocks, kind) — DAG; `ready` = sin deps abiertas → auto-unblock.
- `leases`: claim atómico con TTL + heartbeat. UPDATE condicional en SQLite = lock.
  Agente muerto → lease vence → task vuelve a ready. Esto es lo que permite 100
  agentes sin pisarse.
- `events`: event-sourcing append-only (created, claimed, comment, commit, branch,
  blocked, review, done…). Todo lo demás (board, reportes, standups) son proyecciones.
- `comments`: hilo por task; autor = dev o agente (identidad persistente
  `dev:berna`, `agent:berna/refactor-1`). ESTE es el canal 24/7 entre agentes de
  distintos devs — cada sesión CC, vía hook SessionStart/heartbeat, recibe menciones
  y comentarios nuevos de sus tasks.
- `artifacts`: commits, branches, PRs, reports vinculados al task.

### Git-binding (enforced, no opcional)
```
branch naming:  tk/<task-id>/<slug>          ← la rama ES del task
commit trailer: Task: tk-4f2a                ← cada commit queda asociado

quién lo impone:
  CC hook PreToolUse(Bash≈git commit) ─▶ taskops guard commit
      · ¿la sesión tiene task claimed?  no → DENY con mensaje accionable
      · inyecta el trailer si falta
  git hook post-commit ─▶ taskops ingest commit <sha>
      · registra el commit como evento del task (cubre commits hechos a mano)
  git hook post-checkout / CC SessionStart ─▶ asocia la sesión a task por branch
  CC hook Stop / SubagentStop ─▶ taskops report
      · resumen de la sesión como comentario del task (auto-standup)
```
La evaluación con LLM de cada commit (¿cumple el spec? ¿scope creep?) entra por
PostToolUse o por un worker `taskops eval` — y es el gancho natural a megabrain:
commit → index incremental → el evento del task referencia los chunks tocados.

### Superficie MCP (corta a propósito, como megabrain)
```
taskops_plan    crear/descomponer: epic → subtasks con deps (acepta árbol entero)
taskops_next    "¿qué hago?": claim atómico del mejor task ready para MI identidad
                (respeta deps, prioridad, files-touched para no chocar worktrees)
taskops_update  progreso/status/handoff/bloqueo + comment en una llamada
taskops_ask     leer: el task + spec + hilo + commits + qué lo bloquea / a quién
                bloquea + tasks vecinos tocando los mismos archivos
taskops_report  standup / burndown / "estado del proyecto" generado (md render)
```
5 tools. Todo lo demás (guard, ingest, sync, studio) va por CLI, que es lo que los
hooks invocan. Guardrails estilo task-orchestrator: schemas que el server rechaza si
el agente no entrega lo requerido (p.ej. done sin commits asociados → rechazado).

### Plugin Claude Code (el empaquetado)
Un plugin `taskops` que instala: el MCP server, los hooks (PreToolUse guard,
SessionStart context-inject con "tus tasks + menciones", Stop auto-report), skills
(`/tasks`, `/claim`, `/standup`, `/plan`) y AGENTS-facing doc: `.taskops/GUIDE.md`
generado — la guía que cualquier agente (o humano) lee y sabe operar el sistema.

## 3. Decisiones ya tomadas por este research
1. Python + patrón megabrain-v3 (usecases/storage/transports, SQL solo en storage,
   invariantes de arquitectura testeadas, studio esbuild commiteado).
2. Sync multi-dev por **event log JSONL en git** (Beads lo validó) + SQLite local;
   servidor remoto opcional después, mismo motor.
3. Concurrencia por **leases con TTL** sobre SQLite WAL, no por locks de archivos.
4. Enforcement por **hooks CC + git hooks**, no por convención.
5. MCP mínimo (5 tools); ejecución paralela delegada a Agent Teams/worktrees de CC —
   taskops coordina y registra, no reimplementa el spawn.

## 4. Fuentes
- https://code.claude.com/docs/en/agent-teams · https://code.claude.com/docs/en/hooks
- https://www.claudecodecamp.com/p/claude-code-agent-teams-how-they-work-under-the-hood
- https://steve-yegge.medium.com/welcome-to-gas-town-4f25ee16dd04 ·
  https://github.com/steveyegge/gastown · https://paddo.dev/blog/gastown-two-kinds-of-multi-agent/
- https://github.com/backloghq/backlog · https://github.com/cjo4m06/mcp-shrimp-task-manager
- https://github.com/jpicklyk/task-orchestrator · https://mcpmarket.com/server/agent-board
- https://virtuslab.com/blog/ai/vibe-kanban · https://www.blog.brightcoding.dev/2026/07/17/vibe-kanban-the-revolutionary-ai-agent-manager-every-dev-needs
- https://www.codeagentswarm.com/en/guides/claude-code-task-management ·
  https://github.com/tryemerge/code-factory · https://www.augmentcode.com/tools/open-source-agent-orchestrators
- https://www.mindstudio.ai/blog/claude-code-agent-teams-shared-task-list ·
  https://israynotarray.com/en/ai/2026/05/31/claude-code-hooks-complete-guide/
