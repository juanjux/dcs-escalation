# Realistic CAS — pruebas de motor, v1

Estas misiones NO implementan todavía el plugin. Aíslan comportamientos del motor
para decidir cómo hacerlo sin romper CAS, BAI, JTAC ni el combate terrestre.

## Cómo ejecutar y qué devolver

- Mapa **Iraq**, área de la prueba de Su-25T que ya funcionó. Todo aparece al inicio;
  no hay activaciones tardías ni aparatos Client/Player. Todos los pilotos Average.
- Entra como **Game Master azul o rojo**. Si DCS no ofrece entrar desde misión
  individual sin slot pilotable, crea un servidor multijugador local con la `.miz`
  y selecciona Game Master. Hay un puesto por bando, además de observador CA.
- No tomes control de vehículos ni les des órdenes: modificaría la prueba.
- Tiempo de las tablas = **segundos desde que arranca la instrumentación**, no hora
  del reloj de misión. Puedes acelerar. No hay campañas ni MOOSE ejecutándose.
- Se muestrea cada 10 segundos; las fases entran en la primera muestra posterior
  a su instante previsto (hasta 10 segundos de margen). El log lleva el instante real.
- Captura el resumen al acabar; si ves algo interesante, apunta misión, segundo,
  unidad, acción y blanco. Tras salir, conserva `Saved Games/DCS/Logs/dcs.log`
  antes de la siguiente ejecución: todas las líneas propias empiezan por
  `RCAS_TEST|nombre_de_prueba|`. Basta pasarme el log completo o esas líneas.
- Si `ERR` sube, no interpretes la falta de disparos como resultado: pásame el log.
  Un `ACTION` registra que la llamada no lanzó excepción, **no** que DCS la obedeció.
- `shot`: eventos S_EVENT_SHOT; `gun`: comienzos de ráfaga, si esa versión los publica;
  `hit`: impactos recibidos; `ammo-`: caída de munición. **No son todos el mismo
  contador**: un cañón puede gastar munición sin generar SHOT por proyectil.
- `det=true` es conocimiento nativo, no necesariamente contacto visible ahora ni
  identificación completa. El log separa VISUAL/OPTIC/RADAR, `visible`, `lastTime`,
  `type`, distancia y `lastPos`, junto a posición real, LOS geométrica y AGL real.
- Logging deliberadamente abundante: configuración/entorno y sensores al arrancar;
  estado, vida, posición, velocidad, orientación y radar cada 10 s; inventario
  detallado inicial y tras cambios; cada evento y orden; trayectorias/blanco actual
  de armas mientras DCS las conserve. `WEAPON_GONE` no presume impacto o interceptación.
- Blancos inmortales y sin fuego, y aviones inmortales, salvo donde se indica lo
  contrario. Es deliberado: necesitamos repetir fases sin perder el sujeto.
  **No se borran misiles/bombas en vuelo**. Impactar después de ocultar no demuestra
  por sí solo una adquisición nueva a través de invisibilidad.

## Primera tanda: hacer 00, 01 y 06 antes de gastar tiempo en las demás

### 00_CAS_control — control positivo (hasta 12 min)

Dos Su-25T, 2.000 m AGL iniciales, Kh-29T del payload de prueba que funcionaba;
seis carros visibles, inmortales y sin respuesta. Búsqueda CAS en zona.

**Observa/reporta:** ¿ambos adquieren y disparan? Instante del primer lanzamiento,
altura real y si atacan los dos o solo el líder. Si no atacan en unos 6 minutos,
para las pruebas CAS 01–05 y pásame el log: falta un control válido.

### 01_CAS_hidden — caducidad de visibilidad (12 min)

Mismo escenario, inicialmente oculto a IA. A **180 s** se muestra y se reemite una
vez la misma tarea (también se hace esa reemisión en 00). A **360 s** se vuelve a
ocultar, sin cancelar tareas ni armas. A **540 s** se muestra otra vez sin reemitir.

**Observa/reporta:** ¿hay lanzamientos nuevos antes de 180? ¿ataca al mostrar?
¿después de 360 sigue haciendo pasadas/lanzamientos nuevos sobre carros ocultos?
¿recupera el ataque tras 540? Distingue lanzamiento nuevo de misil ya en vuelo.

### 06_Ground_unit_vs_group — granularidad real (7 min)

Cuatro calles separadas, cada una con un Abrams observador y dos T-72B en el mismo
grupo. Todos inmortales. Los T-72B no disparan. Casos:

1. `CONTROL`: los dos visibles.
2. `GROUP_HIDE`: SetInvisible al grupo.
3. `UNIT1_HIDE`: solo SetInvisible al controlador del primer carro.
4. `GROUP_HIDE_UNIT1_SHOW`: ocultación de grupo seguida de mostrar solo el primero.

Los observadores están en HOLD hasta **60 s**, luego abren fuego. A **240 s** se
manda mostrar a los cuatro grupos (sin órdenes nuevas a los controladores de unidad).
A **330 s** se manda mostrar explícitamente a cada carro.

**Observa/reporta:** cuáles detecta y a cuáles dispara cada Abrams antes/después de
cada fase. Especialmente si ocultar uno afecta al compañero y si una orden de unidad
vence a la de grupo. Si una calle no tiene LOS/tiro ni en la última fase, no vale
como resultado negativo: necesito su log. Los alcances y LOS están registrados.

## Segunda tanda: tareas, memoria y disparos

### 02_AttackGroup_hidden — ¿un ID de grupo elude la ocultación? (12 min)

Como 01, con AttackGroup en lugar de búsqueda CAS. Misma secuencia 180/360/540 s.

**Observa/reporta:** ¿ataca antes de revelar? ¿omite/finaliza la tarea oculta y solo
ataca al reemitir a 180? ¿continúa atacando después de 360? Si solo cambia esto
respecto a 01, tenemos una diferencia del tipo de tarea, no del payload.

### 03_AttackUnit_hidden — blanco concreto (12 min)

Como 02, pero AttackUnit solo sobre `TARGET-1` y con ataque de grupo activado.
Sus cinco vecinos NO reciben tarea directa y se revelan/ocultan con él.

**Observa/reporta:** comportamiento de ocultación y si líder o punta disparan a un
vecino no asignado. Una explosión que daña vecinos no cuenta como selección de otro
blanco; interesa el blanco al que se dirige el ataque.

### 04_EngageUnit_hidden — tarea de oportunidad por ID (12 min)

Misma prueba, EngageUnit y `visible=false` como parámetro de tarea (ese parámetro
no es SetInvisible). Solo `TARGET-1` asignado, sin búsqueda genérica añadida.

**Observa/reporta:** igual que 03 y diferencias de persistencia/reanudación respecto
a AttackUnit. No se ha implementado todavía una lista blanca de campaña.

### 05_knowTarget_hidden — conocimiento forzado (12 min)

Búsqueda CAS como 01. A **~21 s** el controlador de vuelo recibe knowTarget del
primer carro con tipo/distancia conocidos; el grupo sigue invisible hasta 180.

**Observa/reporta:** ¿cambia `det` y/o ataca antes de 180? ¿solo sabe del primero o
tira también a sus vecinos? Esto distingue “lo conoce” de “puede atacarlo”.

### 07_Memory_moving_hidden — posición obsoleta (8 min)

Un Abrams en HOLD observa un camión. A **60 s** congelamos una marca en la posición
observada y lo ocultamos; a **70 s** recibe ruta para alejarse 2,5 km. A **300 s**
se revela. No hay disparos ni retargeting deliberado del observador.

**Observa/reporta:** confirma que el camión realmente se mueve lejos de la marca.
Captura a 50/150/290/330 s si te resulta cómodo; lo importante está en el log:
¿`lastPos` sigue al camión oculto, se congela o desaparece? ¿se actualiza al revelar?
Si el terreno impide verlo incluso al principio, el ensayo no es concluyente.
Este test prueba memoria consultable, **no** imponer coordenadas falsas a un misil.

### 08_Fire_events_hidden_shooters — qué eventos tenemos (7 min)

Tiradores ocultos a IA y blancos visibles e inmortales: M113/ametralladora,
Abrams/cañón, Shilka/AAA, Osa/SAM y M109/artillería (seis tiros a una zona vacía).
Los blancos aéreos son MQ-9 inmortales. Aquí **no revelamos automáticamente al
disparar**: probamos primero si la ocultación impide al propio tirador combatir y
qué eventos genera realmente. TIC no está cargado.

**Observa/reporta:** quién dispara de verdad y quién no; para cada uno, `shot`,
`gun` y `ammo-`. Si ves fuego pero no SHOT, el log sirve para elegir evento/sondeo
alternativo. Un “no disparó” no permite concluir que falte el evento.

## Tercera tanda: sensores y entorno (exploratoria, no cifras de realismo)

### 09_Sensors_day / 10_Sensors_cloud / 11_Sensors_night — 10 min cada una

Mismas posiciones, aviones, sensores y rutas. Solo cambia cielo despejado mediodía,
cielo con preset de nubes/base 1.500 m, o medianoche despejada. No hay SAM.
Todos en HOLD, inmortales, buscando blancos pero sin autorización para disparar.

Siete observadores: Hornet con ATFLIR / Hornet sin pod, F-15C control de radar
aire-aire, A-10C II con Litening, MQ-9 a 2.000/5.000 m y Kiowa a 300 m. Estos son
perfiles de prueba, **no** alturas recomendadas. Vehículos estáticos y un móvil.

**Observa/reporta:** si todos aparecen y vuelan, altura real/nubes encontradas y
cuándo aparece contacto de cada plataforma. Pásame el log: exporta getSensors,
getRadar inicial y detección por VISUAL/OPTIC/RADAR en cada muestra.

Limitaciones deliberadas:

- OPTIC no identifica por sí solo “esta detección fue por canal IR del pod”.
- getRadar no dice GMT/RBM ni orientación de barrido del pod. La presencia de radar
  aire-aire no se convertirá en capacidad terrestre por defecto.
- Distintas velocidades/órbitas implican geometrías distintas; compararemos cada
  plataforma **contra sí misma** entre archivos usando distancias/AGL del log.
- La IA puede compartir información o no explorar sensores como un humano. Los
  filtros de detección son evidencia del motor, no una prueba aislada de física.
- Que la IA detecte/no detecte tras una nube no sustituye tu observación del FLIR
  humano; registramos el comportamiento DCS sin un veto universal IR/nubes.
- La base/preset de nubes no permite conocer aquí cada intersección volumétrica.
- Un contacto a 5.000 m no demuestra identificación humana perfecta a esa altura.

## JTAC y mapa

### 12_FAC_vulnerability — MQ-9 sin privilegios (8 min)

MQ-9 con FAC nativo y dos carros inicialmente ocultos. El dron no es inmortal;
solo está invisible al principio. Carros visibles a **90 s**. Dron visible al
enemigo a **210 s**. Hay un Osa oculto pero activo que puede derribarlo.

**Observa/reporta:** detección de carros al revelar, si el Osa adquiere/dispara al
quitar la protección del dron y si este cae. Si no dispara, log de distancias/LOS.
No se interpreta ausencia de láser como fallo: sin cliente pilotable que pida
servicio, **no estamos validando el protocolo de radio FAC**. Tampoco MOOSE Autolase;
su integración necesita una prueba posterior del adaptador, una vez elegido backend.

### 13_F10_native_and_markers — distinción IA / mapa (5 min)

Seis grupos: normales, ocultos a IA, y `hidden`/`hiddenOnMFD`/`hiddenOnPlanner`
desde generación, en ambos bandos. Marcas de referencia para todos y una marca
solo roja/solo azul. A **120 s** se cambia SetInvisible (no flags del mapa).
A **240 s** se retiran las dos marcas por coalición.

**Observa/reporta:** iconos nativos frente a marcas de texto antes/después de 120;
qué muestra Game Master azul y rojo y, opcionalmente, observador CA azul/rojo.
Esto valida las diferencias y primitivas de marcas. **Game Master puede saltarse
la niebla: no certifica F10 de un piloto ni ocultación por bando en un servidor.**
La matriz completa de FOW/slots humanos queda pendiente y no lleva un falso PASS.

## Plantilla rápida de respuesta

```text
Versión DCS / misión / SP o servidor local / rol CA:
ERR final:
Primer ataque o detección:
Antes de revelar / después de revelar / después de ocultar:
Líder vs punta; blanco seleccionado si se ve:
Incidencias (no aparece, terreno, RTB, etc.):
Captura + dcs.log adjuntos.
```

## Validación fuera del motor y límites de esta entrega

El generador compila con Lua 5.1 cada misión, el script de instrumentación y las
cadenas de triggers que DCS ejecutará posteriormente. Comprueba IDs, AI-only,
puestos Game Master y la integridad ZIP. El arnés de APIs simuladas comprueba fases
y ausencia de errores Lua, **no** el comportamiento de DCS. No se ha ejecutado DCS
automáticamente ni se han modificado settings o guardados de campaña.

El generador y el Lua están en el worktree `codex/realistic-cas-plan`, bajo
`tools/realistic_cas_tests`. La carpeta contiene hashes y parámetros por misión.
No sobrescribe suites existentes; una revisión debe ir a una carpeta nueva.

Después de estos resultados: decidir granularidad/unidad/grupo, renovar/caducar
contactos, integrar FAC/MOOSE/TIC y preparar pruebas del plugin completo, incluyendo
clones de TIC, Whitelist/ControlledTask, FOW por bando, terreno y estrés con mapa grande.
No hace falta medir todos los multiplicadores de balance antes de saber si el motor
respeta nuestra barrera de ocultación.
