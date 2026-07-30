# El lab: dos developers, un board, sin nadie tipeando

Cómo se corre el experimento de dos sesiones contra un board compartido, qué mira, y qué se
arregló cada vez que lo rompió. Escrito porque cada corrida encontró cosas que ningún test
encontró — el sistema tiene que sobrevivir a dos modelos usándolo, no a un test usándolo.

## Qué es

```
  /tmp/lab-origin          bare, el git que comparten
  /tmp/lab-mgr             el clon del manager: contexto + cards, nunca implementa
  /tmp/lab-dev1            un developer y sus agentes
  /tmp/lab-dev2            el otro
  taskops.bernardocastro.dev/lab    el board: la fuente única
```

Cada developer corre `/tmp/lab-run.sh <dev> <rondas> <segundos>`, que abre **una sesión nueva
de Claude Code por ronda** y le dice una sola palabra: `dale`. Eso es a propósito — es la forma
real en que alguien usa esto, y lo que tiene que hacer suficiente esa palabra es el
`SessionStart` hook, no el prompt.

```bash
nohup /tmp/lab-run.sh dev1 5 60 &
sleep 20                       # escalonados, para que colisionen
nohup /tmp/lab-run.sh dev2 5 60 &
```

**`env -u ANTHROPIC_API_KEY`** dentro del script, y no es cosmético: con la variable puesta,
Claude Code la prefiere sobre el login de claude.ai y la corrida muere con *"Credit balance is
too low"* sin tocar la suscripción que ya está paga.

## Qué mirar

```bash
cd /tmp/lab-mgr
taskops attention          # qué espera una decisión, agrupado por el movimiento que necesita
taskops report board       # las columnas
tail -f /tmp/lab-logs/dev1.log
```

Y en la caja, lo que ninguna pantalla muestra:

```bash
ssh gpu 'lxc exec bernardocastro -- sudo -u berna bash -lc \
  "wc -l ~/taskops-server/lab/.taskops/events.jsonl"'
```

## Lo que la corrida tiene que demostrar

| qué | cómo se ve cuando funciona |
|---|---|
| el rol se entrega solo | la sesión despacha workers en vez de laburar ella |
| la colisión se refuta | el segundo dev recibe `assigned to agent:…, which is not running` |
| el verifier se pide solo | `SubagentStop` nombra la card en el momento del handover |
| el turno no muere sucio | `Stop` bloquea dos veces sobre reviews propias y después suelta |
| una review, un verifier | la card claimeada desaparece del `attention` de los demás |
| nadie firma lo suyo | `reviewer: peer` refuta a `dev:X` sobre lo que hizo `agent:X/wN` |
| el commit es del agente | el trailer `Task:` y el bind salen a nombre del lease-holder |

## La regla que gobierna todo el ejercicio

**Que ningún developer se quede sin cards.** Si dev1 arranca y vacía la cola, dev2 no prueba
nada y la corrida no dice nada sobre dos personas. Por eso el board arranca con **ocho cards
independientes** en archivos disjuntos y sólo dos con dependencias, y por eso hay un monitor
que avisa `STARVING` cuando la cola baja de dos. Al que le falte, se le agregan cards en
módulos que nadie está tocando.

## Lo que cada corrida encontró

Ninguna de estas apareció en la suite. Todas aparecieron mirando la máquina.

- **El log del servidor estaba en cero.** Cuatro boards, bases llenas, `events.jsonl` vacío —
  al revés de lo que dice la arquitectura. Un `rm db.sqlite`, que es la reparación documentada
  de un cache, borraba un board para siempre. Ahora hay `journal` después de cada escritura y
  `reconcile` cuando un board se sirve por primera vez.
- **Los especialistas no existían.** `Agent type 'taskops-worker' not found`: vivían en un
  plugin que nadie instala, así que cada spawn caía a `general-purpose` — y un verifier sin las
  restricciones de sonnet/solo-lectura se armaba venvs y barría 6404 casos para chequear tres
  funciones de calendario. Ahora `init` los escribe en `.claude/agents/`.
- **Una review la verificaban tres agentes a la vez**, porque una card en review no tenía
  lease y aparecía en el sweep de todas las sesiones.
- **La autorevisión volvió por otra puerta**: `dev:dev2` cerró lo que `agent:dev2/w1` había
  entregado, y son dos strings distintos para una persona con dos manos.
- **El commit dentro del worktree era del humano**, porque el Bash de un sub-agente no lleva
  `$TASKOPS_ACTOR` — así que las reglas de agente no se le aplicaban a un agente.
- **`reviewer: peer — <la razón>` se anulaba a sí mismo**, porque el parser leía toda la línea
  como nombre. Este proyecto le pide a cada decisión que diga su porqué; la primera vez que
  alguien lo hizo bien, la política se apagó en silencio.
