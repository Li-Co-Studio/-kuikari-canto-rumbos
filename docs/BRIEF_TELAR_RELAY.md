# BRIEF — Telar unificado + relay OSC (Esteban / Carlos)
## Para Claude Code · F:\lico\canto-rumbos · jul 2026

Lee TODO antes de ejecutar. Trabaja fase por fase con verificación. Al final,
actualiza docs\BITACORA_SETUP.md (sección nueva, misma tersura que la anterior).

## PRINCIPIO DE ARQUITECTURA (decisión de Hafo — no la discutas, impleméntala)

**Una sola entrada: audio en vivo.** La app analiza SIEMPRE lo que entra por la
interfaz de audio. Las grabaciones se reproducen (Ableton u otro reproductor)
ruteadas hacia una entrada, y la app las trata igual que una voz en vivo.
No hay modo de sincronización, no hay cuenta regresiva. `tocar_csv.py` se queda
como utilidad menor (reproducir análisis viejos), NO es parte del flujo principal.

**TD es el hub visual y el relay.** Recibe todo el OSC en :7000, dibuja las
chaquiras, y re-emite los mismos canales + canales derivados hacia las
computadoras de Esteban (Resolume) y Carlos (Blender).

## REGLAS (mismas de siempre)
F: únicamente · cmd, nunca PowerShell · conda lico-studio (py3.10) · CPU, sin
CUDA · Gradio 3.50.2 intacto · nunca inventar wixárika · nunca ASR sobre voz
wixárika · autoridad del material: Ramón. El patch de TD vive en
`F:\lico\canto-rumbos\TouchDesigner_patch\` (ya tiene los OSC In CHOP básicos).
Para trabajar el patch usa el **TouchDesigner MCP** del harness; si no está
disponible o falla, NO improvises: genera los scripts de callbacks como
archivos .py en `TouchDesigner_patch\scripts\` + un paso-a-paso en
`TouchDesigner_patch\MONTAJE.md` para que Hafo los pegue en TD a mano.

## FASE 1 — Config central de destinos
Crear `F:\lico\canto-rumbos\config.json`:
```json
{
  "targets": {
    "td":      "127.0.0.1:7000",
    "ableton": "127.0.0.1:7001",
    "esteban": "[IP_ESTEBAN]:7002",
    "carlos":  "[IP_CARLOS]:7003"
  },
  "audio": { "device_in": null, "live_hop_ms": 120 }
}
```
Los placeholders [IP_*] se quedan así hasta que Hafo los dé (pregúntale, no
inventes IPs). Crear `src\osc_targets.py`: carga config, expone
`clientes(nombres)` → lista de SimpleUDPClient; ignora targets con placeholder
sin resolver (con warning, sin crashear).

## FASE 2 — voz_rumbos.py v2 (sin romper el CLI existente)
1. `--list-devices`: lista entradas de audio (sounddevice) con índice.
2. `--device N`: selecciona entrada (default: config audio.device_in o el
   default del sistema). Esto es lo que permite "grabación = mic": Hafo rutea
   Ableton a una entrada del Apollo (o loopback) y elige ese device.
3. `--targets td,esteban` (nombres del config) además del `--osc host:port`
   actual; si se dan ambos, se suman. Default en modo --live: target `td`.
4. Bajar latencia del modo vivo: procesar con ventana deslizante y hop de
   ~config.live_hop_ms (hoy analiza chunks de 0.5 s cada 0.25 s — apretarlo),
   manteniendo pyin estable (ventana de análisis puede seguir siendo mayor que
   el hop). Medir y reportar latencia estimada evento-a-OSC en la bitácora.
5. Sigue sin grabar nada en modo vivo. Ese principio no se toca.

## FASE 3 — telar_osc.py: mismo soporte de --targets.

## FASE 4 — Patch de TD: visual de chaquiras
En el .toe de `TouchDesigner_patch\` (vía TD MCP, o scripts+MONTAJE.md):
1. Container `/telar_visual`:
   - Table DAT `cuentas` (tx, ty, r, g, b, scale).
   - Callbacks del OSC In DAT existente: implementar onReceiveOSC según el
     código ya acordado con Hafo (está en la conversación de claude.ai; copia
     exacta abajo). /telar/palabra incrementa fila; /telar/morfema agrega
     cuenta (x = (slot-22)*0.08, y = 1.2 - fila*0.16; direccional = oro
     0.72,0.55,0.12 escala 1.4; normal = hueso 0.92,0.89,0.82 escala 1.0).
   - Para /voz/*: cada /voz/silaba agrega cuenta a la fila activa usando como
     x un contador de sílaba dentro de la fila; /voz/vocal colorea la última
     cuenta según vocal (paleta: a,e,i,u en cuatro tonos tierra; + en oro).
     Nueva fila cada silencio largo (sin /voz/f0 > 2 s) — usar un Timer CHOP
     o lógica en callbacks.
   - DAT to CHOP → Geo COMP con instancing (Circle/Sphere SOP), translate
     tx/ty, color r/g/b, scale. Render ortográfico, fondo negro.
   - Botón/pulse "limpiar telar" que vacía `cuentas` y resetea contadores.
2. NO sobrescribas nada que Hafo ya tenga en el patch: agrega containers.

## FASE 5 — Patch de TD: relay OSC hacia Esteban y Carlos
Container `/relay`:
1. Passthrough: TODO mensaje recibido en :7000 (/voz/* y /telar/*) se reenvía
   tal cual a esteban y carlos (OSC Out DAT por destino; IP:puerto leídos de
   config.json — puede leerse con un DAT/script al arrancar, no hardcodear).
2. Canales derivados, suavizados, bajo namespace `/rumbos/*` (para mapeo fácil
   en Resolume, que prefiere floats continuos 0-1):
   - `/rumbos/f0_norm` [0-1]  (f0 en midi 36-84 → 0-1, con lag ~0.1 s)
   - `/rumbos/energia/1..4` y `/rumbos/energia/centro` [0-1] — actividad por
     rumbo: sube con cada /voz/vocal dirigida a ese rumbo, decae con lag.
   - `/rumbos/silaba` [bang 0→1→0]
   - `/rumbos/fila` [int] — fila actual del telar
   Implementar con CHOPs (Lag, Trigger, Math) y un OSC Out CHOP por destino.
3. Frecuencia de envío del relay CHOP: ~30-60 Hz máximo.

## FASE 6 — Spec para Esteban y Carlos
`docs\OSC_SPEC.md`: tabla completa de direcciones (crudas y /rumbos/*), tipos,
rangos, puertos (esteban :7002, carlos :7003 — ajustables en config.json), y:
- Nota Resolume: activar OSC Input en Preferences, puerto 7002, mapear
  /rumbos/* por OSC learn a parámetros de clips/efectos.
- Nota Blender: no trae OSC nativo — incluir en el spec un snippet receptor
  Python (socket UDP + parseo OSC simple o python-osc) listo para correr como
  script/handler en Blender, escuchando :7003 y escribiendo a propiedades de
  objetos. Marcar como punto de partida para Carlos.

## FASE 7 — Pruebas de humo (reportar las 4)
1. `telar_osc.py --demo --targets td` → chaquiras de "pakamie" visibles en el
   render de /telar_visual (pide a Hafo confirmación visual).
2. `voz_rumbos.py --live` con mic → cuentas apareciendo por sílaba + canales
   /rumbos/* moviéndose (verificar con listener propio en 7002 simulando a
   Esteban, ya que su compu no está en la LAN todavía).
3. Grabación-como-mic: Hafo reproduce Canto_RAMON0xmodular-02.wav ruteado a
   una entrada, `--device` apuntando ahí → mismo comportamiento que el vivo.
   (Si el ruteo Apollo no está disponible en esta sesión, deja documentado en
   MONTAJE.md el procedimiento y márcalo pendiente de hardware.)
4. Relay passthrough: listener en 7002 recibe copia exacta de /telar/* y
   /voz/*.

## FASE 8 — Bitácora
Actualiza docs\BITACORA_SETUP.md: qué se hizo, latencia medida, qué quedó
pendiente (IPs reales, prueba en LAN con Esteban/Carlos, ruteo Apollo), y los
3 siguientes pasos.

## Código de referencia para los callbacks (Fase 4) — copiar tal cual como base
```python
def onReceiveOSC(dat, rowIndex, message, bytes, timeStamp, address, args, peer):
    t = op('cuentas')
    if address == '/telar/palabra':
        me.store('fila', me.fetch('fila', 0) + 1)
        me.store('col', 0)
    elif address == '/telar/morfema':
        idx, texto, slot, es_dir = args[0], args[1], args[2], args[3]
        fila = me.fetch('fila', 0)
        x = (slot - 22) * 0.08
        y = 1.2 - fila * 0.16
        if es_dir:
            t.appendRow([x, y, 0.72, 0.55, 0.12, 1.4])
        else:
            t.appendRow([x, y, 0.92, 0.89, 0.82, 1.0])
    elif address == '/voz/silaba':
        fila = me.fetch('fila', 0)
        col = me.fetch('col', 0) + 1
        me.store('col', col)
        x = (col - 22) * 0.08
        y = 1.2 - fila * 0.16
        t.appendRow([x, y, 0.85, 0.82, 0.75, 1.0])   # /voz/vocal recolorea después
    return
```
(La lógica de recoloreo por vocal, el corte de fila por silencio y el namespace
/rumbos/* los desarrollas tú siguiendo las Fases 4-5.)
