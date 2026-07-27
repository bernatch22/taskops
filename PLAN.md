# taskops — PLAN de implementación (para ejecutar 2026-07-28)

**Qué es**: el sustrato de coordinación que a Claude Code le falta — tasks persistentes con
DAG de dependencias, claims atómicos por lease, git-binding enforced por hooks, hilo de
comentarios entre agentes/devs, event log commiteado en git para multi-dev sin servidor,
y un Studio web para verlo todo. MCP + SQLite + Studio, patrón megabrain-v3.

**Frameworks obligatorios** (leer ANTES de escribir una línea):
- Skill **`art-of-python`**: `~/.claude/skills/art-of-python/SKILL.md` (los 10 mandamientos),
  `STRUCTURE.md` §2 (pyproject anotado — copiarlo), `PATTERNS.md`, y `example/` (mini-SDK
  runnable, copiar sus shapes de tests).
- Referencia arquitectónica: **`~/megabrain-v3`** (indexado — usar `megabrain_ask` ante
  cualquier duda de "cómo lo hizo megabrain"). Archivos canon a imitar, citados por fase
  abajo. Leer también `~/megabrain-v3/ARCHITECTURE.md` y `tests/architecture/test_invariants.py`.
- `RESEARCH.md` de este repo: el landscape y las decisiones ya tomadas (no re-litigar).

**Reglas heredadas de megabrain-v3 que taskops adopta tal cual**:
- SQL vive SOLO en `storage/` (invariante testeada).
- `contracts/` = TypedDicts puros, capa 1, importa solo L0. Optionality por **split
  `total=False`**, nunca `NotRequired` (ver el warning en `megabrain-v3
  src/megabrain/contracts/bundle.py` L14-21).
- Schema MCP **generado** desde los TypedDicts (copiar `transports/mcp/schema.py`).
- Dispatch = TABLA, handlers de 3 líneas (copiar `transports/mcp/dispatch.py`).
- Usecases sync, un archivo por verbo, retornan contracts. Sin async en el motor.
- Transportes (cli/mcp/http) delgados, cero lógica, mismos usecases.
- Errores tipados → una línea accionable, jamás traceback al agente.
- Studio: esbuild → un bundle commiteado dentro del paquete Python
  (copiar `studio/build.mjs`), CI falla si el bundle drifteó.
- Archivos ≤100 líneas, funciones ≤30 (los tests de arquitectura lo imponen).

---

## 1. ENTIDADES (contracts/ — la capa 1 entera)

```
Project (implícito: 1 repo = 1 proyecto; .taskops/ en la raíz git)
│
├── Task ────────────────┐
│   id: str          hash corto tipo beads: "tk-4f2a9c" (random, merge-safe)
│   title: str
│   spec: str        el brief COMPLETO: un agente lo lee y sabe todo
│   status: Status   ver state machine §2
│   priority: int    0=urgente … 3=algún día
│   parent: str|None epic → subtasks (árbol); deps van aparte (DAG)
│   labels: [str]
│   files: [str]     hint de superficie de edición (anti-colisión de claims)
│   created_by: Actor
│   created/updated: float (epoch)
│
├── Dep              (task: str, blocks: str)  arista del DAG
│                    "task bloquea a blocks"; ready = sin deps entrantes abiertas
│
├── Lease            el claim atómico
│   task: str
│   actor: Actor     quién lo tiene
│   session: str     session-id de CC (correlaciona con transcripts)
│   branch: str|None tk/<id>/<slug>
│   expires: float   TTL renovado por heartbeat; vencido → task vuelve a ready
│
├── Actor            identidad persistente (el "50 First Dates" resuelto)
│   id: str          "dev:berna" | "agent:berna/polecat-1"
│   kind: "dev" | "agent"
│   dev: str         a qué humano responde el agente
│
├── Event            event-sourcing append-only; TODO lo demás es proyección
│   id: str          hash(contenido) — idempotente al re-ingestar
│   task: str
│   actor: Actor
│   kind: Literal[   "created","claimed","released","status","comment",
│                    "commit","branch","blocked","unblocked","handoff",
│                    "review","eval","done",
│                    "message",          # chat dirigido agente↔agente / dev↔agente (§4F)
│                    "activity" ]        # latido de sesión: tool corrido, archivo tocado
│                                        #   (alimenta el live feed del Studio, no el JSONL
│                                        #    de git — es efímero, tabla local only)
│   body: dict       payload por kind (sha+message para commit, texto para comment…)
│   ts: float
│
├── Comment          proyección de events kind=comment — el canal 24/7
│   mentions: [str]  "@dev:berna", "@agent:x/y" → aparece en el context-inject
│                    del SessionStart del mencionado
│
└── Artifact         proyección de events commit/branch/pr
    task, kind: "commit"|"branch"|"pr", ref: str (sha/branch/url)
```

Contracts extra (inputs de tools, como `megabrain-v3 contracts/tools.py`):
`PlanParams, NextParams, UpdateParams, AskParams, ReportParams` — TypedDicts anotados;
**las descripciones son parte del contrato** (es lo único que el agente lee).

## 2. STATE MACHINE (server-enforced — transición inválida = rechazo con mensaje)

```
                    ┌────────────────────────────────────────────────┐
                    │              deps abiertas                     │
   taskops_plan     ▼                                                │
  ──────────▶ ● backlog ──deps ok──▶ ready ──taskops_next──▶ claimed │
                    ▲                  ▲   (lease atómico)      │    │
                    │                  │                        ▼    │
                    │       lease vence│                   in_progress
                    │       o released │                    │  │  │
                    │                  └────────────────────┘  │  └──▶ blocked ──┐
                    │                                          │      (espera    │
                    │                                          ▼       humano/   │
                    │                                       review     dep nueva)│
                    │                                        │  │                │
              ┌─────┴─────┐                     eval falla / │  │ eval ok        │
              │ cancelled  │◀── humano ── rechazo ◀──────────┘  ▼                │
              └───────────┘                                   done ──unblocks──▶ (deps
                                                                     de otros tasks)
```

Guardrails duros (estilo task-orchestrator, el server RECHAZA):
- `claimed/in_progress` requiere lease vivo del actor que llama.
- `done` requiere ≥1 evento `commit` asociado **o** flag explícito `no_code: true`
  con justificación (tasks de research/docs).
- `review→done` puede exigir `eval` ok si el proyecto activa `eval_gate` en config.
- Un task con subtasks abiertas no puede pasar a `done`.

## 3. DELEGATIONS — quién hace qué (taskops NO re-implementa el spawn)

```
   HUMANO (dev)                         taskops                    Claude Code
   ──────────                           ───────                    ───────────
   escribe epic ──/plan──▶ taskops_plan: descompone → DAG
                           (el LLM que descompone es la SESIÓN CC
                            que llamó — taskops solo persiste el árbol)
                                        │
   lanza N sesiones /                   ▼
   Agent Teams / worktrees ──▶ cada agente: taskops_next
                               · lease atómico del mejor ready
                               · anti-colisión: penaliza tasks cuyo
                                 `files` intersecta leases vivos
                                        │
                               agente trabaja en SU worktree/branch
                               (worktrees los maneja CC, no taskops)
                                        │
                               hooks registran commits/branches (§4)
                                        │
                               taskops_update → review/done
                                        │
   dev revisa en Studio ◀── proyecciones (board, DAG, timeline, fleet)
   o pide /standup      ◀── taskops_report
```

Roles emergentes, no hardcodeados: un "lead" es simplemente la sesión que llama
`taskops_plan`; un "worker" la que llama `taskops_next`. Los roles tipo Gas Town
(Mayor/Refinery) se recrean con agents/skills del plugin, encima del sustrato.

## 4. FLOWS con mecanismos de trigger (git + CC hooks, exhaustivo)

### Flow A — commit de un agente (el git-binding enforced)
```
agente corre Bash("git commit -m …")
  │
  ├─▶ CC hook PreToolUse (matcher Bash≈git commit) → `taskops guard commit`
  │     · ¿sesión tiene lease?  NO → exit 2 (DENY) + "corré taskops_next primero"
  │     · ¿branch == tk/<id>/*?  NO en repos enforced → DENY con el comando fix
  │     · falta trailer `Task: tk-xxxx` → lo inyecta (updatedInput)
  │
  ├─▶ commit ejecuta
  │
  └─▶ git hook post-commit → `taskops ingest commit HEAD`
        · Event(kind=commit) + Artifact; idempotente por hash
        · cubre TAMBIÉN commits hechos a mano por el dev
        · si config.eval: encola eval LLM (¿el diff cumple el spec? ¿scope creep?)
          → Event(kind=eval) que el gate review→done puede exigir
```

### Flow B — sesión CC arranca (context inject + presencia)
```
CC hook SessionStart → `taskops brief --session <id>`
  · detecta actor (env TASKOPS_ACTOR o git config user.email → Actor)
  · detecta task por branch actual (tk/<id>/*) → re-asocia lease si es suyo
  · stdout → contexto de la sesión: MIS tasks claimed + menciones @ nuevas
    + comentarios recientes de mis tasks + qué tasks ready hay
  → el agente arranca sabiendo TODO sin preguntar
```

### Flow C — sesión termina (auto-standup)
```
CC hook Stop / SubagentStop → `taskops checkout --session <id>`
  · resume: qué tasks tocó, commits, status final
  · Event(kind=comment) con el resumen → el hilo del task ES el standup
  · libera leases de tasks no terminados (handoff limpio) o los renueva
```

### Flow D — sync multi-dev (el event log en git)
```
`taskops sync` (git hook post-merge/post-checkout + comando manual)
  · exporta events locales nuevos → .taskops/events.jsonl (append, IDs hash)
  · importa events del JSONL que el pull trajo → SQLite (idempotente)
  · JSONL commiteado = viaja con push/pull → multi-dev SIN servidor
  · conflicto imposible por diseño: append-only + IDs por hash (patrón Beads)
  · SQLite (.taskops/db.sqlite) va GITIGNOREADO — es caché derivable
```

### Flow F — chat agente↔agente en tiempo real (el mecanismo HONESTO)
No existe push mid-turn hacia una sesión CC: una sesión solo "escucha" cuando un hook
dispara. Entonces la entrega en tiempo real se construye con los puntos de inyección
que SÍ existen — y para el humano, el tiempo real de verdad está en el Studio (WS).

```
agente A (dev 1, feature X)                      agente B (dev 2, feature Y)
  taskops_update {comment|message,                     │
    mentions:["@agent:dev2/b"]}                        │
        │                                              │
        ▼                                              │
  Event(kind=message) → SQLite ──┐                     │
        │                        │ WS broadcast        │
        │                        ▼                     │
        │                  Studio: hilo visible        │
        │                  en vivo para los devs       │
        │                                              │
        └─▶ entrega a B, por CUALQUIERA de estos       │
            triggers (el primero que dispare):         ▼
            · PostToolUse/PreToolUse hook de B → `taskops inbox --session <id>`
              → si hay mensajes nuevos p/ B: stdout con additionalContext
              → B los VE en su próximo tool call (segundos, no minutos)
            · UserPromptSubmit / SessionStart → brief incluye inbox
            · B llama taskops_ask o taskops_next → el render antepone su inbox
```
- El inbox se marca entregado por (actor, session, last_event_id) — sin duplicados.
- Entre MÁQUINAS distintas los mensajes viajan por el relay (§9); local, por SQLite.
- Los devs chatean con los agentes desde el Studio (POST → Event message → misma ruta).

### Flow G — live feed de sesiones (transcripts JSONL + hooks → WS)
Dos fuentes complementarias, ambas ya validadas por el ecosistema (Observatory,
disler/claude-code-hooks-multi-agent-observability, claude-team-dashboard):

```
FUENTE 1 — hooks (estructurado, barato, es lo que ya instala el plugin):
  PostToolUse de cada sesión → `taskops track --session <id>`
    → Event(kind=activity){tool, file?, task} → tabla local (ring, no va a git)
    → Studio WS: "agent:berna/b está editando storage/leases.py (tk-4f2a)"

FUENTE 2 — transcript tail (el detalle fino, opt-in):
  ~/.claude/projects/<proyecto-encoded>/<session-id>.jsonl es APPEND-ONLY,
  una línea = un JSON válido (mensajes, tool calls, resultados).
  `taskops watch` (daemon opt-in) = watchfiles sobre ese dir
    → parsea líneas nuevas → resumen por evento → WS topic "session/<id>"
    → el Studio renderiza la transcripción viva de CUALQUIER agente
      (incluso agentes externos que NO tienen el plugin: con que corran
       Claude Code en esa máquina, el JSONL existe igual)
```
La sesión↔task se correlaciona por el session-id que `brief` guardó en el lease.

### Flow E — heartbeat / leases (100 agentes sin pisarse)
```
cada taskops_* call del agente renueva su lease (TTL default 15 min)
`taskops_next` de otro agente:
  BEGIN IMMEDIATE; UPDATE leases … WHERE expires < now OR …  ← SQLite WAL
  = lock atómico sin filesystem locks; agente muerto → lease vence
  → task vuelve a ready y otro lo agarra. Nada queda colgado.
```

## 5. SUPERFICIE MCP — 5 tools (contratos)

```
taskops_plan    { repo_path, tasks: [ {title, spec, priority?, labels?, files?,
                  parent?, after?: [idx|id] } ] }
                → crea el árbol+DAG en una llamada; `after` referencia por índice
                  dentro del batch o por id existente. Render: tabla ids creados.

taskops_next    { repo_path, actor?, labels?, session? }
                → claim atómico del mejor ready (prioridad, deps, anti-colisión
                  por `files`). Render: el task ENTERO (spec, hilo, comandos
                  sugeridos: `git switch -c tk-<id>/<slug>`). O "nada ready" + por qué.

taskops_update  { repo_path, task, status?, comment?, mentions?, handoff_to?,
                  blocked_on? }
                → una llamada = transición + comentario. Valida state machine.

taskops_ask     { repo_path, task? | query? }
                → con task: spec + hilo + commits + qué lo bloquea/a quién bloquea
                  + tasks vecinos por `files`. Con query: búsqueda sobre títulos/
                  specs/comentarios (FTS5). Render: markdown.

taskops_report  { repo_path, kind: "standup"|"board"|"burndown"|"actor",
                  actor?, since? }
                → proyecciones renderizadas en md (el mismo render que exporta
                  el Studio y los reportes auto-generados).
```
El chat va DENTRO de estas 5: mandar = `taskops_update {comment, mentions}` (kind=message
si hay mentions); recibir = el inbox se antepone al render de `taskops_next`/`taskops_ask`
y llega por hooks (§4F). No hay tool #6 — la superficie corta es deliberada.

Todo lo demás es CLI (lo que invocan los hooks): `taskops init | guard | ingest |
brief | checkout | sync | studio | doctor | inbox | track | watch`.

## 6. LAYOUT del repo (calcado de megabrain-v3 + STRUCTURE.md del skill)

```
taskops/
├── pyproject.toml            ← copiar el anotado de art-of-python STRUCTURE.md §2
├── scripts/{bootstrap,format,lint,test,gates}
├── src/taskops/
│   ├── _types.py _errors.py _version.py          # L0: cero imports del paquete
│   ├── contracts/            # L1: entities §1 + tool params. TypedDicts puros.
│   │   ├── task.py deps.py lease.py actor.py event.py report.py tools.py
│   ├── storage/              # ÚNICO dueño del SQL. Store + una clase por tabla.
│   │   ├── schema.py         # DDL + _LATE_COLUMNS (migración por ALTER idempotente)
│   │   ├── store.py          # Store(repo_root) → .taskops/db.sqlite, WAL
│   │   ├── tasks.py deps.py leases.py events.py  # tablas
│   │   └── sync.py           # JSONL ↔ SQLite (Flow D)
│   ├── engine/               # lógica pura: state machine, scheduler, proyecciones
│   │   ├── machine.py        # TRANSITIONS: dict[(from,to)] → guard; tabla, no ifs
│   │   ├── scheduler.py      # ready-set, scoring de next, anti-colisión files
│   │   ├── project.py        # events → board/standup/burndown (proyecciones)
│   │   └── gitio.py          # parse de trailers, branch names, sha ingest
│   ├── usecases/             # un archivo por verbo, sync, retornan contracts
│   │   ├── plan.py next.py update.py ask.py report.py
│   │   ├── guard.py ingest.py brief.py checkout.py sync.py init.py
│   ├── render/               # contract → markdown (compartido por 3 transportes)
│   └── transports/
│       ├── cli/              # main.py + commands/ (registro por módulo, sin ifs)
│       ├── mcp/              # tools.py schema.py arguments.py dispatch.py
│       │                     #   protocol.py server.py — copiar 1:1 de mb-v3
│       └── http/             # router tabla + Policy(token,readonly,rate) + SSE
│           └── ui/           # app.js bundle COMMITEADO (esbuild)
├── studio/                   # fuente TS de la UI; build.mjs → transports/http/ui/
├── plugin/                   # el plugin Claude Code (§7)
├── tests/
│   ├── architecture/         # invariantes: SQL solo en storage, L1 puro, sync,
│   │                         #   ≤100 líneas/archivo, ≤30/función, anti-vacuum
│   ├── contracts/            # shape.py (copiar de mb-v3) + test_optionality
│   ├── engine/ usecases/ transports/  # unit; MCP por golden de protocolo
│   └── e2e/                  # repo git temporal real: init→plan→next→commit
│                             #   con hooks reales→done→sync entre DOS clones
└── docs/ GUIDE.md            # LA guía agente-legible; `taskops init` la copia
                              #   al repo destino como .taskops/GUIDE.md
```

## 7. Plugin Claude Code (`plugin/`)

```
plugin/
├── .claude-plugin/plugin.json    # nombre taskops, mcp server, hooks, skills
├── hooks/hooks.json              # PreToolUse(Bash≈git commit)→guard,
│                                 # SessionStart→brief, Stop/SubagentStop→checkout
└── skills/
    ├── plan/SKILL.md             # /plan: epic → taskops_plan bien descompuesto
    ├── claim/SKILL.md            # /claim: taskops_next + crear branch + arrancar
    ├── standup/SKILL.md          # /standup: taskops_report standup
    └── handoff/SKILL.md          # /handoff: update con handoff_to + comment
```
Los git hooks (`post-commit`, `post-merge`, `post-checkout`) los instala
`taskops init` en el repo destino (respetando hooks existentes: chain, no pisar).

## 8. Studio — live-first (WebSocket, no polling)

Vistas: **Board** (columnas = status, cards con actor/branch/commits — se mueven solas),
**DAG** (grafo de deps, ready en verde, critical path), **Task** (spec + timeline de
events + hilo de chat EN VIVO — el dev escribe acá y el agente lo recibe vía §4F),
**Fleet** (leases vivos, heartbeat, qué archivo toca cada agente ahora mismo — swim
lanes por sesión), **Session** (la transcripción viva de un agente, tail del JSONL §4G).

Transporte live: **un endpoint WS** `/ws` con topics (`board`, `task/<id>`,
`session/<id>`, `fleet`). El bus interno es simple: cada write de un Event en storage
publica en un `EventBus` in-process (observer, stdlib puro — sin redis ni broker);
el WS handler suscribe topics y hace fan-out a los browsers. Los agentes EXTERNOS
entran igual: sus hooks/`taskops watch` escriben events → mismo bus → misma UI.
El WS es SOLO server→browser para datos; el único write del browser es el chat
(POST normal → Event → bus). Fallback SSE si el WS molesta detrás de la relay
(en bernardocastro.dev ya sabemos que SSE atraviesa bien los dos nginx).
`taskops studio --port 2140 [--token --readonly --rate-limit]` — Policy de megabrain.

Nota stack: el server http de mb-v3 es sync (`build_server`); WS necesita algo más.
Decisión: `transports/http` sirve UI + API igual que mb-v3, y el WS vive en un
módulo `transports/http/live.py` con `websockets` (lib) en un thread propio,
alimentado por el mismo EventBus. Si pyright/deps lo complican, SSE-only en F7
y WS en F8 — la UI habla con una abstracción `LiveFeed` que no sabe cuál es.

## 9. Relay — multi-dev en tiempo real entre máquinas (fase remota)

El JSONL en git (§4D) sincroniza el ESTADO al ritmo de push/pull. Para el chat y el
fleet en vivo entre devs, eso no alcanza → `taskops relay`, un hub WS mínimo:

```
  dev 1 (taskops local) ──WS──▶                    ◀──WS── dev 2 (taskops local)
                               taskops relay
     · cada taskops local        (una VM, token       · replica events kind=
       publica sus events         por dev, TLS          message/activity/status
       en vivo y recibe           en la gpu-relay)      al SQLite local del otro
       los ajenos                                       → mismos hooks §4F los
     · el event log git sigue                             entregan a SUS agentes
       siendo la verdad; el relay es SOLO el camino rápido (efímero, re-derivable)
```
- Idempotencia gratis: los events ya tienen ID por hash — recibir dos veces es no-op.
- Sin relay, TODO sigue funcionando (degrada a sync por git). El relay nunca es
  fuente de verdad. Investigado: A2A (Google) resuelve esto para agentes genéricos
  pero es JSON-RPC/HTTP pesado y ajeno a CC; nuestro relay son ~200 líneas sobre
  el mismo EventBus. Si A2A madura en el ecosistema CC, el relay puede hablar A2A
  como transporte alternativo sin tocar el motor.

## 10. FASES — estado real (actualizado 2026-07-27, 383 tests, todos los gates verdes)

- **F0 Esqueleto** ✅ — pyproject, `scripts/{lint,test,format,gates}`, capa 0
  (`_types _errors _ids _clock _version`), `tests/architecture` con 13 invariantes.
  **Desvío del plan**: el presupuesto de archivo mide **líneas de CÓDIGO** (≤70,
  docstrings excluidos) más un techo crudo de 160, en vez de las 100 crudas de
  megabrain — contar crudo castiga justo lo que esta arquitectura valora. Ver
  `ARCHITECTURE.md`. Y `scripts/format` NO corre `ruff format` (explota las
  colecciones hand-wrapped; megabrain tampoco lo corre: 221 de 300 archivos).
- **F1 Contracts + Storage** ✅ — 8 contratos, `Store` + 5 tablas, WAL, `sync` JSONL↔SQLite.
  Gate: round-trip de cada entity validado con `shape.py` contra su TypedDict.
- **F2 Engine** ✅ — `machine` (tabla + guards puros sobre `Facts`), `scheduler` (leases
  atómicos, anti-colisión por archivos), `project`/`activity` (proyecciones), `gitio`,
  `commitline`, `bus`, `identity`, `log`. Gate: **50 threads con conexiones reales
  compitiendo por un task → exactamente 1 ganador**.
- **F3 Usecases + CLI + MCP** ✅ — 11 usecases, 5 tools MCP con schema generado, CLI de
  11 comandos, `render/` en 7 módulos. Gate: handshake + los 5 tools por JSON-RPC.
- **F4 Git-binding** ✅ — guard (deniega/reescribe), ingest, brief/checkout, git hooks
  instalados por `init` (chained, no pisan). Gate: e2e con repo git REAL.
- **F5 Sync multi-dev** ✅ — export/import idempotente. Gate: **dos clones reales
  convergiendo por un remoto bare**, más idempotencia de re-import.
- **F6 Plugin + mensajería** ✅ — `plugin/` con `plugin.json`, `.mcp.json`,
  `hooks/hooks.json` (4 eventos) y 4 skills; `taskops hook <event>` habla el protocolo.
  **Mejor que el plan**: el `PreToolUse` devuelve `updatedInput` y **reescribe el
  comando** del agente para inyectar el trailer — el agente nunca lo escribe ni ve un
  error por él. Gate: mensaje de un agente entregado a otro en su siguiente tool call.
- **F7 Studio live** ⛔ **NO IMPLEMENTADO**. Es lo único grande que falta. El diseño está
  en §8 y las piezas que lo habilitan ya existen y están testeadas: `engine/bus.py`
  (EventBus in-process), `events.after_seq()` (el cursor que un proceso separado poletea,
  porque el bus no cruza procesos), y todas las proyecciones (`board`, `fleet`, `standup`)
  ya devuelven contratos listos para serializar. Falta: `transports/http/`
  (router+Policy+SSE/WS), `studio/` (TS+esbuild), y `taskops watch` (tail de los
  transcripts JSONL §4G).
- **F8 (futuro)** ⛔ — `taskops relay` (§9), eval LLM de commits, puente megabrain,
  A2A como transporte alternativo. `burndown` está declarado en el contrato y el tool
  responde "not implemented yet" a propósito, en vez de mentir con un gráfico vacío.

### Lo que los tests encontraron y el plan no anticipaba
Vale registrarlo porque son las decisiones que solo aparecen corriendo el sistema:
1. **`BEGIN IMMEDIATE` tiene que ser la primera sentencia** — sqlite abre transacción
   implícita en el primer write, y el heartbeat escribía antes. El claim entero es UNA
   transacción ahora.
2. **`claimed → done` faltaba**: la máquina exigía pasar por `in_progress`, o sea una
   llamada obligatoria extra en cada tarea del proyecto a cambio de nada.
3. **Los git hooks necesitan `sys.executable` absoluto**, no `taskops` en el PATH: git
   corre los hooks con SU entorno, que rutinariamente no ve el venv → el hook no hacía
   nada, en silencio, porque toda línea termina en `|| true`.
4. **`rev-parse --abbrev-ref HEAD` falla en un repo sin commits** (HEAD unborn) → el
   guard le decía a un agente que la rama de task en la que estaba no era una rama de
   task. Ahora `symbolic-ref`, que además reporta detached HEAD honestamente.
5. **`git log --grep commit` se leía como un commit** — el parser buscaba "commit" cerca
   del principio en vez del subcomando real.
