# Simulacro: dos personas, dos cuentas de Claude, un board

Guía para probar taskops a mano, de cero, con **dos clones distintos del mismo repo** y **dos
cuentas de Claude Code**, sincronizando por el servidor `taskops.bernardocastro.dev` **sin
pushear git**.

Todo lo que sigue está pensado para dos panes de terminal lado a lado. Se anota `[P1]` y `[P2]`.

---

## Por qué el servidor y no git

`.taskops/events.jsonl` es la verdad y viaja **committeado**, así que lo normal entre dos
personas es `git push` / `git pull`. Este simulacro pide explícitamente no pushear git — y sin
git no hay transporte. Por eso acá el transporte es el servidor:

```
   P1  ──push──▶  taskops.bernardocastro.dev  ◀──pull──  P2
                  (mergea los dos logs; los ids
                   tienen content-hash, así que
                   el mismo evento nunca se duplica)
```

`push` manda tu log y **acto seguido se trae el del otro**, así que en la práctica es un `sync`
completo en un comando. `pull` es solo la mitad de bajada.

---

## Paso 0 — el proyecto en el servidor (una sola vez)

Esto corre **en la caja**, no en tu laptop. El servidor guarda cada proyecto en
`~/taskops-server/<nombre>/` y le acuña un token.

El servidor corre en el **container `bernardocastro`** dentro de la caja, como el usuario
`berna`, con el venv en `~/taskops-app/.venv`. `ssh gpu` te deja en el host, no en el container:

```bash
ssh gpu
lxc exec bernardocastro -- sudo -u berna bash -lc \
  "~/taskops-app/.venv/bin/taskops serve init demo-dos"
# imprime el token del proyecto — copialo, se muestra UNA vez
```

Para que las dos personas entren con **su propia cuenta de GitHub** en vez de compartir un
token, atá el proyecto al repo: quien tenga permiso de push al repo, tiene el board.

```bash
lxc exec bernardocastro -- sudo -u berna bash -lc \
  "~/taskops-app/.venv/bin/taskops serve link demo-dos --github bernatch22/demo-dos"
exit
```

> Si preferís no tocar GitHub para la prueba, saltá el `link` y usá el token a mano: en el paso
> 2 se pasa con `--token` en lugar de `taskops login`.

---

## Paso 1 — los dos clones

Dos directorios distintos, mismo `origin`. **Nunca vas a pushear git**; el origin está para que
las dos copias tengan el mismo historial de arranque y para que los hooks tengan un repo real.

```bash
# [P1]
git clone git@github.com:bernatch22/demo-dos.git ~/demo-p1
cd ~/demo-p1

# [P2]
git clone git@github.com:bernatch22/demo-dos.git ~/demo-p2
cd ~/demo-p2
```

Si el repo no existe todavía, sirve cualquier repo de juguete — lo único que importa es que las
dos copias arranquen del mismo commit:

```bash
mkdir -p ~/demo-origin && cd ~/demo-origin && git init -q --bare && git symbolic-ref HEAD refs/heads/main
mkdir -p /tmp/seed && cd /tmp/seed && git init -q -b main
echo "# demo" > README.md && git add -A && git commit -qm "seed"
git remote add origin ~/demo-origin && git push -q origin main
git clone -q ~/demo-origin ~/demo-p1 && git clone -q ~/demo-origin ~/demo-p2
```

---

## Paso 2 — cada clon se suma con UN comando

> Desde el commit de autosync, los pasos 2 y 3 son uno solo:

```bash
# [P1] y [P2], cada uno en su directorio
taskops join https://taskops.bernardocastro.dev/demo-dos?token=<el-token>
```

Eso es `init` + hooks + `.mcp.json` + `remote add` + el primer `pull`, junto. Y desde el mismo
commit **los `taskops push` / `taskops pull` del resto de esta guía son opcionales**: el plan se
comparte solo, y `attention` sincroniza antes de responder. Quedan en la guía porque muestran
qué viaja y cuándo.

## Paso 2 (manual) — inicializar taskops en cada clon

```bash
# [P1]
cd ~/demo-p1
taskops init                       # crea .taskops/, el .mcp.json y los git hooks
taskops setup                      # wirea los MCP servers del proyecto (NO toca tu shell)

# [P2]
cd ~/demo-p2
taskops init
taskops setup
```

`taskops init` es **idempotente** y es la forma soportada de reparar un clon: `.git/hooks` no se
versiona, así que en cada clon fresco hay que correrlo o los hooks no existen.

---

## Paso 3 — conectar cada clon al servidor

```bash
# [P1] y [P2], cada uno en su directorio
taskops login https://taskops.bernardocastro.dev      # abre el navegador, GitHub
taskops remote add https://taskops.bernardocastro.dev/demo-dos
```

Con token en vez de GitHub:

```bash
taskops remote add https://taskops.bernardocastro.dev/demo-dos --token <el-token>
```

Comprobá que quedó:

```bash
taskops remote        # muestra el server de este proyecto
taskops open          # abre el board en el navegador
```

---

## Paso 4 — P1 planifica y empuja el board

Las cards van con **criterios de aceptación EARS**, y eso no es decoración: una card con
criterios **no la puede cerrar el agente que la trabajó** — el motor lo refuta. Eso es lo que
fuerza el handoff que querés probar. `tasks add` no toma criterios, así que van por `plan`:

```bash
# [P1]
cat > /tmp/plan.json <<'JSON'
[
  {"title": "parser de CSV",
   "spec": "Leer un CSV a una lista de dicts. Sin dependencias externas.",
   "acceptance": ["WHEN se le pasa un CSV con cabecera THE SYSTEM SHALL devolver un dict por fila",
                  "WHEN el CSV está vacío THE SYSTEM SHALL devolver una lista vacía"]},
  {"title": "el endpoint /import",
   "spec": "POST /import recibe un CSV y devuelve cuántas filas entraron.",
   "after": 0,
   "acceptance": ["WHEN llega un CSV válido THE SYSTEM SHALL responder 200 con el conteo"]}
]
JSON
taskops tasks plan /tmp/plan.json --actor dev:p1

taskops attention        # el parser bajo DISPATCH; el endpoint todavía no (depende del parser)
taskops push             # sube el log y baja el del otro (todavía vacío)
```

`"after": 0` es el índice de la entrada anterior **en el mismo lote**: el endpoint queda en
`backlog` hasta que el parser cierre. Por eso `attention` muestra una sola card y no dos — el
grafo ya está diciendo cuál es el orden.

```bash
# [P2]
taskops pull
taskops attention        # la misma card, ahora acá
taskops report board     # las dos: el parser en ready, el endpoint en backlog
```

**Ese es el momento de verdad del simulacro.** Si el board de P2 muestra las cards que escribió
P1 — con su dependencia — la sincronización sin git funciona.

---

## Paso 5 — cada persona abre su sesión de Claude

Cada pane, con su cuenta. Si tenés dos binarios (`claude` y `claude-jp`, por ejemplo):

```bash
# [P1]
cd ~/demo-p1 && claude

# [P2]
cd ~/demo-p2 && claude-jp
```

Si son la misma binaria con cuentas distintas, `/login` dentro de cada sesión.

**Lo primero que le decís a cada sesión**, palabra por palabra:

```
Sos el orchestrator de este board. Arrancá con taskops_report kind=attention
y trabajá lo que diga. No implementes vos: despachá a sub-agentes.
Tu actor es dev:p1        ← en P2 poné dev:p2
```

---

## Paso 6 — trabajo en paralelo, y la colisión que NO debe pasar

```bash
# [P1] le decís a su Claude:
"tomá el parser de CSV"

# [P2] le decís a su Claude:
"tomá el endpoint /import"
```

P2 va a rebotar: el endpoint depende del parser y está en `backlog`, así que no se despacha.
**Eso es correcto y vale verlo** — es el grafo impidiendo trabajo que todavía no se puede hacer.
Para tener las dos en paralelo, agregá una tercera card sin dependencias:

```bash
# [P2]
taskops tasks add "logger de errores" --spec "Un logger a stderr con nivel." --actor dev:p2
taskops push
```

Cada sesión hace `taskops_dispatch` sobre su card y spawnea un `taskops-worker`. Mirá los dos
panes: cada worker trabaja en su propio worktree, en su propia rama `tk/<id>/<slug>`.

**La prueba que importa** — que los dos intenten la misma card:

```bash
# [P2], a propósito, sobre la card que P1 ya tomó:
"tomá también el parser de CSV"
```

Después de que P1 haya hecho `taskops push`, P2 hace `taskops pull` y el claim de P1 ya está en
su board: la card no se le ofrece. Sin haber pulleado, P2 puede reclamarla localmente — los dos
logs se mergean y **gana el claim más viejo**; el otro lo ve al sincronizar. Por eso la regla
práctica del simulacro:

> **`taskops push` después de cada cambio de estado.** Es una llamada, es idempotente, y es lo
> único que hace que dos boards sin git digan lo mismo.

Nota sobre identidad: cada comando acepta `--actor`. Sin él, el CLI te resuelve por tu
`git config user.email`, y como los dos clones son de la misma máquina en este simulacro, los
dos serían la misma persona. **Pasá `--actor dev:p1` / `--actor dev:p2` siempre**, o poné un
`git config user.email` distinto en cada clon, que es más fiel a la realidad:

```bash
cd ~/demo-p1 && git config user.email p1@demo.test && git config user.name P1
cd ~/demo-p2 && git config user.email p2@demo.test && git config user.name P2
```

---

## Paso 7 — el handoff a review, que es el punto del ejercicio

Cuando el worker de P1 termina, la card **no** queda `done`: queda en `review`, y su lease se
suelta. El motor lo obliga si la card tiene criterios de aceptación.

```bash
# [P1]
taskops push
taskops attention
# → VERIFY — hand each to the verifier ... tk-xxxxxx  parser de CSV
```

Ahora la parte interesante: **que la revise la otra persona.**

```bash
# [P2]
taskops pull
taskops attention        # la card de P1 aparece en VERIFY acá también
```

Y a su Claude:

```
Verificá tk-xxxxxx: spawneá el sub-agente taskops-verifier contra esa card.
```

El verifier lee los criterios EARS, corre lo que tenga que correr, y cierra o rebota:

```bash
# [P2], a mano si preferís no usar el agente:
taskops tasks done tk-xxxxxx --actor dev:p2 \
  -m "los dos criterios se cumplen: corrí pytest, 4 pass; con CSV vacío devuelve []"
# o el rechazo:
taskops tasks reject tk-xxxxxx --actor dev:p2 \
  -m "el criterio 2 falla: con un CSV vacío tira StopIteration en vez de devolver []"
taskops push
```

```bash
# [P1]
taskops pull
taskops attention
# si fue rechazada → RESUME, asignada de vuelta a su worker
# si se cerró      → ya no aparece
```

---

## Paso 8 — las dos redes de seguridad, a propósito

**Un commit sin card debe fallar.** En cualquiera de los dos panes:

```bash
cd ~/demo-p1 && git checkout main
echo "x" >> README.md && git add -A && git commit -m "prueba"
# → el pre-commit hook lo rechaza y te dice qué hacer
```

**Un worker que muere debe soltar la card.** Matá una sesión a mitad de una card y después:

```bash
taskops recover          # devuelve las cards de workers callados
taskops attention        # aparecen otra vez, listas para despachar
```

---

## El ciclo, resumido en las cinco líneas que vas a repetir

```
taskops pull        ← antes de decidir nada
taskops attention   ← qué está esperando, y qué hacer con cada card
<la sesión de Claude despacha, spawnea, verifica>
taskops push        ← después de cada cambio de estado
taskops open        ← mirarlo con los ojos
```

---

## Lo que hace el servidor, y por qué importa más de lo que parece

Cuando un proyecto tiene remote, **los writes no ocurren en tu disco: ocurren en el servidor.**
`taskops_next` y `taskops_update` viajan por HTTP y se ejecutan en la sqlite de la caja. Eso es
deliberado — es lo único que hace que dos máquinas no puedan reclamar la misma card — pero tiene
una consecuencia que conviene tener presente en este simulacro:

> **Las reglas que corren son las del SERVIDOR, no las de tu laptop.** Un servidor viejo aplica
> guards viejos, en silencio y sin avisar. Si actualizás taskops localmente y algo que debería
> refutarse no se refuta, el servidor es el primer lugar donde mirar.

Redeploy (build local → push al container → reinstalar → reiniciar):

```bash
cd ~/taskops && rm -rf dist && .venv/bin/python -m build --wheel
scp dist/taskops_cli-*.whl gpu:/tmp/
ssh gpu 'lxc file push /tmp/taskops_cli-0.2.0-py3-none-any.whl bernardocastro/home/berna/taskops-app/
  lxc exec bernardocastro -- sudo -u berna bash -lc \
    "~/taskops-app/.venv/bin/pip install -q --force-reinstall --no-deps \
       ~/taskops-app/taskops_cli-0.2.0-py3-none-any.whl && pm2 restart taskops"'
```

## ¿Y el channel? ¿Y el alias?

Los dos están **apagados por default** desde el commit `addf202`, y esta es exactamente la
situación en la que valdría prenderlos.

**El channel** empuja eventos del board *dentro* de una sesión abierta, como interrupciones. Se
apagó porque en una laptop, con una sola persona, casi todo lo que llegaba era el eco de algo
que esa misma sesión acababa de hacer: seis eventos por tarde, uno era noticia. Lo que lo
reemplazó es `taskops attention`, que lee el estado en vez de esperar el evento.

**Dónde sí sirve, y es este simulacro:** cuando el que mueve la card es *otra persona*. El
verifier de P2 cierra la card de P1, y sin channel P1 se entera cuando vuelva a hacer `pull` +
`attention`. Con channel, le llega en el momento. Si querés probar esa diferencia:

```bash
export TASKOPS_CHANNEL=1
taskops setup --channel        # ahora sí escribe el alias en tu ~/.zshrc
# abrí una shell nueva, y en vez de `claude`:
claude-tk
```

**El alias (`claude-tk`) existe solo para eso.** Lo único que agrega es la bandera
`--dangerously-load-development-channels server:taskops-channel`, que es lo que hace que Claude
Code registre el channel. Sin channel, el alias no tiene ningún propósito — por eso `taskops
setup` ya no toca tu shell salvo que se lo pidas.

Para sacarlo:

```bash
taskops setup --remove         # saca el bloque del ~/.zshrc, deja el archivo como estaba
```

> El channel es un **research preview** de Claude Code y puede estar bloqueado por política de
> la organización. Si no aparece, hace falta `channelsEnabled: true` en los managed settings, y
> eso lo habilita un Owner en claude.ai/admin-settings/claude-code. El simulacro entero funciona
> sin él; con él, solo llegan antes las noticias.

---

## Si algo se ve raro

```bash
taskops status           # dónde está el proyecto, en una pantalla
taskops sync             # reconstruye db.sqlite desde el log (la db es descartable)
taskops report board     # todas las columnas y quién tiene qué
taskops tasks log tk-xxx # la conversación entera de una card
```

`db.sqlite` es un cache: borralo y `taskops sync` lo reconstruye. `.taskops/events.jsonl` es lo
único que no se puede perder — y está committeado.
