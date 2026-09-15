# Realistic CAS — segunda tanda

Tres preguntas, once archivos de control/variante. **Empieza por 20, 21 y 22.**
Los demás pueden esperar al resultado de ese bloque. No hay pruebas nuevas de F10,
sensores, nubes ni JTAC, y no se ha cambiado ninguna misión de la primera tanda.

Todas en Iraq, al mediodía, AI Average, sin Player/Client, con Game Master azul/rojo.
Si hace falta, cargarlas en un servidor local para elegir ese puesto. No conducir
vehículos ni darles órdenes. Todos inmortales; blancos en HOLD. La cámara/F10 no
oculta modelos: comprobamos solo comportamiento de IA.

Controles y variantes de cada bloque tienen la misma geometría, composición y carga.
No uses los controles de la primera tanda como sustituto: aquí no se reemite una
tarea aérea a los 180 s. No se intenta forzar un PASS: FIN significa medición
completada, **no** hipótesis confirmada. INVALID requiere corregir el ensayo.

## 20–22: ocultación por unidad o grupo

Un Abrams rojo mirando hacia dos blancos azules del MISMO grupo: **BLANCOS-1 es
T-72B; BLANCOS-2 es un camión Ural**. Distancia de unos 500 m, composición igual en
los tres archivos. Pantalla: nombre, modelo, detected, visible, LOS e impactos.

| Archivo | Única diferencia experimental |
| --- | --- |
| 20_scope_control | Ambos siguen visibles; no se manda SetInvisible durante la medición. |
| 21_scope_unit | Se oculta solo BLANCOS-1 mediante su controlador de unidad. |
| 22_scope_group | Se oculta el grupo entero. |

La prueba espera **10 segundos consecutivos** de ambos blancos detectados y visibles,
con LOS. Si no lo logra en 240 s: INVALID. Quince segundos después de adquirir,
aplica la diferencia. Tras otros 30 s abre fuego el Abrams usando
`AI.Option.Ground.val.ROE.OPEN_FIRE`, cuyo valor real queda en el log.

A los 180 s desde el cambio se muestra otra vez usando el MISMO controlador que
ocultó; 120 s después termina. Duración típica 6–8 min, máximo unos 10 min.

**Reportar:** ¿el Abrams detecta/ve/dispara al tanque, al camión, a ambos o a ninguno
durante cada fase? ¿21 afecta también al camión? ¿recupera la visión y el ataque al
restaurar? Si 20 no dispara, no interpretar el silencio de 21/22 como éxito.

El conocimiento previo puede persistir: `det=true` pero `visible=false` no es lo
mismo que contacto visible. Precisamente medimos qué hace con un blanco ya conocido.

## 23–24: memoria después de adquirir

Abrams observador en HOLD y camión a 500 m. Misma geometría en ambos archivos.

| Archivo | Diferencia |
| --- | --- |
| 23_memory_control | El camión se mueve y sigue visible. |
| 24_memory_hidden | Se oculta antes de iniciar la misma ruta. |

No empieza hasta adquirir durante 10 s estables con LOS. Quince segundos después
congela una marca **creada por el SCRIPT** en la posición inicial; diez segundos
más tarde ordena un movimiento lateral de 250 m, a 5 m/s. A +180 s desde el cambio
se revela y a +260 s termina. Duración típica 6–8 min.

En pantalla: posición real, `lastPos` NATIVA, `lastTime`, desplazamiento, contacto y
LOS. Un `nil` es ausencia de dato, no error. Se invalida si no adquiere, si no se
mueve al menos 40 m en 120 s desde la orden o si pierde LOS durante el movimiento.

**Reportar:** ¿23 actualiza su posición? ¿en 24 lastPos se congela, desaparece o sigue
al camión? ¿se actualiza al revelar? Captura durante movimiento oculto y al final.
La marca fija no prueba memoria nativa; son dos cosas distintas.

## 25–30: ataques, revocación y ocultación permanente

Dos Su-25T, dos Kh-29T cada uno (cuatro en total), seis carros inmortales. Inicial/ruta
a 2.000 m AGL; la órbita usa 2.200 m MSL. Altitud real registrada, no supuesto exacto.
Ninguna fase reemite/cancela tareas ni borra armas en vuelo.

| Archivo | Tarea / variante |
| --- | --- |
| 25_CAS_control | Búsqueda CAS, todos visibles siempre. |
| 26_CAS_revoke | Misma CAS; ocultar grupo después del primer Kh-29T. |
| 27_CAS_always_hidden | Misma CAS; grupo oculto desde el inicio, nunca se revela. |
| 28_AttackUnit_control | Ataque directo solo a BLANCOS-1, siempre visible. |
| 29_AttackUnit_revoke | Misma tarea directa; ocultar grupo después del primer Kh-29T. |
| 30_AttackUnit_always_hidden | Misma tarea directa, grupo siempre oculto. |

Control/revoke: al primer lanzamiento se comprueba en la siguiente evaluación
(hasta ~1 s después) que quede al menos un Kh-29T. Si no queda, INVALID. En el
control se cambia solo la etiqueta; en revoke se manda ocultar. Se observan 240 s,
se restaura visibilidad y se observan otros 180 s. Si no hay primer lanzamiento en
480 s, INVALID. Duración habitual unos 11 min; límite máximo 15 min.

Siempre ocultos: observar 720 s completos, **sin desvelar a los 180 s**. Si se
registra un Kh-29T termina como RESULTADO: LANZÓ CONTRA OCULTO. Si no dispara,
comparar con su control antes de sacar conclusiones.

**Reportar:** si el control hace un segundo lanzamiento; si la variante hace tiros
NUEVOS durante la ventana oculta; si reanuda al mostrar. Pantalla registra munición,
primer tiro, tiros antes/después del cambio y el total de la ventana experimental.
Después de restaurar, el contador de ventana queda congelado; el total sigue.

Un impacto posterior puede ser del misil ya lanzado: **no cuenta como ataque nuevo**.
Dos lanzamientos casi simultáneos antes de la orden se clasifican como anteriores
al cambio; el log da los instantes exactos. No interpretes solo la animación de pasada.

## Logging y respuesta

- Todo con prefijo `RCAS_TEST|nombre_mision|` en `Saved Games/DCS/Logs/dcs.log`.
- Decisiones cada 1 s; pantalla y estado detallado cada 5 s; eventos en su instante.
- Retornos crudos de detección con índice y tipo, además de etiquetas corregidas:
  detected, visible, knowType, knowDistance, lastTime, lastPos, lastVel.
- Fases, enums ROE, posiciones, AGL, munición detallada, disparos, daño y armas en vuelo.
- `ERR>0` invalida la interpretación: pásame el log. FIN no garantiza éxito del diseño.
- Respuesta mínima: **número, estado final, quién dispara a quién en cada fase**, con
  captura. El log permite recuperar el resto. No reiniciar DCS antes de conservarlo.

No hace falta probar los once de una sentada. Si falla el control de un bloque,
para ese bloque. Estas misiones pasan comprobaciones fuera de DCS; sus resultados
in-engine siguen pendientes.
