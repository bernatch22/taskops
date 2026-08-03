# Changelog

## 0.5.3 — una card sin capitulo deja de ser un estado que el sistema carga

El modelo empieza diciendo que **toda card pertenece a exactamente un milestone**, y el codigo
llevaba un balde permanente para las que no. `plan` y `capture` refusan crear una sin capitulo — pero
una card escrita antes de 0.5.0 lleva `""` de por vida, y el UI tenia un sentinel y una fila
`No milestone` para dibujarlas. Medido en un tablero real: su unico capitulo mostrando `0/6` al lado
de un balde con las 56 cards que ese tablero habia cerrado en su vida.

`replay` no lo resolvia, y su propio comentario dice por que: enganchar una card al capitulo que
casualmente este abierto en ESTE clon inventaria un hecho sobre el pasado y diferiria de una maquina
a otra. Ese argumento es sobre una **eleccion** — y con un capitulo en toda la vida del tablero no
hay ninguna: todos los clones foldean el mismo log al mismo id.

`storage/belonging.py` (modulo nuevo: el budget refuso meterlo en `milestone.py` y tenia razon, aquel
foldea los capitulos del tablero y este contesta en cual esta UNA card) resuelve al **leer** y en los
tres lectores que existen — el payload del board, los counts y el slice del worker. Nunca al ingest:
una card es mas vieja que su capitulo. `_snapshot` queda afuera, porque reproduce el evento de la
card en otra maquina y tiene que decir lo que el evento dice.

El balde no se borra. Con varios capitulos activos y cards legacy, adivinar **si** seria inventar, y
ahi la card sigue suelta y toda superficie lo dice. Lo que desaparece es el balde en el tablero donde
la respuesta esta determinada.

## 0.5.2 — el tablero que migra: archivar su historia, y decir quien la hizo

Dos cosas que faltaban para que un tablero anterior a los capitulos quedara entero, encontradas
mirando uno de verdad.

### Una card cerrada tampoco podia archivarse, y eso es TODA la historia

Con `--milestone` puesto, el capitulo nuevo de un tablero real se quedo con sus 6 cards abiertas y
las 57 cerradas siguieron sin capitulo: el picker mostraba el unico capitulo del tablero al lado de
un balde con todo lo que ese tablero habia terminado en su vida.

`edit` refusa cualquier edicion de una card `done` o `cancelled`, y el argumento es correcto para
cuatro de los cinco campos — reescribir el spec de trabajo entregado reescribe el registro de lo que
se entrego. No lo es para `milestone`: archivar no cambia nada de lo entregado, dice **en que
capitulo** se entrego, que es la unica pregunta que se le hace a una card cerrada despues. La
exencion es de un campo, el guard sigue puesto (el capitulo existe y esta activo), ningun status se
mueve, y una llamada que nombra `--milestone` **y** otro campo se refusa entera.

### El header no mostraba a nadie en un tablero con dos developers y 63 cards

`peopleOf` derivaba la gente de tres cosas y las tres son estado **vivo**: quien tiene un lease
ahora, quien tiene una card asignada, quien escribio un objetivo. Un tablero cuyas cards abiertas
estan todas en `review` (que libera el lease) y sin asignar no tiene ninguna de las tres — asi que
la fila devolvia vacio y el header desaparecia. Los nombres estaban en el payload que ya tenia
cargado: `created_by`. Ahora cuenta tambien a quien escribio una card, sigue sin costar un request, y
una cara que dice "nothing in hand" es la respuesta correcta para un dev entre cards.

## 0.5.1 — el modelo de capítulos, usable en el tablero que ya existía

Tres defectos, uno por cada cosa que pasó al abrir el primer milestone de un tablero real. Ninguno
era de lógica: los tres vivían en el día en que el modelo se empieza a usar, que es el día que la
suite no construye.

### `attention` se caía justo cuando el modelo nuevo se usa

`0.5.0` partió el milestone en `title` + `goal` y sacó `text` del contrato. Dos lectores quedaron
atrás, y los dos viven en la dirección que nadie chequea:

- `render/attention.py` imprime el grupo CONFIRM, que **sólo existe cuando un capítulo está en
  review** — el estado normal entre "un agente reportó" y "una persona cerró". O sea que la lectura
  que el `CLAUDE.md` manda abrir cada turno moría con `KeyError: 'text'` en el momento exacto en que
  el capítulo empezaba a funcionar.
- `_planinto.py` lista los candidatos del refusal de `plan`, que **sólo se alcanza con dos capítulos
  activos**. Un refusal escrito a propósito para nombrar la salida contestaba un traceback.

Ningún test los vio porque toda la suite deja su único capítulo `in_force`. Los dos tests nuevos
construyen esas dos formas exactas.

### Una card no podía entrar a un capítulo, así que un tablero que migra quedaba entero afuera

La proyección de `0.5.0` lleva los **hechos** de un tablero viejo hacia adelante y no puede llevar
sus **cards**: enganchar una card al capítulo que casualmente esté abierto en un clon inventaría un
hecho sobre el pasado y diferiría de máquina a máquina. Así que la que tiene que poder moverla es una
persona — y no había verbo. Medido en un tablero de verdad: 63 cards, 6 abiertas, y un capítulo nuevo
que decía `no cards`.

`taskops tasks edit <id> --milestone <id>` ahora la mueve, por el camino que ya existía (un evento
`edited`, la arbitración por timestamp, el `UPDATE` con whitelist) en vez de un segundo camino de
escritura para una columna. Con la validación de `--carry` y **no** la de `plan`: el capítulo tiene
que estar **activo**, porque una card abierta dentro de un capítulo alcanzado es una de dos mentiras.
Y no se puede vaciar: una card pertenece a exactamente uno, así que "sin capítulo" no es un estado
que alguien pida — es sólo la forma en que llega una card escrita antes de que los capítulos
existieran.

### Un capítulo EN VIGENCIA decía "not started"

`◆ Cerrar el menú libre · not started`: la marca decía vigente y la etiqueta decía que nadie lo había
empezado. La fila imprimía eso con cero cards para **cualquier** estado, y "not started" es la
leyenda que el mismo menú usa como título del grupo `planned` — mientras el pill del mismo capítulo
decía `no cards`. Tres renderizados de un estado, dos palabras.

Un capítulo en vigencia sin cards es el primer día normal de uno. Ahora dice `no cards`, y sólo un
`planned` dice `not started`. `Menu` se exporta para que el smoke pueda alcanzar la fila: sólo existe
con el dropdown abierto, y la primera versión de esa aserción probaba el pill y pasaba en verde con
el bug puesto.

## 0.5.0 — milestones: un tablero tiene capítulos, y un humano los cierra

### El objetivo del proyecto no era un hecho, era un capítulo

`objective` era un hecho como cualquier otro y salía de vigencia por ser **superseded**: escribías
uno nuevo y el viejo dejaba de inyectarse. Nada registraba si alguna vez se había alcanzado, así que
un tablero con ocho objetivos superados no podía contestar la única pregunta que el registro existe
para contestar — *qué shippeamos*.

Ahora la norte del proyecto es un **milestone**: un capítulo con estado
(`planned · in_force · review · reached · abandoned`), que un agente abre, trabaja y **reporta**
terminado, y que **solo una persona** puede dar por alcanzado. Es el mismo argumento que `done` en
una card, un nivel arriba: ningún conteo de cards cerradas significa "lo shippeamos".

- **Toda card pertenece a exactamente un milestone**, y un tablero sin ninguno **refusa** planificar.
  Esa es la regla sobre la que se apoya todo lo demás.
- **Varios activos a la vez** es el caso normal: un equipo shippea dos cosas en dos semanas, y un
  tablero que se negara a registrar la segunda estaría en desacuerdo con lo que está pasando. El
  límite no es "un capítulo por tablero", es "un capítulo por card" — así que `plan` **pregunta**
  cuál cuando hay más de uno abierto, en vez de adivinar. Una card en el capítulo equivocado se
  juzga contra las reglas de otra gente y nada lo dice.
- `taskops milestone done <id> --carry tk-…,tk-… --into <id>` mueve lo que quedó abierto al capítulo
  siguiente, porque un capítulo alcanzado con cards abiertas adentro es una de dos mentiras.
- Cancelar **conserva el motivo**. No hay delete: "paramos" no es "shippeamos", y el motivo es lo
  que alguien quiere tres semanas después cuando la misma idea vuelve.

### El `Stop` hook exigía un verifier que ya estaba corriendo

Visto en vivo: la sesión es bloqueada, spawnea un `taskops-verifier`, cierra el turno, **la vuelven
a bloquear con la misma línea**, contesta *"ya está lanzado, no voy a spawnear otro"*, y recibe una
tercera copia. Nada estaba roto salvo el número: un sub-agente reclama la card en su propio proceso
un momento después, así que el segundo bloqueo cae necesariamente antes de que algo pueda probar que
el primero funcionó. Bloquear sobre algo que el lector no puede hacer que pase más rápido es cómo una
red se convierte en una discusión.

Dos mitades:

- **Una vez por card**, y contaba en un solo balde para toda la sesión — así que la primera card se
  gastaba el presupuesto de dos y una card entregada más tarde **no se mencionaba nunca**: el
  silencio exacto que esta red existe para evitar, alcanzado por el mecanismo que lo evitaba.
  `unfinished` conserva dos y esa asimetría es el punto: una card todavía en tus manos la podés
  terminar AHORA.
- **El mensaje ahora nombra la salida.** Una sesión bloqueada sin salida tiene dos movidas: un
  sub-agente duplicado, o discutir. Eligió discutir.

### Un milestone era una sola frase, y por eso el UI no se entendía

Un capítulo tenía `text` y nada más, así que la misma oración hacía de nombre, de objetivo y de
descripción. El síntoma estaba en la pantalla: una banda al 100% del ancho con
`◎ que una clienta suba su CSV y reciba el reporte  +1  by 2026-09-01  2 cards` — de la que no se
podía sacar qué es un milestone, y en la que el segundo capítulo era un `+1` sin forma de abrirlo.

Ahora tiene dos campos, porque se leen en lugares distintos y a largos distintos:

- **`title`** — tres o cinco palabras (`El importador`). Es lo que imprime el selector, el badge de
  una card y cada línea de log. Corto POR ESO: antes, todo lo que tenía que meterlo en una fila lo
  cortaba a la mitad de una palabra.
- **`goal`** — qué significa *done* y qué queda afuera, en las palabras que haga falta. Es lo que
  lee todo worker del capítulo, así que el borde se escribe adentro: *"NO entra el envío por mail —
  ese es el capítulo siguiente"*. Un goal escrito como `decision` fue la primera versión de esto, y
  quedaba en una lista de fallos técnicos donde nadie lo leía como el punto del trabajo.

`edit` deja en paz lo que no le pasás: escribir un goal no borra el nombre que alguien eligió.

**Los tableros viejos no se reescriben.** Un capítulo pre-0.5.0 tiene `text` y el fold lo mapea a
`title` — se lee largo, que es un problema de display y no de datos.

### La UI: un selector, y un modal por cada sujeto del modelo

La banda murió. En su lugar, arriba de las columnas, un **pill** del tamaño de su texto:

```
╭─────────────────────────────╮ ╭───╮ ╭───╮
│ ◆ El importador ▾  ▬▬▬░ 3/7 │ │ ⓘ │ │ ◎ │
╰─────────────────────────────╯ ╰───╯ ╰───╯
```

- **Elegir un capítulo filtra el board**: las columnas quedan, sus cards cambian. Sin filtro, cada
  card dice a qué capítulo pertenece; filtrado, ese badge desaparece.
- El dropdown muestra **el estado de todos mientras elegís** — progreso, quién está adentro, y cuál
  espera a una persona. Eso es lo que hace visible que dos agentes trabajan en capítulos distintos.
- **`ⓘ` es el dashboard del capítulo**: el goal completo arriba y en grande, el progreso, quién está,
  qué scopes toca (derivado de los labels de sus cards), y los objectives/rules/decisions/notes que
  son SUYOS. Sin lista de cards: el board está tres pulgadas más abajo y ya las dibuja.
- **`◎` es el modal del proyecto**: lo que vale para siempre, lo que el engine REFUSA, y el registro
  de lo shippeado. Los tabs `Project | Milestones | Policies` se fueron: partían en tres cosas que
  se leen juntas y hermanaban un hecho de proyecto con uno de capítulo, que es lo contrario de lo
  que dice el modelo.

Y un `npm run smoke`: los componentes renderizados a string contra un payload REAL del servidor,
con 18 aserciones sobre comportamiento y no sobre markup. Existe por un bug y tiene su forma: elegir
un milestone no cambiaba las cards. `tsc` estaba limpio, el payload estaba bien, el servidor estaba
bien, y nada en la suite miraba el cableado entre el selector y las columnas. Las tres mutaciones
que le metí las caza.

### Un hecho ahora tiene VIDA, y es lo único que impedía que el contexto creciera para siempre

Un hecho declara su `level` al escribirse: `project` vive para siempre, y cualquier otro pertenece al
capítulo en vigencia y **se va de todas las rebanadas** cuando una persona lo da por alcanzado. Nadie
lo retira a mano.

El alcance ya tenía dos dimensiones y ahora son tres, y cada una protege algo distinto:

    labels/files   ──▶ RELEVANCIA: una decisión sobre la base no llega a una card del parser
    owner          ──▶ TAMAÑO con el EQUIPO: una rebanada crece de UNO, sean tres o treinta
    milestone      ──▶ TAMAÑO con el AÑO: lo decidido en marzo no se inyecta en diciembre

La segunda ya estaba; la tercera es nueva y es la que no se podía arreglar con alcance por tema.

### Tres sustantivos donde había dos comandos y un flag

`--mine` decía dos cosas distintas en el mismo comando — "archivá esto bajo mí" al escribir y
"mostrame mi página" al leer — y tenía que decirlas, porque `objective` podía significar la norte del
proyecto **o** la de un dev. Ya no puede: la norte es un milestone.

```sh
taskops milestone …          # el capítulo: new, start, edit, review, done, reject, cancel, show, list
taskops context …            # lo del PROYECTO y del capítulo: rule, decision, note, log, retire
taskops me …                 # lo tuyo: objective, decision, note, retire
```

- **Se fueron**: `context objective`, `context show`, `--mine`, `--owner`. Tipear la forma vieja
  contesta con el reemplazo, porque la refusa de argparse lista las opciones y nunca dice a dónde se
  mudó el verbo.
- **`rule` es su propio sort** y se imprime aparte: una decisión sin `labels` ni `files` alcanza toda
  card — eso *es* una regla, mecánicamente — y en una lista plana la más fuerte del tablero quedaba
  entre dos notas sobre la base de datos.
- Un `objective` **sin dueño está refusado**. Antes se aceptaba y no lo leía nadie: quedaba archivado
  bajo un dev que no existe. Los tableros viejos que tienen alguno lo siguen mostrando, marcado
  `project` — un hecho no puede desaparecer porque cambió una versión.
- Un `note` no puede ser `--project`: si es permanente es un `rule` o una `decision`, y una nota que
  sobrevive a su capítulo es el scratchpad que hizo crecer la rebanada para siempre.

### El prompt que lee una sesión, en cuatro bloques

Lo que es verdad **independientemente del trabajo** va antes del trabajo: las reglas del proyecto,
después los settings que el engine **refusa**, después el capítulo con sus counts y sus hechos, y al
final lo que espera a una persona. Un lector que aprende el capítulo antes que las reglas juzga las
reglas por el capítulo, que es al revés.

`taskops attention` gana un grupo **CONFIRM**: un milestone reportado terminado espera a una persona,
y es lo más grande del tablero que nada más destraba. Un sweep que lo omitiera reportaría un tablero
tranquilo con un capítulo entero esperando que lo cierren. El saludo y la barra de abajo leen el
capítulo en vez de un objetivo — la misma frase, con una fuente que no se supersedea en silencio.

### Un capítulo creado desde un clon no existía en el servidor

Un bug de una línea y del peor tipo posible: la fila rpc de `milestone_create` nombraba una función
que no existe (`ms.open_wrapped`), así que abrir un capítulo desde un clon reventaba **en el
servidor**. Toda la suite pasaba, porque cada test corría un solo store — la misma clase de bug que
ya costó doce en tres días. `tests/e2e/test_milestone_over_the_wire.py` es el arreglo: un servidor
real, un clon real, y las cinco cosas que tienen que pasar allá y no acá. Cada una mutada a mano.

Y `need()` iteraba un `Store` en el camino de la refusa (`matching(store, …)`), así que un id
ambiguo daba `TypeError` en vez de la frase que dice cuál es.

### Herramientas y superficies

- **`taskops_milestone`** (la décima): sin argumentos, **todos** los capítulos activos con sus
  counts; con `milestone=<id>`, ese capítulo **y sus cards** — que es "cómo llego a sus cards" en una
  llamada y no en dos.
- **`taskops_context`** gana `level` y `milestone`, y **pierde `mine`**: `state=objective` es el del
  que llama, siempre, sin flag. `taskops_plan` y `taskops_capture` ganan `milestone`.
- `GET /api/milestones`, y `/api/context` + `/api/task/context` contestan la rebanada v2. La UI
  agrupa por capítulo, muestra los counts y la lista de capítulos terminados.
- Un turno de dos módulos nuevos por presupuesto de arquitectura, y cada corte era una costura real:
  `contracts/slice.py`, `contracts/_factfields.py`, `usecases/_moving.py`, `usecases/_joins.py`,
  `usecases/_planinto.py`, `usecases/_stating.py`, `usecases/_whose.py`, `render/_blocks.py`,
  `render/_moves.py`, `transports/http/_routes.py`, `transports/http/_verbms.py`.

Lo que sigue salió después de 0.4.0 y sale con esta versión.

### El worker de una persona no podía tomar la card de esa persona

El camino normal de delegación estaba roto de punta a punta: asignás una card a `dev:ana`, la
sesión de Ana spawnea un worker, y `agent:ana/w1` era **refusado su propia card** — tanto pidiéndola
por id como pidiendo "cualquiera", porque el pool filtraba con la misma comparación. El worker se
iba al pool y agarraba otra cosa, que es exactamente el síntoma que ya costó cuatro sesiones de
debugging cuando la causa era otra (un sub-agente que no se nombraba).

La comparación era por **actor id**, y un actor id no es una persona. Ahora se pliega a dev en
`engine/identity.assigned_to`, el mismo pliegue que ya hacían `reviewer: peer` y la rebanada de
contexto: un `agent:ana/w1` y un `dev:ana` son una persona con dos manos.

Pliega en **un** sentido y nunca entre personas, y las dos mitades se pagan solas:

- un assignee `agent:` sigue siendo de ESE worker — un dispatch hecho para él o una card devuelta
  con findings — así que ni su propio dev se la lleva por delante;
- `agent:juan/w1` sigue siendo rechazado en una card de `dev:ana`, que es lo único que impide que
  "assigned" sea una etiqueta que cualquiera ignora.

El ruteo de reviews no se toca: un assignee `dev:` en `review` es el revisor elegido y lo sigue
distinguiendo `routed_to`, con su expiración intacta.

`engine/_pool.py` sale de `scheduler.py`, que estaba en 70 de 70 líneas de código y 159 de 160 de
archivo: no entraba ni el import. Eran dos cosas — la mecánica de un claim (unblock, sweep, lease,
branch) y **qué se le ofrece a quién**, que no escribe nada. Y se borró la copia muerta de esa
valla que había quedado en `usecases/claim.py`, con la regla vieja adentro.

### Una persona no podía ver bajo qué contexto trabaja el agente de una card

Lo que un worker recibe al claimear una card — la rebanada: el objetivo, lo que el proyecto tiene
zanjado y que alcanza a ESA card — no tenía forma de leerse desde afuera. Había `context_for` como
caso de uso y como verbo rpc, pero **ninguna ruta HTTP**, así que la UI solo podía mostrar el
overview del proyecto entero, sin el angostamiento por sujeto.

`GET /api/task/context?id=<tk-…>` la expone verbatim — la misma llamada que hacen la tool MCP y
`SessionStart`, no una aproximación filtrada distinto — y el drawer de una card la muestra
inmediatamente antes de la spec, por el mismo argumento que ordena ese módulo: el lector para
temprano, y algo ya zanjado leído DESPUÉS del plan que debía moldear es una decisión
re-litigada en el diff. Sin policies: una policy es un setting de proyecto que no se angosta por
card, así que repetirla en cada una sería una copia por card de un hecho que no varía por card.

`get_context` se mudó con ella a `transports/http/context.py`: `api.py` estaba en 68 de 70 líneas
de código y no entraba otro handler. Que un módulo no entre es la invariante avisando que hace dos
cosas — y ahí eran dos: los endpoints del board, y el contexto.

### El verificador leía el contexto equivocado

La rebanada de una card es el proyecto **más una persona**, y esa persona pasa a ser el **autor**
y no el `assignee`. Son lo mismo mientras la card se trabaja; en `review` no: el ruteo escribe en
`assignee` al **revisor** elegido, así que un verifier de otro dev recibía su propio objetivo y
nunca el de quien hizo el trabajo — justo el que necesita para juzgarlo.

El autor sale de los **eventos** (`entered_review_by`, la misma derivación que usan los guards de
cierre) y no de una columna nueva: el log ya dice quién movió la card y hacia dónde, y una segunda
copia de esa respuesta es una copia capaz de discrepar. `_contextslice` sigue siendo puro — recibe
el autor ya resuelto, no el store — que es lo que mantiene la regla testeable desde literales.

La rebanada sigue creciendo en **uno**: el contexto del verificador no se suma al del autor.

### Dos especialistas, no cuatro — y un solo modelo fijado

`taskops-lead` y `taskops-fixer` se van. Ninguno se ganaba un archivo:

- El **lead** es el orquestador con otro nombre: mismas tools menos `Edit`, mismo trabajo, un
  nivel abajo. Y la sesión que planificó es la que ya tiene el plan en la cabeza, así que
  delegar el epic a otro agente era duplicar al que ya estaba ahí.
- El **fixer** es un worker cuya card resulta ser un conflicto de merge: el mismo loop, los
  mismos guards, y un prompt más angosto. Dos roles que en realidad son uno, descritos dos
  veces, son dos lugares para que la misma regla se desincronice.

El árbol pasa a ser de dos niveles y sigue sin poder ser más profundo, porque eso es una
propiedad de las tool lists y no una regla que alguien tenga que recordar.

Y el modelo: **el worker no fija ninguno, el verifier fija `opus`.** La asimetría es la política
entera. Una card que es un typo en un docstring y una que es una máquina de estados tienen la
misma forma para ese prompt y no se parecen en nada como trabajo — y el orquestador que la
despacha es el único que leyó la spec, así que fijar un modelo ahí sería pagar de más en cada
card chica o mandar uno barato a las difíciles. El verifier es lo contrario: su trabajo es ser
más difícil de convencer que el worker, así que **no puede ser el más débil de los dos**, y sin
modelo heredaría lo que la sesión estuviera corriendo — que en una sesión barata es un sello de
goma con pasos extra.

Los strings que apuntaban al fixer y **corren** — `attention` bajo `LAND`, el `why` de un
landing que no mergeó — ahora dicen `taskops-worker`. Eran los que le decían a una persona qué
spawnear, así que dejarlos nombrando un agente que no existe habría sido un `Agent type not
found` en el peor momento.

## 0.4.0 — el board sin GitHub, la barra de abajo, y el tablero local que se levanta solo

### Perfil de dev, y el modal que estaba roto

Donde estaba el botón del chat hay ahora **mini avatares** — dos letras, anillo lime si tienen
lease vivo — y un click abre el perfil de esa persona: sus números, su objetivo, sus decisiones
técnicas, sus invariantes, y las últimas cards que tocó. La fila no cuesta ningún request: sale
de lo que el board ya cargó. El perfil hace **un** fetch, al abrirse.

`agent:ana/w1` **es ana**: el mismo pliegue que hace el engine para `reviewer: peer`. Sin eso un
board con un solo dev mostraría cinco caras.

**Y el modal se veía transparente y descuadrado, y no era el CSS.** El perfil se monta dentro del
header, el header tiene `backdrop-filter: blur(12px)`, y un ancestro con `backdrop-filter` **se
vuelve el bloque contenedor de sus descendientes `position: fixed`** — así que `inset: 0` cubría
40 píxeles de header en vez del viewport, con el panel apretado adentro como flex item. Arreglado
donde no puede volver a pasar: los dos modales van por un `Overlay` que hace **portal a
`document.body`**, así la posición de un overlay no depende de dónde viva el botón que lo abre.

De paso, una sola implementación de las tres cosas que un overlay hace mal: Escape, click en el
backdrop que cierra, y click adentro que **no**.

### El drawer de una card quedaba debajo del modal

`z-index: 40` contra los 50 del modal, y una card se abre rutinariamente **desde** uno — el
perfil lista las cards que tocó esa persona. Llegaba detrás del scrim: invisible hasta cerrar
justo lo que habías clickeado. Ahora va en 60, y Escape es del **de arriba**: el drawer aprendió
a cerrarse con Escape (antes no lo hacía en absoluto) y el `Overlay` se abstiene mientras haya
un drawer abierto.

### `plan` ahora pregunta quién revisa

No hay default de proyecto para el reviewer y no lo hubo nunca: sin policy, una card sale
nombrando a nadie. Eso está bien para el primer día — un dev solo, nadie más en el board, y una
regla que rechazara todo cierre haría la herramienta inusable — y está mal como estado
permanente, porque el único guard que queda es el más débil de los tres: **un agente no puede
cerrar el review que él mismo abrió**. Un segundo agente del mismo dev sí puede, y el dev también.

Así que el resultado de `plan` lo dice, una vez por lote, con los ids adelante y las cuatro
formas de decidirlo. En el **valor de retorno** y no en una guía: una instrucción no es un
mecanismo, y lo que un modelo tiene que accionar va en el mensaje que lo necesita. Calla cuando
todas las cards ya lo dicen — un párrafo que aparece siempre es un párrafo que nadie lee.

### Se fue el chat del board, y con él la última cosa dirigida a nadie

El sidebar (`⌘K`) alcanzaba «la sesión que esté corriendo el canal», y la sesión contestaba con un
`reply` sin card. Las dos mitades asumen que hay **exactamente una** sesión escuchando — y en un
board compartido pueden ser cinco, cada una en su máquina con su propio canal conectado. Una
pregunta dirigida a quien esté mirando no tiene audiencia contestable, y una respuesta dirigida a
nadie no tiene destino.

Eliminado de las dos puntas, porque dejar la mitad era dejar endpoints sin cliente: el sidebar,
`/api/chat`, `/api/conversation`, `usecases.chat`, el kind `chat` (y su exención en
`LOCAL_ONLY_KINDS`), la rama sin card de `reply`, y el corte de conversación al arrancar. `reply`
ahora **exige `card`**.

Lo que quedó es más simple de describir: **todo lo que llega a una sesión está DIRIGIDO** — una
mención, un review ruteado a un dev, una card asignada a uno de sus agentes. Que es lo que hace
verdadera la promesa del canal: si no actuás sobre un evento, nadie lo hace.

Una pieza tuvo que mudarse. El botón «asignar a un especialista» de la UI publicaba un pedido de
dispatch **en el chat**; ahora es un comentario **en la card, con el destinatario mencionado** —
dirigido, entregado en su próximo tool call, y archivado bajo el trabajo del que habla en vez de
al lado. Se fue también la tira de herramientas, que era parte del sidebar; los eventos
`activity` se siguen escribiendo y el board vivo los sigue leyendo como el «doing» de cada card.

### `in_progress` seguía vivo en la UI, y no existe

El engine tiene **siete** estados: `in_progress` se eliminó hace tiempo (`engine.replay` lo
reescribe a `claimed` para logs viejos) y `TaskPanel.tsx` ya lo decía. Los restos estaban en
`contracts.ts`, `bits.tsx` y el CSS — o sea una columna que nunca podía tener cards. Fuera. La
columna `claimed` ahora se llama **«In progress»**, que es lo que significa para quien mira el
board, y ya no hay ambigüedad porque no hay segunda columna con ese nombre.

### Un proyecto local ahora tiene tablero, y se levanta solo

`taskops open` en un proyecto sin remoto se negaba y te mandaba a `taskops ui` — un comando que
**bloquea**, en la terminal que estabas usando para otra cosa. Ahora lo levanta él.

- `taskops ui` **anota dónde quedó escuchando** (`.taskops/ui.json`, gitignored) después del
  bind y nunca antes: una nota escrita sobre la intención anuncia un puerto que un error de bind
  está por dejar muerto. El puerto lo elige el SO (`--port 0`), así dos proyectos abiertos a la
  vez no colisionan — fijarlo en 2140 hacía que el segundo fallara dentro de un hijo detached,
  o sea con una URL que no responde y ningún error a la vista.
- El hook de `SessionStart` lo ofrece: si el proyecto es local, levanta el tablero antes de
  armar el saludo, así **la primera línea siempre tiene a dónde hacer click** — local o remoto.
  Detached como el sweep, mudo ante cualquier falla, y `TASKOPS_NO_UI=1` lo apaga.
- Una nota vieja es peor que ninguna, porque apunta el navegador a un puerto que ahora puede ser
  de otro programa. Se verifica dos veces: el pid vivo (barato) **y** que el puerto conteste —
  un pid que el kernel reasignó pasa el primer chequeo.

### La lista de boards del server, legible

Era un `<ul>` monoespaciado de nombres. Ahora cada fila dice el repo de GitHub detrás si lo hay
y **cuándo se movió por última vez** — que es la pregunta que uno le hace a una lista de boards.
Sigue sin build step y sin dependencias, porque esta es la página que tiene que contestar
justamente cuando algo está roto. El `updated` sale del mtime del log: un `stat` por board, así
la portada cuesta lo mismo con nueve cards que con novecientas, y sigue andando cuando el sqlite
de un board es lo que se rompió. Un contador de cards abiertas costaría abrir cada base.

### Un board sin GitHub no aparecía en la lista de nadie

Las sesiones se acuñan desde GitHub, así que un board sin repo detrás no podía salir en ningún
`/api/projects`: lo creabas desde tu laptop y la portada del server no lo listaba. `board create`
sin GitHub ahora devuelve **también una sesión**, sobre ese board y nada más — exactamente la
forma que redimir un invite ya producía. El `login` ahí es una ETIQUETA, no una identidad: nada
la verifica y nada depende de ella, la autorización son el token y la lista de proyectos.

### `board create` exigía GitHub, y el remoto nunca lo necesitó

El flujo de tres comandos — `remote add <server>`, `board create <name>`, `board invite <who>` —
**fallaba en el primero**. Cuatro fallas, y ninguna la encontró la suite: todos los tests de esta
superficie llamaban a `create_hosted` directo, así que ninguno pasaba por el parser, por el
default de `--repo`, ni por el comando que corre cuando todavía no hay board.

- **`board create` sin GitHub se negaba.** Un checkout sin origin, un repo en un GitLab, un
  directorio que no está en git: todos chocaban con "pass `--github owner/repo`" en el primer
  comando, contra un server que nunca necesitó GitHub para tener un board. Ahora `github` vacío
  es *el otro tipo de board*: el server lo provisiona y **devuelve su token**, que es lo único
  que podía devolver — la ruta con GitHub puede acuñar una sesión porque GitHub ya dijo quién
  sos, y esta no. Con eso `board invite` sigue funcionando sin tocar nada: el derecho a invitar
  es el derecho a escribir, y lee ese mismo `remote.json`.
- **`remote add <server>` pelado se negaba** pidiendo un token. Un servidor sin path no nombra
  ningún board, así que no hay a qué autenticarse ni con qué. Ahora lo anota y dice qué sigue.
- **`board create test` ignoraba el nombre.** El posicional caía en `who`, que solo lee
  `invite`, y el board terminaba llamándose como el directorio.
- **Y el nombre por defecto salía vacío**: `--repo` default es `.`, y `Path(".").name` es la
  cadena vacía, así que se negaba con ``cannot make a board name out of `` `` hablando de un
  directorio con nombre perfectamente bueno.

Quién puede crear en la ruta sin GitHub es una pregunta de despliegue y la contesta el server:
`taskops serve --no-create` cierra la puerta, y en esa ruta **ese flag es todo el control de
acceso** — no hay chequeo de GitHub detrás. Hay un test que lo fija, porque un flag que cerrara
una puerta y no la otra se leería como cerrado estando abierto.

### La barra de abajo: `taskops statusline`

Claude Code deja configurar la fila que pinta encima de sus propios badges del footer. Ahora
taskops la escribe, y `taskops init` la cablea sola en `.claude/settings.local.json` — sin tocar
un `statusLine` que ya tuvieras puesto.

```
-- INSERT --  ·  ◐ tk-92c0aa el parser de fechas  ·  4 to hand out, 2 to review  ·  probe (shared, cached)  ·  78% ctx
```

Tres decisiones, y las tres salen de la cadencia: esa fila se repinta con un debounce de 300 ms.

- **No toca la red y no escribe.** Nada de `heartbeat`, nada de `unblock`, ningún round trip
  HTTP. Un pedido por ráfaga de tecleo contra un board compartido, y una proyección que
  escribiera convertiría *mirar la pantalla* en un evento del log append-only.
- Por eso, con remoto **dice `cached`**. El claim de un compañero llega a esa fila en el próximo
  sync, no en el instante en que lo hace, y una barra que ocultara la diferencia prometería una
  liveness que no tiene.
- **No puede sacar `⏵⏵ bypass permissions on`**: la status line va en su propia fila, encima de
  los badges, no en lugar de ellos. Lo que sí hace es repetir `-- INSERT --` cuando usás vim.

No renderiza vocabulario del board: `5 to hand out`, no `5 dispatch`.

### La columna «Claimed» ahora dice «In progress», y hay una sola

`claimed` e `in_progress` son dos estados porque el engine los necesita — uno es un lease vivo,
el otro es un worker que además lo declaró, y `claimed → done` es legal — pero al que mira el
board las dos columnas le contestaban la misma pregunta. La UI las **pliega en una**. No se
pierde nada: la marca de la card sigue diciendo cuál es (`◐` tomada, `●` reportada en curso).

### El saludo de apertura, reescrito por cuarta vez

Las tres versiones anteriores fallaron por la misma razón y la última lo dejó explícito:
`5 card(s) need dispatch` es jerga. `dispatch`, `specless`, `stalled` y `land` son estados del
scheduler; la línea ahora los traduce a inglés que se entiende sin manual, abre nombrando lo que
está corriendo, y **dice si el board es compartido o solo de esta máquina** — porque "5 listas
para repartir" significa otra cosa en un board que ve el equipo.

### Un id impreso quedaba cortado y no servía para pegar

Un id de taskops es `tk-` más seis hex: nueve caracteres. Los dos renderers nuevos lo cortaban
en ocho, o sea imprimían un handle que no resuelve a nada. Entero en los dos.

### `--mine` borraba el objetivo del equipo, en silencio

Encontrado corriéndolo, y dos veces seguidas. `--mine` archiva un hecho bajo el que llama, y
resolvía mal el id: primero al literal `"me"`, después al nombre pelado `berna`. Ninguno de los
dos parsea, así que `dev_of` contestaba `""` — o sea **el hecho se guardaba como del PROYECTO**.
Y como un objetivo lo supersede el más nuevo con el mismo dueño, decir "mi objetivo es X"
**borraba el norte del equipo de la rebanada de todos**. Sin error, sin aviso.

Dos arreglos, porque el primero solo habría dejado la trampa armada:

- `--mine` resuelve el id COMPLETO (`dev:berna`), vía el mismo `whoami` que usa todo lo demás.
- **`state` refuta un `owner` que no puede parsear.** Un typo no puede poder borrar el norte:
  `me`, `berna`, `dev:` y `agent:nope` se rechazan nombrando la forma correcta.

### Una sesión abría y la persona no veía nada

El hook de `SessionStart` emitía `additionalContext`, que Claude Code envuelve en un system
reminder que **el humano nunca ve** — y el stdout plano de un hook de SessionStart también está
oculto. Así que abrías una sesión, el agente recibía el board entero, y vos no tenías forma de
saber que taskops había corrido, mucho menos que tres cards te estaban esperando.

`systemMessage` es el único campo que llega a la terminal. Ahora se emite una línea:

    taskops · ◎ que el importador ande · ◎ el parser, sin regex · 2 waiting · https://…/probe/

**Una línea, y se gana el lugar en todas las sesiones para siempre.** Lleva el OBJETIVO — el del
proyecto y el tuyo —, qué te está esperando, y la URL del board cuando hay servidor, sin el
token: esto se imprime en un scrollback y en lo próximo que compartas pantalla.

El objetivo lo había dejado afuera, con el argumento de que el modelo lo tiene y quien lo
escribió se acuerda. La primera corrida mató ese argumento: abrís un proyecto que no tocás hace
una semana y no te acordás — que es la misma razón por la que la barra de contexto de la UI está
siempre a la vista y no detrás de una pestaña.

Callada cuando no hay nada: un board vacío lo dice una vez — que es la diferencia entre "no hay
nada que hacer" y "el hook no corrió", indistinguibles en una pantalla vacía — y un repo sin
board no imprime nada.

El test vive en el hook y no sólo en el renderer: una línea correcta y no enganchada es una
línea que nadie ve, y los tests del renderer pasan igual.

### Contexto de PROYECTO y contexto de DEV — una regla, dos dimensiones

Un hecho tenía una sola forma de acotarse: `--labels` / `--files`, o sea por TEMA. Ahora tiene
dos, y la segunda es por PERSONA:

    labels/files  →  una decisión sobre la base no llega a una card del parser
    owner         →  un hecho que alguien enunció para sí llega a sus sesiones y a nadie más

Una sola regla para los cuatro sorts: **con dueño llega a ese dev, sin dueño llega a todos.**

- **Un objetivo por dueño**, no uno global. "El equipo va al importador" y "yo esta semana estoy
  en el parser" son dos frases verdaderas al mismo tiempo, y con un solo lugar la segunda pisaba
  a la primera — decir en qué estabas borraba la razón por la que alguien lo estaba haciendo.
- **La rebanada trae LAS DOS**: `objective` es el norte del proyecto y `yours` el de quien tiene
  la card. No una en lugar de la otra.
- **Y crece en UNO, no en la cantidad de devs.** Ésa es la propiedad que hace que esto no se
  degrade: con tres developers, cada worker sigue leyendo dos objetivos. Es la razón de que
  `owner` sea un FILTRO y no una etiqueta — pasando de ~150-200 instrucciones permanentes la
  obediencia se cae, así que una página que crece con el equipo empeora a todos los agentes cada
  vez que entra alguien.
- **Un cuarto sort, `note`**: lo permanente que no es ni objetivo ni regla — una costumbre, una
  advertencia. Normalmente propio, que es para lo que existe.
- **`--mine`** archiva bajo el que llama, para que nadie tipee su propio id. Y `context show`
  sigue siendo la VISTA GENERAL — muestra los objetivos de todos, porque "quién está en qué" es
  exactamente la pregunta de alguien decidiendo a quién darle una card. `--mine` la vuelve tu
  página.
- Un agente lee lo de su dev: `agent:ana/w1` recibe lo de `dev:ana` — un agente y su developer
  son una persona con dos manos, la misma comparación que hace `reviewer: peer`.

**Y había dos renderers del slice.** El CLI tenía el suyo además de `render.render_context`, y
las copias derivaron en cuanto una creció: la del paquete aprendió a mostrar el objetivo de cada
dev y la del CLI no, así que la misma rebanada se leía distinto según por qué puerta entrabas.
Queda uno.

### El contexto se escribe por MCP, y la cerca se mudó a donde aguanta

`taskops_context` era sólo lectura, con este argumento: *"un worker que pudiera reformular un
objetivo podría reescribir las reglas contra las que se lo juzga"*. El argumento es correcto y
**el mecanismo no protegía nada**: un worker tiene `Bash`, así que `taskops context objective …`
siempre estuvo a una llamada. Lo único que lograba era ponerle fricción al caso legítimo — el
orquestador, el único que tiene algo que hacer seteando un objetivo, tenía que shellear.

Dado vuelta:

- **La mitad de escritura está en el MCP**: `state` + `text` (+ `labels` para el alcance de una
  decisión) y `retire`. Cuatro campos y no siete — `--horizon`, `--owner` y `--files` siguen
  siendo del CLI, porque cada campo acá le cuesta contexto a todos los agentes conectados en
  cada llamada.
- **La cerca está en el use case**, que `Bash` no puede rodear: un actor `agent:` es refutado,
  uno `dev:` no. Es exactamente la línea entre un worker y la sesión que planificó su trabajo,
  y es la que layer 0 ya dibuja — *"guards that demand a justification accept one from a dev and
  reject it from an agent"*. Vive en `engine.identity.a_person`, porque es una regla sobre un
  actor id y nada más.
- **`actor` entró al schema de la tool**, y sin eso la cerca no podría dispararse nunca: un
  llamador que no puede nombrarse resuelve desde git config y llega como el developer.

El test que pineaba lo viejo se fue con la regla vieja, reemplazado por dos: que la tool anuncia
la escritura, y que un `agent:` es refutado — que es **más fuerte**, porque cubre también la vía
por `Bash`, que es la que un agente habría tomado.

Y de paso: dos docstrings de `context.py` estaban DESPUÉS del `return`, así que no eran
docstrings sino expresiones muertas. `show` e `history` no tenían documentación.

### La narración del sweep se quedaba en el laptop

`report sweep --push` existía y **ningún disparador lo pasaba** — ni el hook de `SessionStart`
ni la tarea agendada. Y el flag era `store_true`, así que un flag que nadie pasó llegaba como
`False`. En un board que vive en un servidor eso significa que cada narración desatendida se
escribía en la máquina de alguien y se quedaba ahí: nadie más la veía, y la pestaña Reports del
propio board nunca la tenía — que es exactamente lo único que el sweep existe para producir.

Ahora `push` es **`None` por defecto y significa "sí, si el proyecto tiene remote"**. Un
proyecto local no manda nada (no tiene a dónde, y `push` refutaría), y `--no-push` sigue siendo
la forma de decir que no. Los flags del sweep se mudaron a `_sweep.py`, donde vive el comando,
en vez de estar al lado de seis que son de los dossiers.

Los reportes son ARCHIVOS, no eventos, así que son lo único que un board remoto todavía manda
por `push` — junto con la migración de una vez.

### `taskops board invite`: una puerta por persona, para un board sin GitHub

Un board sin repo de GitHub tenía una sola forma de entrar: el token del proyecto. Un string
compartido, anónimo, y rotarlo deja afuera a todos. Ahora el dueño acuña un código por persona:

```
$ taskops board invite ana
  send them this — it works ONCE, and expires in 7 days:
      taskops join https://…/probe?invite=4596964247820…
```

Ana corre **esa línea y ya está trabajando** — `join` inicializa, instala los git hooks, cablea
el MCP, canjea el invite por una sesión y llena el board. Reusa `join` a propósito: un verbo
nuevo para canjear serían dos pasos, y el segundo es el que la gente olvida — un código gastado
y ningún board.

Cuatro propiedades, cada una cierra una fuga distinta:

- **un solo uso** — un código que sirve dos veces sirve para siempre, porque está en un chat;
- **expira** a la semana, el mismo número que la sesión, porque dos ventanas son dos cosas que
  razonar y nadie sabe cuál lo mordió;
- **nombra a la persona**, así el board registra `dev:ana` y no "alguien que tenía el link" —
  que es la razón entera de no compartir el token;
- **se guarda hasheado**: un `invites.json` filtrado es una lista de nombres, no un juego de
  llaves. El código existe en un solo lugar, el mensaje que mandó el dueño.

Y un código desconocido y uno vencido dan **la misma respuesta**: distinguirlos dice si un
string adivinado alguna vez existió, que es lo único que un adivinador aprende.

Quién puede invitar sale gratis: la ruta cuelga del mount del board, así que el `Policy` que ya
existe la protege — el derecho a invitar es el derecho a escribir, y ésa es la credencial que ya
está en `remote.json`. Un board **ligado a un repo** no necesita nada de esto: el push access ya
es la invitación, y se revoca cuando se revoca el repo.

### Un rechazo llegaba en blanco, y el worker adivinaba

`taskops tasks reject` exige `-m` desde que existe, y su propio docstring dice por qué: *"una
rechazada sin hallazgos es una card devuelta sin nada sobre qué actuar: el worker lee «no
alcanza», adivina, y la card da dos vueltas al pedo"*.

**Esa regla vivía en argparse.** Valía para una persona en una terminal y no para el verifier,
que es un agente llamando `taskops_update status=ready` por MCP — donde el comentario nunca fue
obligatorio. Reproducido: por CLI el comentario queda en el thread; por MCP la card vuelve al
worker con cero findings y el motor la acepta.

El guard se mudó a `engine/machine.py`, que es la única casa de la máquina de estados: `review →
ready` ahora refuta sin texto (y un espacio en blanco no cuenta), en los tres transports. Las
otras flechas a `ready` — `claimed → ready`, `blocked → ready` — siguen sin guard a propósito:
ésas son *me rindo*, y rendirse nunca debe ser más difícil que abandonar.

`Facts` recibe `comment` como campo propio en vez de reusar `justification`. Hoy son el mismo
string en todos los call sites, y siguen siendo dos parámetros: uno es "el razonamiento que
gana un cierre `no_code`", el otro "los hallazgos que un rechazo debe llevar". Pasar uno por el
otro se lee como coincidencia, y el día que alguno crezca una regla propia, la coincidencia es
lo que nadie notaría.

### `parent: 0` se descartaba en silencio, y con eso no había checklists

`after` acepta el índice de una entrada anterior del mismo `plan` — está documentado, porque un
modelo con una dependencia escribe `after: 0` casi tan seguido como `after: [0]`. **`parent` no,
y no protestaba**: `field.optional` devuelve `None` para cualquier cosa que no sea string, así
que un `0` desaparecía y la llamada contestaba `# planned 3 task(s)` sobre un árbol que no
existía. Mismo `plan`, dos campos, dos convenciones, y la que no seguía la convención se callaba.

Ésa es la forma cara de estar mal: el board se lee decomposado, la épica no tiene hijos que
contar, y cierra sobre trabajo que nadie hizo.

- **`parent` acepta índice o id**, igual que `after`. Los ids se **acuñan antes del primer
  insert** — es lo único que lo hace posible: el parent viaja en el evento `created`, y arreglarlo
  en una segunda pasada dejaría el log describiendo un árbol que el board no tiene.
- **Un árbol de tres niveles entra en UNA llamada.** La profundidad no está caseada en ningún
  lado; sale de resolver contra ids que ya existen.
- **Todo error se refuta, nada se descarta**: índice fuera de rango, id que nadie conoce,
  `parent: true` (que por `True == 1` habría adoptado la primera card), y una card que es su
  propio padre — una épica que se contiene a sí misma no cierra nunca, porque siempre es su
  propio subtask abierto.
- `_after.py` es `_refs.py`: el resolvedor es uno solo para los dos campos, que es lo que hace
  imposible reinventar una segunda convención.

### Un hijo no sabía de qué era parte

La otra dirección del árbol no existía. El padre lista a sus hijos desde siempre; **el hijo no
nombraba a nadie** — ni en su card, ni en el brief que escribe `dispatch`, que tampoco menciona
la épica. Un worker adentro de un plan de tres niveles no podía enterarse de para qué era la
cosa que estaba construyendo, y un spec leído sin eso es cómo un subtask se resuelve
correctamente para el problema equivocado.

`TaskView` trae `epic` **resuelto**, no un id: `task.parent` siempre viajó en el payload y es un
hex, que no es algo que nadie pueda leer. Se renderiza primero, arriba de `Waiting on`, en la
card y en la UI.

### `taskops-lead`: el nivel del medio, para que una épica la terminen otros

Ni el worker ni el verifier podían despachar ni spawnear, así que "una card con checklist" no
tenía a quién dársele entera. Hay un cuarto especialista:

```
tu sesión ──▶ taskops-lead   (la épica)
                ├──▶ taskops-worker   (subtask 1)
                ├──▶ taskops-worker   (subtask 2)
                └──▶ taskops-worker   (subtask 3)
```

**El árbol es de tres niveles y no puede ser más profundo**, y eso es una propiedad de las listas
de tools y no una regla que alguien tenga que recordar: el worker no tiene con qué spawnear. El
lead **no tiene `Edit` ni `Write`**, por la misma razón que el orquestador no los tiene: un agente
que puede despachar e implementar termina implementando, y el plan deja de mantenerse justo
cuando el trabajo se pone interesante. El motor lo respalda — una épica no llega a `done` con un
hijo abierto.

### `taskops board create`: empezar un board sin entrar nunca al servidor

Arrancar un board de equipo pedía `ssh` a la caja, `taskops serve init`, copiar un token
minteado de la salida y pegarlo en un chat. Los cuatro pasos son hábitos que nadie quiere:
**nadie hace `ssh github.com` para crear un repo**, y un link con un secreto adentro es un
secreto en el scrollback de todos.

- **`taskops board create`** (comando 22, con `list · view · access`) lee el checkout donde
  estás parado en vez de interrogarte: el repo sale de `origin`, el nombre del repo, el
  servidor de tu login. Crea, linkea, configura el remote, te deja con sesión y migra lo que el
  proyecto ya tenía local — una llamada.
- **La autorización es la misma pregunta que ya hace el login, un paso antes**: *podés crear un
  board para un repo al que ya podés pushear*. No se concede nada que GitHub no hubiera
  concedido primero, y el board queda atado al nacer a algo que demostrablemente controlás.
  El orden importa y hay test: se le pregunta a GitHub **antes** de escribir, así un rechazo no
  deja ni directorio, ni store, ni token minteado.
- **`taskops serve --no-create`** cierra el registro remoto, y `--readonly` ya lo cierra: un
  servidor que rechaza toda escritura no tiene por qué mintear un directorio.
- **`.taskops/board.json`**, commiteado y sin secreto: la dirección del board viaja con el
  clon, así que **`taskops join` no lleva URL**. Es el `.git/config` del board — la credencial
  es una sesión en el home, y el token de máquina sigue en `remote.json`, que el bloque de
  gitignore guarda por nombre. Hay un test de que ese archivo no quede ignorado, porque el
  mecanismo entero descansa en que el bloque liste rutas y no `.taskops/*`.
- **`taskops board access`** responde quién puede entrar imprimiendo los comandos de `gh`.
  **No existe `board access add` y es a propósito**: una lista de usuarios acá sería una copia
  de los colaboradores del repo, y la copia es justo lo que queda vieja el día que alguien
  pierde el acceso.
- `serve init` sigue, para un board **sin** repo de GitHub y para CI. Dejó de ser la puerta de
  entrada, y su salida ahora sugiere linkearlo en vez de terminar en un `?token=`.

**Y el link viaja en `/api/projects`**, porque el cliente no puede saberlo: vive en el
servidor, y un board se liga rutinariamente a un repo que **no** es el `origin` del checkout —
que es exactamente cómo un proyecto alojado fuera de GitHub consigue una lista de accesos de
verdad (un repo vacío que existe sólo para ser el ACL). Leyéndolo del remote local,
`taskops board access` contestaba "not linked to a GitHub repository" sobre un board que sí lo
estaba: en una pregunta sobre quién puede entrar, la peor respuesta equivocada posible.

**Tres bugs que encontraron los tests nuevos, no yo:**

- `join` sin token decidía "¿puedo pullear?" y "¿necesita login?" mirando sólo el token, así que
  un compañero **ya logueado** era mandado a loguearse justo después de haber entrado — y su
  cache quedaba vacía porque el primer pull se salteaba. Lo caza el arnés de topología real.
- El rechazo de `join` sin sesión venía de `add_remote`, cuya frase está escrita para alguien
  configurando un remote a mano: decía "run `taskops login <server-url>`" sin nombrar cuál, y
  la adivinanza obvia — la URL del board recién tipeada — es exactamente la que login rechaza.

`NAME` y `TOKEN_FILE` bajaron a `contracts/hosting.py`, y provisionar un board es
`usecases/provision.py`: vivía en un comando del CLI, y un servidor no puede llamar a eso.

### El default del reviewer se muda: de prosa a una policy validada

0.3.0 puso el default del proyecto adentro de una decisión de contexto
(`taskops context decision "reviewer: taskops-verifier"`). Era el lugar equivocado, y la razón
no es de gusto: **una decisión es prosa para que el modelo la pondere, así que no puede refutar
nada.** Un especialista mal escrito no matcheaba, degradaba a "nadie nombrado", y todas las
cards salían sin reviewer — en silencio, indistinguible de nunca haberlo dicho. Y la primera
vez que alguien siguió la regla de este proyecto de que cada decisión lleve su porqué, escribió
`reviewer: peer — nadie firma lo suyo` y apagó la feature entera, porque la cola se leía como
el nombre.

- **`taskops policy` es el verbo nuevo** (comando 21). `policy reviewer peer` setea,
  `policy reviewer` lee, `policy reviewer none` apaga, `policy show` lista todo. El valor pasa
  por el MISMO validador que el campo de la card, así que un typo se refuta al escribir,
  nombrando los especialistas que el proyecto sí tiene.
- **Es un evento** (`kind: policy`, bajo el centinela `project`), no un archivo de config: viaja
  por `git pull`, tiene id de contenido, guarda su historia, y sobrevive a `rm db.sqlite`. Un
  ajuste que viva sólo en el cache es un ajuste sobre el que dos clones discrepan — hay un test
  de costura que lo camina por el log y un cache reconstruido.
- **`context decision "reviewer: …"` ahora se REFUTA**, nombrando el verbo nuevo. Simplemente
  dejar de leerlo habría sido el mismo silencio otra vez: la frase seguiría grabándose,
  renderizándose y sin hacer nada.
- **Se sigue leyendo al CREAR y estampando en la card.** El guard lee la card, nunca la policy,
  así que cambiarla hoy no reescribe quién podía cerrar lo planificado la semana pasada, ni
  arrastra de vuelta a una card que dijo `--reviewer none`.
- `transports/http/_verbs.py` se partió en la LISTA y sus adaptadores (`_verbargs.py`): estaba
  en el presupuesto de módulo y no entraba un verbo más. Una tabla a la que no se le puede
  agregar una fila dejó de describir la superficie.

### Un verbo que devolvía una lista se perdía entero en el cable

Lo encontró el test de costura del punto anterior, no la suite: `policy_show` funcionaba en un
store y volvía vacío entre dos clones. La causa no estaba en la policy.

`_wirereply.decode` devuelve `{}` para cualquier JSON que **no sea un objeto** — a propósito, un
nginx adelante contesta 502 en HTML y el lector quiere el status, no un traceback del parser. El
costo es que un verbo que contesta un ARRAY pelado se decodifica a nada, sin error en ningún
lado. Tres lo hacían:

- **`search`**: en cualquier board con remote, buscar devolvía cero tasks. Silencioso.
- **`context_history`**: `taskops context log` vacío contra un board remoto.
- **`policy_show`**: recién nacido y ya roto.

Los tres van envueltos en un objeto (`{"tasks": …}`, `{"facts": …}`, `{"policies": …}`) y el
cliente los desenvuelve. La regla está escrita en `_verbs.py` y **pinada**: un test recorre los
verbos de lectura por la puerta real y falla si alguno contesta un array. Las tres instancias
pasaban toda la suite porque todos los tests corrían un store.

## 0.3.0 — un equipo, no una fila: la review se rutea a UNA persona y el trabajo llega al trunk

0.2.0 hizo que dos agentes no pudieran agarrar la misma card. Esta versión hace que dos
**personas** con sus flotas puedan trabajar sin pisarse ni esperarse — incluso en husos
distintos, sin coincidir nunca — y que lo que cierran termine donde alguien lo busca.

Casi todo lo de acá salió de correr el sistema con dos clones y un servidor de verdad, no de
leer el código. Las causas están escritas donde vivían, porque todas vivían en el mismo lugar:
la costura entre dos máquinas.

### Una review es una ASIGNACIÓN, no una noticia

- **El servidor elige al revisor** (`engine/routereview.py`). Cuando una card entra a `review`
  en un board con `reviewer: peer`, el servidor elige UN developer conectado — nunca el autor,
  después el que menos reviews carga, después el de señal más fresca, después alfabético — le
  asigna la card y le manda UN mensaje dirigido. Determinista, así dos clones que preguntan
  "quién revisa X" no pueden discrepar. Antes se anunciaba a todos: dos devs libres empezaban
  la misma review y uno trabajaba al pedo.
- **La presencia viaja en el heartbeat** (`storage/_presence.py`). Cada llamada dice "este dev
  está acá", así nadie tiene que anunciarse y el que deja de llamar deja de recibir ruteo. Un
  dev cuenta como presente cuando alguno de sus actores carga un **id de sesión** — la
  distinción que separa a quien está trabajando de quien corrió un comando y se fue.
- **El ruteo EXPIRA** a la media hora. Es un empujón con fecha, no un candado: una card ruteada
  a alguien que cerró la laptop se reabre sola en vez de morir esperándolo.
- **Y el cierre lo respeta.** Guardaba el claim y dejaba el close abierto — la única puerta que
  decide algo. Un dev cerró una card ruteada a otro sin reclamarla siquiera.

### Una sesión abre sabiendo quién más está en el board

- **El brief de equipo** (`engine/team.py`): quién está conectado y qué card tiene en la mano,
  inyectado ANTES de la lista de trabajo. Junta dos hechos que el store ya tenía y nadie había
  cruzado. Agrupado por DEV, porque una persona y sus agentes son una sola.
- Va antes de "qué está esperando" a propósito: una sesión que lee primero el trabajo pendiente
  ya empezó a elegir.

### Dos maneras de enterarse, un solo hecho

- **`taskops attention --wait`** bloquea hasta que el board te necesita, y despierta también
  por MENSAJES: una review ruteada llega como mensaje, así que un loop que solo mirara cambios
  de estado dormiría justo el evento que alguien eligió para vos.
- **El canal solo lleva lo dirigido a vos**: ni ecos de tu propio dev, ni un id ya entregado, ni
  una audiencia en la que no estás. Los cambios de estado salieron del set por defecto — son
  derivables, y `attention` es donde se leen.
- **El canal recupera lo que se escribió mientras arrancaba** (`/api/sync?after=`), acotado a la
  vida del proceso. Una sesión que abría quince segundos antes de una entrega no se enteraba
  nunca.
- Las dos vías llevan el mismo hecho. Sin canal no hay un modo degradado con reglas propias: es
  el mismo mensaje, leído en vez de empujado.

### El trabajo llega al trunk

- **Aprobar mergea** (`usecases/land.py`): una card que llega a `done` fue leída por alguien que
  no es su autor, que es exactamente cuándo un merge está justificado. Un board había reportado
  118 cards cerradas con `main` en el commit semilla.
- **El trunk se pone al día antes de mergear y el push se verifica después.** Aterrizar es
  concurrente por construcción; sin esto el segundo mergeaba contra un trunk viejo, el push se
  rechazaba y `land` reportaba éxito igual.
- **La rama se trae del remoto**: el que cierra no es el autor, así que su clon nunca la vio.
- **Un conflicto es TRABAJO**, no un fallo: la card cierra igual y el resultado queda en el
  board, donde `attention` lo reporta bajo `LAND` para que un `taskops-fixer` lo resuelva.
- **El servidor nunca mergea.** Tiene estado y no tiene checkout: corría git, fallaba en cada
  paso, y registraba "no main or master branch in this repository" nombrando un repo que no
  existe.

### Reparaciones que costaron una corrida cada una

- `taskops join` reescribía `.gitignore` en cada corrida, así que **todo clon quedaba sucio para
  siempre** y `git switch` rechazaba: ninguna card de ningún clon podía llegar al trunk. Ahora
  responde git (`check-ignore`), y solo cuenta un `.gitignore` DENTRO del repo — un ignore
  global personal no puede hacer que se saltee la regla que guarda un token.
- **Una respuesta por el canal quedaba firmada por otro developer.** `/api/comment` resuelve el
  actor en el servidor, que es correcto para un browser y falso para un canal autenticado. En un
  board con `reviewer: peer` el autor de un mensaje decide quién puede cerrar qué.
- El claim del revisor **sacaba la card de review**, salteando todas las reglas de cierre
  escritas contra una card en review.
- La asignación del ruteo no se soltaba al salir de review, así que una card rebotada quedaba
  invisible para el worker que tenía que arreglarla.

### Cómo se prueba esto

`tests/e2e/test_the_real_topology.py` — un servidor HTTP de verdad en un puerto de verdad, un
origin **bare**, dos clones que corrieron `taskops join`, y una card caminada de plan a trunk.
Doce bugs en tres días y ninguno era de lógica: todos vivían entre dos máquinas, y toda la suite
corría un repo, un proceso, un store. Se le devolvieron ocho mutaciones de bugs reales y caza
las ocho — dos de ellas encontraron agujeros en el arnés mismo antes de eso.

### cada card nombra a su REVIEWER cuando se crea

Quién puede CERRAR una card dejó de ser una regla global y pasó a ser un dato de la card,
elegido al crearla. Un label es pista de ruteo y cualquiera lo edita para buscar; esto es
política, así que es un campo (`reviewer`) y no un label.

- **`reviewer` en `Task`**, settable por `taskops_plan` (`{…, reviewer: "human"}`),
  `taskops tasks add --reviewer` y `taskops tasks edit --reviewer` (`""` lo limpia). Columna
  nueva por el mismo camino que `assignee` — `_LATE_COLUMNS`, así una base vieja la gana sola
  — y viaja en el body del evento `created`, o sea que replica por `git pull` como todo.
- **Validación igual que la del endpoint de assign**: un nombre pelado tiene que ser un agente
  registrado en `.claude/agents/*.md` y si no, 4xx nombrando los que sí existen (un typo sería
  una card que nadie puede cerrar nunca y el board no diría por qué). `human` se acepta tal
  cual — es lo que la gente tipea — y `dev:…` / `agent:…/…` quedan libres.
- **El default del proyecto es una DECISIÓN, no una constante**:
  `taskops context decision "reviewer: taskops-verifier"`. Se lee al CREAR la card y se
  escribe en ella, así cambiar la decisión hoy no reescribe quién podía cerrar lo planificado
  la semana pasada.
- **Enforcement**: reviewer humano (`human` o `dev:…`) → NINGÚN agente cierra la card, con una
  frase que nombra a quien se espera; el `_handed_on` de antes era más débil (un segundo agente
  pasaba). Reviewer agente → la regla de hoy. Sin reviewer → exactamente como antes, con test
  de regresión.

### agentes especialistas por proyecto: el board rutea, la sesión invoca

Un proyecto tiene agentes que solo tienen sentido ahí (el que toca los collectors, el que toca
la UI), y hasta ahora no había dónde declararlos: el plugin trae tres genéricos y punto.
taskops es el REGISTRO y el ROUTER; spawnear sigue siendo del host — no hay subprocesos nuevos
en ningún lado, y MCP sampling no existe en Claude Code, así que un server que invoque algo
está muerto al nacer.

- **`.taskops/agents/*.md`** — commiteados, viajan por git. Mismo formato que `plugin/agents/`
  más dos claves opcionales: `labels: [collectors, etl]` (de qué cards es) y `files: ["src/**"]`
  (su superficie de edición). UN parser para los dos directorios (`usecases/_agentfile.py`), y
  un archivo del repo con el mismo `name` **pisa** al del plugin: un proyecto tiene que poder
  reemplazar el worker de fábrica sin forkear el plugin.
- **Sin yaml.** taskops tiene cero dependencias runtime y no las va a ganar por un header de
  cuatro claves. Se parsea el subset `key: value` / `key: [a, b]` y **se rechaza** todo lo
  demás con una frase que nombra el archivo. Un parser parcial que ADIVINA convierte un typo en
  un registro silenciosamente mal ruteado. Archivo malformado → warning y skip: una sesión
  jamás se cae por un agente con un typo.
- **Materialización en el SessionStart** (`transports/hooks/_materialise.py`): copia los
  especialistas a `.claude/agents/`, que es lo único que Claude Code sabe invocar. Solo se
  sobreescribe y solo se poda lo que lleva el marcador `# generated by taskops from …` — un
  agente escrito a mano ahí NO se toca nunca. Las claves nuestras (`labels`, `files`) se sacan
  de la copia. Corre en el mismo camino rápido que el sweep, sin salirse del presupuesto.
- **Ruteo determinista** en `dispatch`: labels de la card ∩ labels del registro, gana el que
  comparte más, empate por orden alfabético. El brief gana `agent_type: <nombre>` (vacío cuando
  no matchea nada, y ahí el orquestador usa su worker de siempre). Sin `.taskops/agents/`, el
  comportamiento es exactamente el de antes.
- **Enforcement en el CLAIM, no en el prompt.** Un actor `agent:<dev>/<nombre-del-registro>` que
  reclama una card fuera de sus labels es rechazado nombrando LOS DOS sets ("collectors trabaja
  en [etl]; esta card lleva [ui]"). Un binding rol→card que solo se sugiere en un prompt es una
  sugerencia, y un agente que la ignora es indistinguible de uno que nunca la leyó. Un actor
  que no matchea ninguna entrada queda **sin restricción**: el worker ad-hoc de un humano no se
  enjaula porque existan especialistas.
- **Reparación: "assign" tenía dos significados.** `dispatch` asignaba con `set_assignee` (la
  card desaparece para todos los demás) y `capture(assign=…)` dejaba solo una mención (la card
  seguía en el pool y el próximo agente se la llevaba de abajo de la persona a la que se la
  acababan de dar). Ahora los dos pasan por `usecases/_handoff.hand_over`, la mención sigue
  para que el inbox pinguee, y el render dice la verdad: *"only they can claim it"*.
- **Asignar desde el board** (`POST /api/assign`, `GET /api/agents`, `transports/http/assigning.py`):
  el registro existía y las cards se asignaban solas por `dispatch`, pero una persona no podía
  dar una card desde la UI. El endpoint llama a `hand_over` — misma asignación, mismo evento
  `handoff`, misma mención — así que aparece en `/api/live` sin ninguna notificación paralela.
  Un nombre PELADO se mide contra el registro y se rechaza nombrando los que existen (una card
  asignada se le esconde a todos los demás: un typo la deja sin dueño posible y el board no
  dice por qué); un actor id completo (`dev:ana`, `agent:ana/one`) queda libre, igual que el
  fence de claim trata a un actor que no conoce. Reasignar agrega un SEGUNDO handoff, nunca
  edita el primero. En el panel: picker con el registro + la gente vista en el board, y el chip
  del assignee en la card.

### `taskops login`: entrás con tu GitHub y el remote se configura solo

El paso flojo de armar un equipo no era técnico: *"y le emitís un token a cada developer"*.
Alguien mintea un secreto, lo manda por chat, y lo rota a mano cuando una persona se va — o
sea, nunca. El equipo YA está de acuerdo sobre quién lo integra: eso vive en los repos de
GitHub a los que apuntan los proyectos del server. Entonces que pregunte GitHub, no un admin.

- **`taskops login <url>`** (comando VISIBLE, `cli/commands/login.py`): saca el token de
  GitHub de `gh auth token` (timeout 5 s, degrada en silencio) o lo pide con `getpass` — nunca
  con eco, porque un token tipeado en un prompt visible queda en el scrollback y en el
  history. Un `POST /api/auth/github` y devuelve login, proyectos, y **una línea lista para
  pegar por proyecto**: `taskops remote add <url>/<proyecto>`. `--logout` olvida ese server,
  `--show` imprime la sesión (la pantalla de unlock de la UI la pide).
- **El token de GitHub NO se guarda.** Vive en memoria el tiempo de UNA llamada. Lo que se
  persiste es la sesión que emitió el server: alcanza a UN server, expira sola en 7 días, y se
  puede tirar de los dos lados. Ahí está el argumento entero — una `sessions.json` robada
  cuesta un server por una semana; un token de GitHub robado cuesta todos los repos que esa
  persona alcanza, para siempre.
- **`~/.taskops/sessions.json`, 0600, en el HOME y no en un repo** (`usecases/_sessionfile.py`,
  las mismas mecánicas de `_remotefile`: `os.open` con el modo, nunca `write_text` + `chmod`).
  En el home porque un login es de la PERSONA — un developer tiene diez checkouts de tres
  repos — y porque un archivo que nunca entra a un work tree no puede entrar a un commit.
- **`taskops remote add <url>/<proj>` sin `--token`** usa la sesión guardada, matcheando por
  prefijo de URL (lo que se pasa es `<server>/<proyecto>`). Se guarda con prefijo `session:`
  para que la FORMA de lo que hay en disco diga qué clase de secreto es; el prefijo es local y
  muere en el `_request` — al cable va `Bearer <session>` pelado, que es lo que dice el
  contrato. Sin token y sin sesión, el error nombra las DOS salidas.
- **Una sesión vencida se explica.** Un 401 con credencial de sesión dice "la sesión para X
  venció — corré `taskops login X` de nuevo"; con un token de proyecto sigue siendo el 401
  verbatim del server. Un 401 pelado deja al lector adivinando entre red, token y permiso.
- **La sesión no se imprime nunca sin que la pidas.** El login muestra el login de GitHub y
  los proyectos; una terminal es algo que la gente screenshotea. Está testeado, junto con el
  0600, con que el token de GitHub no toca el disco, y con multi-server que no se pisa.
- `_wireclient` se partió: `_wirereply.py` se lleva las tres funciones que leen la respuesta
  (no saben que hay una red, así que se testean desde un literal) y el cliente entró de nuevo
  en el presupuesto de líneas con las rutas de auth adentro.
### el server sabe quién sos por GitHub: nadie más reparte tokens a mano

Un token por proyecto escala para MÁQUINAS y no para personas: sumar a alguien era mandarle un
secreto por un canal cualquiera, y sacarlo era re-mintear para todos. Ahora un proyecto se ata a
su repo de GitHub y **el push access ES el acceso al board** — jp corre `taskops login` y entra a
`/axion/` porque ya tiene push en `cloudacio/Axion`, que es una decisión que Berna ya tomó.

- **El server NO tiene credenciales de GitHub, y ese es el diseño.** El cliente manda SU token
  (el de `gh auth token`); el server pregunta `GET /repos/{owner}/{repo}` **con ese token** y le
  cree: 200 con `permissions.push` es "puede escribir el repo", que es exactamente el grupo que
  debe poder abrir su board. Sin GitHub App, sin secreto de OAuth, sin webhook — no hay nada en
  este disco que alguien pueda robar y usar contra GitHub.
- **El token de GitHub se USA y se DESCARTA.** Nunca se escribe, nunca se loguea, nunca se
  devuelve. Hay un test que lo busca en TODOS los archivos del root después de un login, porque
  "no lo guardamos" es una afirmación que se pudre en silencio.
- **GitHub es la lista de colaboradores y no se copia.** `taskops serve link <proyecto> --github
  owner/repo` escribe una línea; no hay lista de logins, ni equipos, ni roles. Cada una de esas
  sería una segunda copia de algo que GitHub ya sabe, y la copia es la que nadie actualiza el día
  que a alguien le sacan el acceso. Sin flag muestra, `--remove` desata, y **un proyecto sin link
  se comporta igual que siempre: token only**.
- **Rutas nuevas, en el dispatcher RAÍZ** (`transports/http/root.py`, montado por `projects.py`;
  contrato en `docs/exchange.md`): `POST /api/auth/github` → `{login, session, projects}`,
  `GET /api/projects` con `Bearer <session>`, y `GET /` que pasó de ser un 404 a ser la página de
  login — HTML inline, sin bundle y sin dependencias, porque "los boards están en estas URLs" es
  justo lo que necesitás cuando algo anda mal. **No lista NADA sin sesión**: nombrar los boards
  le daría a cualquier visitante la enumeración que el 404 por proyecto existe para negar.
- **La sesión es lo único que deja un login**: `secrets.token_hex(16)` en `<root>/.sessions.json`
  (`0600`), con `{login, projects, created}` y **7 días** de vida — chequeados al leer, podados al
  escribir, así "expiró" es cierto en un server que nadie tocó en un mes. El punto inicial del
  nombre es load-bearing: un proyecto es `[a-z0-9-]`, así que ese archivo no puede colisionar.
- **La sesión se cambia por el token del proyecto EN EL MOUNT**, no adentro de `Policy`: las
  sesiones son una propiedad de un directorio de proyectos, y una policy construida para un board
  no puede conocer un archivo un nivel más arriba. Debajo de esa línea nadie oyó hablar de GitHub.
  El **token del proyecto sigue funcionando solo** — es la credencial de máquina de push/pull/
  agents — y nunca se le echa al browser: el redirect de `/axion` se arma con la query ORIGINAL.
- **Lo que NO alcanza**: `pull`. Leer un repo no es estar en el equipo que lo corre. Un repo que
  la cuenta no puede ver contesta 404 (GitHub negándose a confirmar que existe) y cuenta como "no
  es tuyo", así que el board nunca es un oráculo de existencia. Un **403** no se traga: es un rate
  limit o un token suspendido mucho más seguido que un permiso, así que sale con las palabras
  textuales de GitHub en vez de convertirse en un "no tenés acceso a nada" que confunde.

### claims atómicos en remoto: dos agentes en dos máquinas no agarran la misma card

El miedo central, textual: *"mi miedo es que se pisen agentes en remoto"*. Con push/pull los
boards CONVERGEN, pero el claim seguía siendo local: entre dos syncs, dos agentes en dos
máquinas ven la misma card `ready` y los dos la agarran, cada uno en su propio sqlite. Se
enteran editando los mismos archivos. El engine ya gana esa carrera DENTRO de una base — dos
INSERT sobre una primary key, testeado con 50 threads — así que el arreglo no es un algoritmo
nuevo sino un LUGAR: si el proyecto tiene remoto, `next` y `update` se ejecutan en el sqlite del
server, y la carrera pasa a ser la que el engine ya gana.

- **Dos endpoints nuevos, `transports/http/agentapi.py`** (filas en `router.py`, contrato en
  `docs/exchange.md`): `POST /api/next` → `NextResult`, `POST /api/update` → `UpdateResult`, los
  TypedDicts tal cual — no hay capa de schema, igual que el resto. Son writes, así que
  `--readonly` los rechaza por MÉTODO antes de cualquier handler.
- **La decisión de ruteo vive en los USECASES, no en un transporte.** `next_task` y `update`
  ganan un paso al entrar: si hay `remote.json`, la llamada va por HTTP. Así CLI (`taskops
  claim`, `tasks done`), MCP (`taskops_next`/`taskops_update`) y el board local se comportan
  IGUAL sin tocar ninguno de los tres — un cliente que claimea seguro por una superficie e
  inseguro por otra sería peor que no tener la feature.
- **El `actor` viaja en el body y se ACEPTA — decisión de confianza, documentada, no escondida.**
  Al revés que `POST /api/comment`, que lo resuelve server-side. El server no PUEDE resolverlo:
  no tiene el `$TASKOPS_ACTOR` ni el git config de la otra máquina. El **token del proyecto es la
  frontera de confianza** — quien lo tiene puede actuar como cualquier actor del proyecto, la
  misma frontera que ya dibuja git, donde quien puede pushear puede firmar un commit con
  cualquier nombre. Lo que SÍ se valida es la FORMA: un id malformado es un 400 de
  `engine.identity.parse`, así que un typo no crea una identidad fantasma bajo la que se archiva
  medio trabajo.
- **El server nunca se rutea a sí mismo.** Los endpoints llaman los usecases con `local=True`,
  siempre. Sin eso, un `remote.json` en el store que el server sirve lo haría POSTearse su propio
  claim a esa dirección — a sí mismo, para siempre. Hay un test que planta exactamente ese
  archivo.
- **Todo write remoto pullea antes de contestar, y un pull que falla FALLA la llamada entera.**
  El guard de commits, `brief` y todos los renders leen el board LOCAL: un claim que el server
  otorgó y el board local nunca escuchó es un lease que el propio tooling del agente le niega un
  minuto después. Medio éxito es peor que un error nombrando la red.
  - Los eventos no alcanzan para el lease: `engine.replay` deliberadamente NO materializa
    leases (importar uno sería claimear en nombre de un agente que corre en otra máquina). Por
    eso `usecases/_mirroring.py` escribe exactamente uno y nada más: **el que el server le acaba
    de otorgar a ESTE caller**, que viene en la respuesta. No se infiere del evento de nadie.
- **Offline JAMÁS cae al claim local.** `Unreachable` (502, `unreachable`) nombra la URL y dice
  que no se claimeó local. Ese fallback silencioso ES el pisoteo que la card mata. Leer —
  `board`, `ask`, `report` — sigue andando sin red; solo los dos writes que reparten trabajo
  paran.
- **`tests/e2e/test_agentwire.py`** — contra el server REAL (`build_server`), no contra el fake
  del contrato: la pregunta acá es "¿dos claims caen en UN sqlite y ese sqlite elige uno?", y un
  fake la contestaría con su propia regla inventada. LA prueba: dos proyectos en dos paths, dos
  threads, una barrera, la misma card — un ganador y un `reason` normal. Más: el board del
  ganador sabe que ganó, el guard del server (`done` sin commit) llega verbatim, offline no
  falla al local, el server no se auto-rutea, actor malformado 400, y un server que otorga el
  claim y después no deja leer su log hace fallar la llamada entera.
- **Fuera de scope a propósito**: `plan`, `dispatch` y `ask` siguen locales — `ask` lee un board
  que ya converge por `pull`, y planear en remoto es raro y puede esperar.

### la mitad server del sync remoto: eventos por HTTP, y reportes que no se pisan

- **Cuatro endpoints nuevos, `transports/http/exchange.py`** — la API de intercambio entre dos
  instalaciones de taskops, documentada en `docs/exchange.md` porque el cliente la codea desde
  otro repo y un rename acá lo rompe sin que este repo se entere. Pasan por `usecases/exchange.py`
  (eventos) y `usecases/reportfile.py` (archivos), como todo lo demás: ningún transporte toca
  `storage` ni `engine`.
  - `POST /api/sync` relaya un batch por `engine.log.relay` — **el id NO se recalcula**: el id ES
    el hash del contenido, y recalcularlo bifurca la historia el día que un taskops más nuevo
    serializa un campo distinto. Devuelve `accepted` = cuántos eran NUEVOS, que es la señal de
    idempotencia: el mismo batch dos veces contesta 0 la segunda.
  - `GET /api/sync?after=&limit=` pagina por cursor. **`seq` es LOCAL del server** — por eso
    ningún evento lleva `seq` en el wire: el cliente guarda un cursor POR REMOTO y nunca mezcla
    dos. `max_seq` es el último seq ESCANEADO, no el último devuelto, para que las filas
    filtradas no se re-escaneen para siempre.
  - `LOCAL_ONLY_KINDS` (`activity`) se filtra en LAS DOS direcciones: afuera porque un heartbeat
    por tool-call agrega miles de filas por día a lo único que un humano puede leer; adentro
    porque un server no confía en que el cliente se haya acordado.
  - Batch tope 500, y el batch entero se coerciona ANTES de escribir nada: un evento malformado
    en el índice 40 no deja 39 relayados y al que llamó sin saber hasta dónde llegó. El 400
    nombra el índice.
- **La regla de no-pisarse de los reportes** — lo que motivó la card. Los eventos mergean por
  unión (son hechos del pasado); un reporte no: el dossier es regenerable, la **narración no**.
  `PUT /api/report/file` aplica, en orden: no lo tengo → guardo; idéntico byte a byte → guardo
  (un re-sync es silencioso); **ambos estampados y el entrante MAYOR → guardo** (vio más log);
  cualquier otra cosa → **409 con los dos seqs**. Eso incluye el entrante menor, el igual-pero-
  distinto, y **cualquiera de los dos SIN estampa** — un archivo sin estampa lo escribió o editó
  una persona, que es justo la copia que nadie puede pisar: "cobertura desconocida" no es
  "menos cobertura". `force` pisa, y el mensaje del 409 dice qué se pierde.
  - **El server NUNCA regenera**: `GET` sirve los bytes que tiene y 404ea si no tiene ninguno.
    Regenerar es del dueño del store — devolver un dossier fresco le haría creer al cliente que
    acá hay algo que perder.
  - **El límite está documentado, no escondido**: los `max_seq` de dos máquinas no son
    rigurosamente comparables (cada sqlite numera lo suyo), así que la regla del mayor es una
    heurística de "quién vio más". El caso patológico — dos narraciones independientes del mismo
    día en máquinas que nunca sincronizaron — cae SIEMPRE al 409, que es el resultado honesto.
- **`ReportConflict`** en `_errors.py` (409, `report_conflict`), con `ours`/`theirs` como
  números en el body: el próximo paso del cliente es decidir qué copia sobrevive, y una oración
  que tiene que parsear no es una respuesta.
- **`do_PUT` en el handler** (sin él la stdlib contesta 501 y el 405 de la tabla de rutas nunca
  se alcanza) y `MAX_BODY` de 1 MB a 8 MB: la replicación empuja documentos enteros, y `all.md`
  es un proyecto completo en un archivo.
- **`EventTable.page_after`** devuelve la página y su cursor (`after_seq` ahora la usa, sin SQL
  duplicado), y **`storage.event_from`** sale de `_parse` para que el log commiteado y el POST
  coercionen un evento foráneo con el MISMO código — dos coerciones en dos módulos es cómo los
  dos caminos empezarían a discrepar sobre qué es un evento válido, y con ids de contenido
  discrepar significa bifurcar.
- 24 tests nuevos (`tests/transports/test_exchange.py`), incluidos los cinco casos del PUT.
- **El wire lleva proyecto: la narración de un board ya no se filtra a los demás.** Era el hueco
  que la card de `serve` había dejado escrito: `WIRE` es global al proceso, así que la prosa de un
  digest en /alpha llegaba a TODOS los boards abiertos del server — y una narración nombra las
  estrategias y los datos del proyecto que la escribió. Cerrado en el CONTRATO, no en un transporte.
  - **`WireMessage` gana `root`**: el path absoluto del store que lo emitió. El root y no un
    "nombre de proyecto" — el emisor (una narración adentro de un use case) no sabe ni debe saber
    bajo qué prefijo lo montó un server, y el root es el identificador que las dos puntas ya
    comparten porque las dos lo sacan del mismo `resolve_root`.
  - **El filtro vive en `usecases.feed.follow`**, que ya resuelve su propio root: un mensaje de
    otro root no se yieldea. Con eso NINGÚN transporte necesita saber de proyectos — `live.py`
    enmarca y `projects.py` monta routers enteros, nunca ve un frame suelto.
  - **Un mensaje SIN root se DESCARTA**, decidido y documentado: entregarlo a todos "por
    compatibilidad" con un publicador viejo sería conservar exactamente el bug. El default
    permisivo es el que fuga; el costo del otro es un rato de animación perdida en un upgrade.
  - **El frame no expone el path**: `live._public` saca `root` antes de enmarcar (en las dos
    envolturas, websocket y SSE) — es un path del filesystem del server, y en un server
    multi-proyecto también nombra un board para el que quien mira puede no tener token. Copia,
    nunca mutación: el broadcast le pasa el MISMO dict a todos los suscriptores.
  - 6 tests nuevos: dos stores y dos follows con un publish de A; el mensaje ajeno que llega
    cincuenta veces por segundo y no se cuela; el huérfano sin root; y los bytes del frame, que no
    contienen ni la palabra `root` ni el path.

## 0.2.0 — one door per audience, reports that explain themselves, and a server

- **`taskops serve` — muchos boards en un puerto, cada uno con su token.** `taskops ui` sirve el
  repo donde estás parado; `serve` sirve un DIRECTORIO de proyectos, que es lo que hace falta en
  un host: el board centralizado (el código sigue en git), y los claims atómicos porque compiten
  en UN solo sqlite. Es el objetivo detrás de taskops.bernardocastro.dev; el deploy es otra card.
  - **No es un cuarto transporte, es el mismo montado.** `transports/http/projects.py` parte el
    primer segmento del path, resuelve el proyecto bajo el root del server, y delega en el
    `router.build` que YA existe con el prefijo RECORTADO. Un proyecto es literalmente el board
    de hoy: los endpoints, el SSE y el websocket andan bajo `/<proyecto>/` sin que ninguno se
    entere de que existen los prefijos. `server.py` ganó `serve_route`, así que la mitad socket
    del transporte tampoco tuvo que aprender qué es un proyecto.
  - **`taskops serve init <proyecto>`** crea el directorio, corre el init de taskops adentro
    (`install_git_hooks=False` — un server es un almacén de boards, no un working tree) y mintea
    el token con `secrets.token_hex(16)` a un archivo **0600**, impreso **UNA sola vez**. El
    modelo es el de gist: el token ES la frontera de confianza, no va a git ni a un log, y
    nada lo puede volver a mostrar — uno perdido se re-mintea, no se consulta.
  - **Aislamiento estructural, no chequeado por endpoint.** Un router montado está atado a UN
    root y solo ve paths ya recortados, así que un request que entró por `/axion/` no tiene cómo
    nombrar otro store. El nombre se valida contra `[a-z0-9-]{1,40}` **antes** de construir un
    path: `..`, `/` y el vacío se rechazan como sintaxis, no se atrapan después en un resolve.
  - **Sin confianza ambiente.** Todo pide el token del proyecto, incluidas las LECTURAS; el
    token de A da 401 en B; un proyecto sin archivo `token` no se sirve (rechazado, no abierto);
    y un proyecto inexistente es un 404 pelado que no nombra nada — listar los que sí existen
    sería regalarle a un desconocido el inventario de boards del host.
  - **La trampa del bus, pineada.** El BUS de eventos es global al proceso, así que un write en
    A despierta el `follow` de B — pero lo que B lee después es SU cursor de sqlite, y el
    despertar no rinde nada. Ese es el renglón que hace que un proceso sea seguro para N boards.
    La excepción queda escrita y no escondida: un `WireMessage` (delta de narración) no lleva
    proyecto, así que sí llega a todos los boards abiertos; taparlo pide un campo en el contrato.
  - **La UI se monta bajo un prefijo con UN tag.** `index.html` lleva `<base href="/">` y todo lo
    demás es relativo; el server reescribe ese tag a `/<proyecto>/` al servirlo, y `api.ts` lee
    `document.baseURI`. `location.pathname` no servía: el SPA rutea en el browser, así que en
    `/axion/task/tk-1` el path solo no puede decir dónde termina el mount. `url()` **saca el
    slash inicial** — `new URL("/api/board", base)` tira la base a la basura, así que una ruta
    escrita de la forma obvia andaba perfecto en `taskops ui` y se escapaba del mount en
    `serve`; sacarlo en un lugar y no en once call sites es lo que impide reintroducirlo. El
    websocket se arma con el mismo `url()` en vez de a mano con `location.host`, que era
    justamente la única llamada que se habría comido el prefijo y se habría llevado el feed.
- **`taskops remote` + `push`/`pull`: dos boards convergen en segundos, no en un `git pull`.**
  La mitad CLIENTE del sync remoto. `taskops remote add <url> --token <t>` registra EL servidor
  del proyecto, `taskops push` manda lo local y se trae lo ajeno, `taskops pull` solo trae. El
  camino por git (Part 4b de USAGE) sigue vivo y **no queda deprecado**: es la respuesta correcta
  para un equipo que no quiere operar nada.
  - **Cero dependencias nuevas.** Todo con `urllib.request` (`usecases/_wireclient.py`), timeout
    explícito de 30 s y **sin reintentos**. Un retry sería *seguro* — cada write de acá es
    idempotente — y por eso mismo es mala idea: escondería una red que falla detrás de un comando
    que siempre parece andar. `pyproject` sigue con `dependencies = []`, que es un feature.
  - **El token NUNCA llega a git.** `.taskops/remote.json` se crea con `os.open(..., 0o600)` en
    UN syscall (el `write_text` + `chmod` publica el token a toda la máquina por el ancho de una
    llamada) y `taskops init` agregó `.taskops/remote.json` a su bloque de gitignore. Ojo, esto
    no era gratis: ese bloque lista PATHS, no un wildcard, así que un archivo nuevo bajo
    `.taskops/` nace **trackeado**. Un proyecto inicializado por un taskops viejo gana la línea
    al re-correr `init` (`_UPGRADES`), o actualizar en el lugar quedaba a un `git add .` de un
    leak. `tests/e2e/test_remote.py` lo pinea con un `git check-ignore` de verdad.
  - **Los reportes NO se pisan, y el mensaje lo dice.** El dossier se regenera; la NARRACIÓN se
    escribió una vez, la pagó un modelo o la escribió una persona, y nada la reconstruye. Gana el
    `stamped_seq` mayor; un 409 del server sale a pantalla nombrando **los dos seqs** y las dos
    salidas (`taskops pull` o `push --force`), nunca como "HTTP 409". Dos narraciones
    independientes del mismo dossier caen siempre ahí, que es la respuesta honesta.
  - **`pull` REPLAYEA**, y el test pregunta por el BOARD, no por la fila. Traer eventos sin
    materializarlos ya dejó un board vacío una vez (está contado en el docstring de `replay.py`),
    y la fila estuvo en la base todo el tiempo — así que `test_a_pull_puts_the_card_on_the_board`
    mira lo único que una persona mira.
  - **Se marca exportado SOLO después del 200.** Un push cortado a la mitad re-manda y el server
    acepta cada evento una sola vez (ids content-hash). Al revés, un evento que nunca salió de la
    máquina se vuelve un evento que nadie va a mandar nunca. Hay test con un puerto muerto.
  - **El cursor es del SERVER y se guarda con humildad**: cada sqlite numera lo suyo, así que
    nunca se compara contra un seq local. Si el server olvida el suyo, el GET contesta desde 0 y
    re-importar todo es un no-op, no una reparación.
  - **Offline no es un estado de error**: una línea que nombra la causa y dice que el board local
    sigue siendo tuyo, exit 1, y nada marcado a medias.
  - **El bloque de gitignore se mudó a `usecases/_gitignore.py`**, propio, porque dejó de ser un
    detalle de `init` en el momento en que empezó a custodiar un secreto.
  - **Hueco conocido del contrato**, comentado en la card del server: `GET /api/report/file`
    contesta por UN label, así que el cliente no puede DESCUBRIR un reporte que existe solo en el
    server. `Wire.list_reports` ya pide una lista y **degrada** a los labels locales si el server
    no la sirve, así que el día que la ruta exista el cliente la aprovecha sin cambios.

- **Tres puertas, una por audiencia — y ahora la separación es real.** El proyecto declaraba
  "el CLI es del dev, el MCP es del agente" y era cosmético: `taskops --help` listaba 7
  comandos y escondía 13, y por esa misma puerta entraban cuatro audiencias — el dev, el
  agente, git y Claude Code. `plugin/hooks/hooks.json` invocaba
  `python3 -m taskops.transports.cli.main hook <event>` y `usecases/hooks.py` escribía los git
  hooks contra el mismo módulo. Esconder un comando se lee igual que borrarlo desde afuera y no
  es lo mismo: seguía siendo una puerta al binario del dev, y la superficie del CLI la decidían
  tres lectores a la vez.
  - **Transporte nuevo `transports/hooks/`**, hermano de `cli/` y `mcp/`, con la misma regla y
    el mismo test de arquitectura (delgado, sin `storage` ni `engine`). Siete subcomandos
    planos, nombrados por el EVENTO y no por el verbo interno: `pre-tool-use`, `post-tool-use`,
    `session-start`, `stop`, `commit`, `ingest commit|branch`, `sync`. Nadie lo tipea nunca:
    `taskops init` lo escribe en `.git/hooks/*` y el plugin lo trae en su `hooks.json`. Existe
    por un límite físico, no por gusto — un hook de Claude Code es un `{"type": "command"}` y
    uno de git es un script de shell; los dos EJECUTAN algo, y git no tiene cliente MCP.
  - **Trece comandos BORRADOS del CLI**, sin alias y sin ocultos: `guard`, `hook`, `ingest`,
    `brief`, `inbox`, `track`, `checkout` (cableado) y `next`, `update`, `ask`, `plan`,
    `dispatch`, `log` (del agente — ya los tiene por MCP con mejor contrato). Con ellos se fue
    la maquinaria que los escondía (`_HIDDEN`, `_Unlisted`). `taskops --help` lista 7 y 7 es
    todo lo que hay. `studio` sigue como alias oculto de `ui`: es un rename reciente, no una
    audiencia. Los MÓDULOS de `ask`/`update`/`plan`/`log`/`dispatch` quedan — `taskops tasks
    show|done|release|plan|log` y `taskops run` apuntan a esas mismas funciones, así que
    `tasks done` sigue pasando por el guard idéntico y no hay una segunda puerta a `done`.
  - **Los exit codes NO se movieron**, porque son el contrato: `commit` sale **2** y escribe a
    stderr para DENEGAR (es lo que Claude Code lee como deny y lo que el modelo ve), los
    eventos de hook salen **siempre 0** con la decisión adentro del JSON, y todo falla ABIERTO.
  - **`taskops init` ahora REESCRIBE su propia línea** en vez de contestar "already installed".
    Sin eso, un repo inicializado antes de esta mudanza queda con un hook apuntando a un módulo
    que ya no existe — y como toda línea termina en `|| true`, eso no falla: deja de atar
    commits a cards **en silencio**, y nadie se entera hasta que un board aparece sin commits.
    Lo de arriba del marcador (el hook que puso otro) no se toca.
  - **`tests/e2e/test_hook_wiring.py`**: un repo git de verdad, un `git commit` de verdad, y la
    pregunta que importa — ¿quedó el commit en la card? Es el único test que caza un rename mal
    hecho, porque nada más en el sistema hace ruido cuando el cableado apunta a la nada.

- **La narración se VE escribiéndose.** Apretar Generate en la vista Reports "no hacía nada":
  el `POST /api/report/digest` era una llamada al modelo de varios minutos detrás de un spinner
  mudo, el archivo decía `_pendiente_` todo ese rato, y un navegador que cortaba la conexión se
  llevaba el único feedback que había. Ahora el POST **arranca** el digest en un thread y
  contesta `{"status":"narrating"}` en milisegundos; la prosa viaja por el WebSocket que la
  board ya tiene abierto (`/api/live`, frames `type: "narration"`; `event: narration` en el
  fallback SSE) y el panel la renderiza a medida que llega, con markdown y auto-scroll. Un
  segundo Generate del mismo reporte se rechaza con **409**: dos modelos reescribiendo el mismo
  archivo no es contención, es corrupción.
- **Un delta de narración NO es un evento.** Viaja por un canal efímero nuevo (`engine.WIRE`,
  contrato `contracts.WireMessage`) que no toca la base ni `events.jsonl` — ese archivo va
  committeado y su valor es que un humano lea su diff, cosa que mil fragmentos de prosa
  destruirían. No hay cursor y por lo tanto no hay recuperación: un browser que reconecta se
  perdió lo que pasó, y está bien, porque el **archivo** es la copia durable y el socket sólo la
  ventana. El fan-out (`Broadcast`) es ahora uno solo, compartido con el `EventBus`.
- **El .md crece mientras el modelo escribe.** `digest` volcaba la narración al archivo recién
  al final; un `report all` dejaba `_pendiente_` en disco un cuarto de hora — indistinguible de
  un reporte que nadie narró — y un crash a los catorce minutos lo hacía permanente. Ahora se
  flushea cada ~400 caracteres y en cada frontera de pass, con el mismo `render.narrated` que
  hace la escritura final.

- **El reporte escrito es una BIBLIA de lo que se hizo, no un resumen.** El dossier que se
  imprime en una terminal y el que se escribe a disco eran el mismo texto corto, y el corto
  perdía justo lo que hace falta un mes después: el **spec de cada card** no estaba (así que la
  narración podía describir lo entregado pero jamás compararlo contra lo pedido), de los
  comentarios sobrevivía **sólo el último y truncado a una línea** (que es donde vive el
  razonamiento), y las listas de archivos se cortaban en 4 con `+N more` (que es exactamente el
  dato que uno fue a buscar). Ahora el renderer toma un parámetro `detail: "brief" | "full"` —
  UN renderer, dos densidades, no dos módulos que driftean: `brief` es lo que la terminal
  siempre imprimió (el golden byte-a-byte de `report day` sigue verde), y `full` es lo que
  `--write`/`--digest` ponen en el archivo, con el **Pedido** citado entero, **todos** los
  comentarios atribuidos y completos, y todos los archivos de cada commit.
- **Un proyecto recién planificado ya no reporta silencio.** `report all` sobre cuatro cards
  creadas hoy, con specs, archivos y una cadena de dependencias, contestaba
  `0 closed · 0 in flight · 0 blocked` y tres títulos vacíos: `in_flight` filtraba
  claimed/in_progress/review y `blocked` filtraba blocked, así que **`backlog` y `ready` — o
  sea TODO el trabajo planificado y sin empezar — no pertenecían a ninguna sección**. Es la
  misma clase de bug que un proyecto terminado contestando `tasks list` con silencio: un
  filtro que describe algunos estados y todo lo demás cayéndose por el agujero. Ahora
  `PeriodReport` tiene `opened` (las cards CREADAS en la ventana y todavía abiertas, cada una
  con **a qué espera y a qué bloquea** — el DAG ES el contenido de un día de planificación: sin
  él, "¿qué puedo empezar ahora?" no se contesta) y `waiting` (las abiertas y sin empezar que
  la ventana tocó pero no creó). Cada card abierta cae en EXACTAMENTE una sección. El `full`
  cita también el spec de las cards abiertas, y el encabezado suma `N opened` / `N waiting`
  **sólo cuando no son cero**, para que la línea de resumen deje de decir que no pasó nada sin
  reescribir el encabezado de cada dossier ya commiteado. Y el "no pasó nada" se juzga ahora
  por las SECCIONES y no por `actors` — juzgarlo por actors es justo cómo se escondía el bug:
  cuatro cards creadas son un actor con cuatro tareas, así que el reporte no estaba "vacío",
  simplemente no tenía dónde poner una card `ready`.
- **El prompt de la narración exige exhaustividad.** Pide un párrafo POR CARD que diga qué se
  pidió, qué se entregó (commits, archivos, tamaño del diff), qué se decidió o se descubrió
  (los comentarios) y qué costó (cuánto estuvo tomada, cuántos intentos) — y que **diga cuando
  lo entregado no coincide con lo pedido**, que es la línea más valiosa que un reporte puede
  tener. Estructura fija: lo que necesita un humano, después una sección por área del código,
  después las decisiones y las sorpresas, y al final lo que queda abierto. Explícito en el
  prompt: **el largo no es el problema, la omisión sí** — pero no se inventa nada.
- **Un dossier largo se narra en TAJADAS y se cose, nunca truncado en silencio.** Pasando
  `_chunks.CHUNK_CHARS` (60 000 caracteres, ~15k tokens) el dossier se corta en los bordes de
  card o de día — nunca por el medio de una card — cada tajada se lee con su header, y una
  llamada final ensambla las partes. No es un límite de contexto sino de ATENCIÓN: con más
  entrada que eso, una sola respuesta empieza a colapsar cards en oraciones y la narración se
  vuelve el resumen que venía a reemplazar. El camino largo cuesta N+1 llamadas a propósito:
  recortar el prompt produciría un reporte que se olvida de las cards que quedaron últimas y
  nada en la página lo diría. El timeout de UNA lectura pasó de 240s a 900s: una tajada de
  `report all` sobre axion-v3 (45 cards, 340 KB de dossier) se pasó de 240s y **se tiró el
  digest entero después de veinte minutos** — cinco tajadas buenas perdidas con ella. El
  número estaba dimensionado para el dossier de un día contestado en tres párrafos.

- **La vista `Reports` en el UI — leer un reporte no es trabajo de terminal.** El reporte diario
  es lo único que taskops produce para que lo lea una PERSONA: es largo, es prosa, y hasta hoy
  sólo se veía como ASCII en una terminal, que es la peor superficie posible — nadie scrollea una
  terminal para leer lo que pasó ayer. Ahora es la tercera solapa, al lado de Board y Activity:
  a la izquierda los reportes de `.taskops/reports/` (el más nuevo arriba, con badge `stale +N`
  cuando el día siguió después de escribirlo y `✎` cuando ya tiene narración), a la derecha el
  elegido RENDERIZADO — con la `## Narración` levantada a su propio panel arriba de todo, porque
  en el archivo va última (los hechos primero, la prosa como lectura de ellos) pero en pantalla
  es a lo que viniste. El botón **Generate / Regenerate** corre el mismo `report day --digest`
  desde el browser: tarda ~30s porque es una llamada al modelo, muestra un spinner, y el error
  del server llega VERBATIM (que `claude` no esté instalado o no esté logueado es algo que el
  lector arregla en un minuto, y sólo si se lo dicen). Es una escritura, así que `--readonly` la
  rechaza por método — un board en una pantalla en una sala no puede gastar nada por ser mirado.
  Tres endpoints: `GET /api/reports` (el índice, filas sin cuerpos: treinta dossiers serían un
  megabyte de texto para dibujar treinta etiquetas), `GET /api/report?date=` (ya existía) y
  `POST /api/report/digest`. El listado vive en un `usecases/index.py` nuevo y trata el `label`
  como string OPACO — hoy es una fecha, mañana es un rango (`2026-07-22..2026-07-28`, `all`), y
  lo que lo parseara como día se rompería con el primer reporte semanal; por eso `stale` no se
  contesta para un label que no es un día, en vez de adivinarse. El markdown lo renderiza
  `ui/src/markdown.ts`, escrito a mano y sin dependencia: el bundle viaja DENTRO del wheel, así
  que cada kilobyte lo paga todo `pip install taskops` para siempre — y produce datos, no HTML,
  de modo que nada toca `dangerouslySetInnerHTML` y un reporte no puede inyectar markup por estar
  escrito. Una desviación deliberada de CommonMark: una línea indentada NO es un bloque de código,
  porque la indentación del dossier es la que pone un commit debajo de su card.
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
