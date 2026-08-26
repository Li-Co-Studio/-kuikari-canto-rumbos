# OSC_SPEC.md — direcciones, tipos y puertos

Fuente de verdad de puertos/IPs: `config.json` (raíz del proyecto). Todo
lo que sale de `voz_rumbos.py`/`telar_osc.py` llega primero a TD (:7000,
hub visual + relay) y de ahí se reenvía a Esteban y Carlos.

## Puertos (`config.json` → `targets`)

| Destino | Puerto default | Notas |
|---|---|---|
| `td`      | 7000 | Hub visual + relay. Recibe todo. |
| `ableton` | 7001 | Producer-pal / M4L. |
| `esteban` | 7002 | Resolume. IP pendiente de Hafo (`[IP_ESTEBAN]`). |
| `carlos`  | 7003 | Blender. IP pendiente de Hafo (`[IP_CARLOS]`). |

## Direcciones crudas (emitidas por `voz_rumbos.py` y `telar_osc.py`, reenviadas tal cual por el relay)

| Dirección | Args | Tipo/rango | Origen |
|---|---|---|---|
| `/voz/silaba` | `[idx]` | int, incremental | onset de sílaba detectado |
| `/voz/vocal` | `[vocal, clase, rumbo]` | vocal: str en `{a,e,i,+,u}` · clase: int estable 0-4 por vocal (`CLASE_VOCAL` en `voz_rumbos.py`), o -1 si no se pudo clasificar — insumo crudo para el filtro de formantes de Fase F, no espacial · rumbo: int, canal restaurado en Fase D-bis (2026-08-25, ver `--rumbos`/`DEFAULT_RUMBOS`) — **configurable por montaje, no un mapeo canónico**; el único valor fijo por diseño es ɨ (`+`) = 0 (centro). El paneo espacial real del montaje sigue siendo Fase E (paneo cuadrafónico en Ableton), no este campo | vocal clasificada por formantes |
| `/voz/f0` | `[hz, midi]` | hz: float ≥0 (0 = no sonoro) · midi: float (nota MIDI continua) | tono por frame |
| `/voz/nota` | `[midi_int, vel]` | midi_int: int 0-127 · vel: int 0-127 | nota estable (para MIDI-CV del modular; emitido por consumidores de `voz_rumbos`, no por el script en sí) |
| `/telar/palabra` | `[texto, n_morfemas]` | texto: str · n_morfemas: int | inicio de una palabra segmentada |
| `/telar/morfema` | `[idx, texto, slot, es_direccional]` | idx: int · texto: str · slot: int 1-43 (plantilla wixárika) · es_direccional: 0/1 | cada morfema de la palabra |
| `/telar/direccional` | `[texto]` | str | solo cuando el morfema es direccional |
| `/telar/fin` | `[texto]` | str | fin de la palabra |

## Direcciones derivadas `/rumbos/*` (calculadas por el relay en TD, `THROTTLE_HZ` ≈ 30-60Hz)

| Dirección | Args | Rango | Descripción |
|---|---|---|---|
| `/rumbos/f0_norm` | `[valor]` | float 0-1 | f0 en MIDI 36-84 normalizado, con lag exponencial (~suave, no instantáneo) |
| `/rumbos/energia/1` … `/rumbos/energia/4` | `[valor]` | float 0-1 | actividad del rumbo 1-4; sube con `/voz/vocal` dirigida a ese rumbo, decae con lag |
| `/rumbos/energia/centro` | `[valor]` | float 0-1 | igual, para rumbo 0 (centro) |
| `/rumbos/silaba` | `[0 o 1]` | bang 0→1→0 (~50ms de ancho) | un pulso por cada `/voz/silaba` |
| `/rumbos/fila` | `[fila]` | int | fila actual del telar (incrementa con cada `/telar/palabra`) |

## Paneo cuadrafónico (Fase E, relay → Ableton)

`/paneo/fuente` y `/paneo/manual` llegan al relay como cualquier otro
mensaje del hub (puerto 7000, ver tabla de control abajo). Pero la salida
hacia Ableton **no es una dirección OSC nombrada** — ver "Control real de
Ableton" más abajo, verificado en vivo el 2026-08-09.

| Dirección (entrada al relay) | Args | Rango | Descripción |
|---|---|---|---|
| `/paneo/fuente` | `["C"\|"F"]` | str | selecciona qué gesto mueve el ángulo: C = sílaba (avanza `PANEO_PASO_SILABA_DEG` por onset), F = manual. B (respiración) todavía no existe — no hay señal viva de pausa de respiro, solo el cálculo offline de `analisis_canto.py` |
| `/paneo/manual` | `[angulo]` | float 0-360 | centro manual en modo F; la modulación automática oscila ±`PANEO_F_AMPLITUD_DEG` alrededor |

D (densidad) no se selecciona — corre siempre como base: cada `/voz/silaba` la sube a 1.0, decae exponencialmente (`PANEO_LAG_DENSIDAD`) hacia 0 sin nuevas sílabas. Bocinas en orden horario desde 0°: FL(0°) → FR(90°) → BR(180°) → BL(270°).

### Control real de Ableton — TDAbleton, no OSC nombrado

Probado en vivo (2026-08-09): `TDA_Level`/`TDA_Mapper` **no reciben OSC**
(solo emiten telemetría por `udpsend 127.0.0.1 8888`). El control real es
el Control Surface de TDAbleton (`TDA.py`, remote script), que expone un
shell remoto en el puerto **58888** (no 7001 — `config.json` tenía el
puerto viejo, corregido a `127.0.0.1:58888`):

1. Handshake obligatorio antes de cualquier otro mensaje:
   `/tda/command ["connect", <puerto_respuesta>, "<version>"]`. El
   remote script indexa clientes por `(ip, puerto_origen)` del paquete
   entrante — hay que mandar todo desde el mismo socket/puerto de origen
   (el `oscout_ableton` DAT, que mantiene un socket abierto).
2. `/shell/runCode [codigo_python]` ejecuta Python directo contra `SONG`
   (Live API), sin respuesta OSC. Así se escriben los sends:
   `SONG.tracks[i].mixer_device.sends[j].value = x`.
3. `/shell/requestData [expresion, as_repr, id]` lee cualquier expresión
   Python y responde `/shell/data [id, valor]` — usado para verificar,
   no corre en el ciclo en vivo.

Cada track fuente ya tiene 4 sends (`Send A/B/C/D`, índices 0-3) que
corresponden 1 a 1 con los 4 return tracks creados a mano
(`quad_FL`, `quad_FR`, `quad_BL`, `quad_BR`, en ese orden) — coincide con
el orden `[FL,FR,BL,BR]` que ya usa `calcular_ganancias()`.
`relay_callbacks.py` arma un bloque de Python (`_PANEO_CODIGO`) que
escribe los 4 sends de las tracks en `TRACKS_FUENTE` de una vez — por
ahora solo `[2]` (`3-Canto_RAMON...`): Ramón va independiente del resto
de las tracks, a pedido de Hafo (2026-08-09). Las demás tracks no las
toca este motor todavía,
throttled a `PANEO_THROTTLE_HZ=20` (más bajo que `THROTTLE_HZ` porque
cada envío es un `exec()` dentro de Ableton, no un binding liviano).
Verificado end-to-end: escritura con vector de prueba distinto por
bocina, lectura de vuelta exacta en 2 tracks, reset a 0.0 confirmado.

**Resuelto en Fase D-bis (2026-08-25):** el pendiente de Fase D (arriba)
quedó cerrado. `relay_callbacks.py`, función `calcular_actualizacion()`,
leía `args[1]` de `/voz/vocal` como si fuera rumbo espacial cuando en
realidad era `clase` desde Fase D — funcionaba sin error (mismo rango 0-4)
pero el significado ya no era correcto. Con el rumbo restaurado como
tercer argumento (`args[2]`), ese bloque vuelve a leer el rumbo real; los
canales `/rumbos/energia/*` que consumen Esteban (Resolume) y Carlos
(Blender) vuelven a ser espacialmente correctos. No se tocó nada del motor
de paneo de Fase E (`calcular_ganancias`, `_PANEO_CODIGO`, envío a
TDAbleton) — sigue siendo el paneo real del montaje, independiente de este
canal.

## Filtro de formantes vocal a timbre (Fase F, parte 1 — 2026-08-26)

`relay_callbacks.py` ahora también lee el `vocal` de `/voz/vocal` para
mantener un formante objetivo `(F1, F2)` en `rumbos_estado["formante"]`
(`calcular_actualizacion()`, tabla `FORMANTES_DEFAULT` — espejo de
`DEFAULT_VOWELS` en `voz_rumbos.py` — o `vocales_ramon.json` real si
`cargar_formantes()` lo encuentra junto a `config.json`). Sin vocal
clasificada (`vocal == ""`) se mantiene el último formante, no corta a
silencio. Motor puro, probado sin TD/Ableton (ver
`test_relay_callbacks.py`).

**Parte 2 resuelta (2026-08-26):** EQ Eight agregado a mano por MCP en
`1-Vital`/`2-Vital` (índice 1 de la cadena, después de Vital), bandas 1 y
2 puestas en modo Bell, índices reales de parámetro confirmados con
`get_device_parameters` (`FORMANTE_DEVICE_INDEX = 1`,
`FORMANTE_PARAM_FREQ = {1: (6, 11), 2: (16, 21)}` — banda 1/2, canal A/B).
El parámetro Frequency de EQ Eight es 0.0-1.0, no Hz — la curva se
calibró en vivo contra el dispositivo real (10Hz/469Hz/22000Hz en
t=0.0/0.5/1.0, ver `hz_a_normalizado()` y `docs/BITACORA_SETUP.md`) en
vez de asumir una fórmula de memoria. Ganancia de las dos bandas sigue en
0dB (a propósito, sin efecto audible todavía) — afinar Ganancia/Resonancia
por oído queda para Hafo/Ramón, no es una decisión técnica.

**Parte 3 resuelta (2026-08-26):** disparo real conectado — `TouchDesigner_patch/scripts/relay_callbacks.py`
retransferido al `/project1/relay/callbacks` en vivo de TD (estaba
desincronizado del archivo), `inicializar()` corrido, `ableton_activo`
confirmado `True`. Verificado end-to-end **sin ninguna escritura manual**:
`voz_rumbos.py --file <clip> --osc 127.0.0.1:7000` con dos vocales
(sintéticas, de una sola vocal sostenida, para tener un punto de lectura
inequívoco) movió solo el EQ Eight real vía OSC → TD → relay → Ableton —
'a' (F1=700Hz/F2=1300Hz) y ɨ (F1=350Hz/F2=1500Hz), los dos leídos en
pantalla exactos. La cadena probada es la misma que usaría el canto real
de Ramón; solo cambia la fuente de audio (ver `docs/BITACORA_SETUP.md`
para el detalle y por qué no se usó el canto real para este punto de
prueba específico).

## Nota para Resolume (Esteban)

1. Preferences → OSC → activar **OSC Input**, puerto **7002** (o el que
   quede en `config.json`).
2. Usar **OSC Learn** en el parámetro de clip/efecto que quieras mapear,
   y mandar mensajes reales desde el relay (o con un editor OSC de
   prueba) apuntando a `/rumbos/f0_norm`, `/rumbos/energia/*`, etc. —
   todos son floats continuos 0-1, ideales para mapeo directo.
3. `/rumbos/silaba` sirve como trigger de bang para efectos on-beat.

## Nota para Blender (Carlos)

Blender no trae receptor OSC nativo. Snippet mínimo (socket UDP + parseo
manual, sin dependencias — usar como punto de partida, correrlo como
script/handler dentro de Blender escuchando `:7003`):

```python
import socket
import struct

def _parse_osc(datos):
    def _leer_str(b, i):
        fin = b.index(b'\x00', i)
        s = b[i:fin].decode('utf-8')
        i = (fin + 4) & ~3  # padding a múltiplo de 4
        return s, i

    direccion, i = _leer_str(datos, 0)
    tipos, i = _leer_str(datos, i)
    args = []
    for t in tipos[1:]:  # tipos[0] es ','
        if t == 'f':
            args.append(struct.unpack_from('>f', datos, i)[0]); i += 4
        elif t == 'i':
            args.append(struct.unpack_from('>i', datos, i)[0]); i += 4
        elif t == 's':
            s, i = _leer_str(datos, i)
            args.append(s)
    return direccion, args


def escuchar(puerto=7003, callback=None):
    """callback(direccion, args) por cada mensaje. Correr en un modal
    operator o timer de Blender (bloquea si se llama directo)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', puerto))
    sock.setblocking(False)
    while True:
        try:
            datos, _addr = sock.recvfrom(4096)
        except BlockingIOError:
            continue
        direccion, args = _parse_osc(datos)
        if callback:
            callback(direccion, args)
```

Alternativa: instalar `python-osc` en el Python embebido de Blender y usar
`pythonosc.dispatcher`/`osc_server` — más robusto si Blender lo permite en
tu setup, pero el snippet de arriba no depende de instalar nada.
