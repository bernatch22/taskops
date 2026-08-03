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

**`TASKOPS_ACTOR=dev:<dev>`** también, y por una razón que costó encontrar: a mitad de la
primera noche el clon de dev1 apareció trabajando como `dev:me`. Un agente le había cambiado
`git config user.email` al repo — porque el `CLAUDE.md` global del usuario dice cuál debe ser la
identidad de git, y el agente lo leyó y "corrigió" el checkout. taskops resuelve el actor desde
git cuando nadie lo fija, así que la identidad de un developer entero derivó sin que nada
fallara. No rompió nada esa vez porque `me` y `dev2` siguen siendo dos personas distintas; si
los dos clones hubieran derivado al MISMO nombre, `reviewer: peer` se trababa entero — el único
autorizado a cerrar habría sido el autor.

La identidad de una sesión no puede depender de un archivo que un agente puede editar. Se fija
en el entorno, que es exactamente para lo que existe la variable.

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
| el turno no muere sucio | `Stop` bloquea UNA vez por review propia (una card nueva avisa de nuevo) y dos por card sin terminar |
| una review, un verifier | la card claimeada desaparece del `attention` de los demás |
| nadie firma lo suyo | `reviewer: peer` refuta a `dev:X` sobre lo que hizo `agent:X/wN` |
| el commit es del agente | el trailer `Task:` y el bind salen a nombre del lease-holder |

## La regla que gobierna todo el ejercicio

**Que ningún developer se quede sin cards.** Si dev1 arranca y vacía la cola, dev2 no prueba
nada y la corrida no dice nada sobre dos personas. Por eso el board arranca con **ocho cards
independientes** en archivos disjuntos y sólo dos con dependencias, y por eso hay un monitor
que avisa `STARVING` cuando la cola baja de dos. Al que le falte, se le agregan cards en
módulos que nadie está tocando.

## El resultado

Un repo semilla vacío, dos sesiones de Claude Code, una palabra a cada una: `dale`.

```
$ git clone /tmp/lab-origin && cd lab-check
$ PYTHONPATH=src pytest tests -q
731 passed in 0.79s
```

Ciento seis módulos en `main` y ciento dieciocho cards cerradas — **ciento diecisiete por el
peer y NINGUNA por quien la escribió**, con cero intervenciones humanas después de esa palabra.

Dos tandas: la primera corrió CON los bugs que fue encontrando, la segunda con todo arreglado
desde el minuto cero. La segunda encontró dos más, que es el argumento para que haya una tercera.

La card que hace el merge pasa por las mismas reglas que las demás, y lo hace en tandas: cada
vez que un lote cierra, la vuelve a tomar alguien y `main` crece sin que la suite se ponga en
rojo una sola vez. Un merge que dejara los tests rotos sería el fracaso silencioso más caro de
todos, y es lo que más veces verifiqué.

Lo que hizo suficiente el `dale` no fue el prompt: fue el `SessionStart` entregando el rol, el
`SubagentStop` pidiendo el verifier en el momento del handover, el `Stop` negándose a terminar
un turno con una review abierta, y la rama viajando sola al remoto.

## Lo que la primera noche midió

Dos developers, cinco rondas cada uno, una palabra por ronda. Al cabo de veinte minutos:

```
38 cards · 19 cerradas · 0 intervenciones humanas despues del `dale`
cerradas por un PEER: 19      cerradas por el mismo dev: 0
commits atados a un agente: 20   atados a una persona: 8   (las 8 son de antes del fix)
```

Los ceros son el resultado. Ninguna card la firmó quien la escribió, y nadie tuvo que
acordarse de nada: el rol lo entregó el `SessionStart`, la review la pidió el `SubagentStop`,
el turno no pudo morir sucio por el `Stop`, y la rama viajó sola.

## Dos cosas que sólo se ven con dos personas

**El trabajo se hizo dos veces.** Siete cards fueron implementadas por un agente de dev1 y
después, entero y de cero, por uno de dev2 — porque dev2 rechazó las siete como "no hay código"
y no podía ver la rama. Ése es el costo medido del bug de publicación, y es el argumento de por
qué una rama tiene que publicarse sola: no es comodidad, es que si no, dos personas escriben el
mismo módulo.

**Nadie mergea.** Cada card vive en su rama y `src/textkit/` en `main` sigue vacío, así que el
objetivo del proyecto no se puede cumplir por construcción: cada spec dice "NO TOCAR los módulos
de las otras cards" y ninguna card se hacía cargo de juntarlos. Lo encontró dev2, no un test —
un board puede estar entero en `done` y el repo vacío. Ahora hay una card de aterrizaje, la
única autorizada a tocar `main` y `__init__.py`.

**Y una advertencia sobre leer estos logs.** Dev2 reportó como causa raíz que "un update con
sólo un comentario cierra la card". Es falso — lo probé y un comentario no mueve nada; lo que
había era una sola llamada con comentario Y `status=done`, que el modelo leyó como dos. Un
diagnóstico escrito por un agente en una card es una HIPÓTESIS. Las dos cards que reportó como
rotas estaban, en los eventos, correctamente cerradas por su peer.

## Lo que la segunda tanda agregó

- **`attention` recomendaba lo imposible**: le decía a un dev que verificara once cards que
  tiene estructuralmente prohibido cerrar, y la sesión gastó seis llamadas rechazadas antes de
  deducirlo. Consejo que el motor va a rechazar cuesta llamadas y enseña a desconfiar de la
  lista — que es lo único que una barrida no puede permitirse. Después de arreglarlo, una
  sesión corrió `taskops recover` por iniciativa propia por primera vez: cuando la lista deja
  de mentir, se vuelve creíble entera.
- **La integración no se repite sola.** La card de aterrizaje era UNA, se cerró, y el board
  llegó a 101 cerradas con `main` congelado. Hace falta que esa card vuelva a existir, o
  taskops necesita noción de *aterrizar* — hoy no la tiene, y el síntoma es un board que dice
  "todo hecho" sobre un repo que no lo refleja.

Y lo que encontró una SESIÓN, que vale más que los dos anteriores: quince de sesenta y un
archivos de test importaban `pytest`, contra el invariante de cero dependencias fuera de la
stdlib. Nadie lo había visto porque **la revisión por card no puede ver deriva acumulada** —
cada verificador mira su propio diff y la suite pasaba. La sesión lo midió, diagnosticó la
causa, reconoció que la salida era una decisión de proyecto y no la tomó: dejó las dos opciones
con su costo en la card. Eso no lo arregla un verifier mejor; necesita una revisión periódica
del conjunto contra los invariantes.

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
