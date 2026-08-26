# MONTAJE.md — pegar a mano en TouchDesigner

**ACTUALIZACIÓN 2026-07-07 (tarde): ya aplicado en vivo.** Con el TD MCP
disponible (puerto 9981 activo), todo lo de abajo se ejecutó directamente
sobre `canto_rumbos.toe` en esta sesión — no hace falta pegarlo a mano.
Ver el detalle exacto (rutas reales, ajustes hechos, verificación) en la
sección "Fases 4/5 aplicadas en vivo" de `docs\BITACORA_SETUP.md`. Esta
guía queda como referencia de qué se construyó y por qué, y por si algo
se borra y hay que rehacerlo. Diferencia principal con lo escrito abajo:
todo vive bajo `/project1/telar_visual` y `/project1/relay` (no en la
raíz), porque el patch real ya tenía un container `/project1`; y en vez
de un DAT dispatcher nuevo, el dispatcher se escribió directamente en el
`/project1/oscin2_callbacks` que ya existía (estaba vacío, solo el stub
default).

---

Esta sesión no tuvo acceso al TD MCP (TD no estaba corriendo — puerto 9981
sin responder), así que en vez de editar el `.toe` directamente, esto queda
como guía paso a paso para pegar los scripts en tu patch. No se toca nada
que ya tengas armado (OSC In CHOP básicos) — solo se agregan containers.

## `/telar_visual` (Fase 4 — visual de chaquiras)

1. Crea un Container COMP `/telar_visual` (o donde prefieras colgarlo).
2. Adentro, crea una **Table DAT** llamada `cuentas` con encabezado:
   `tx, ty, r, g, b, scale` (una fila de encabezado, sin datos).
3. Crea un **Text DAT** llamado `callbacks` en `/telar_visual` (ruta final
   `/telar_visual/callbacks`) y pega ahí el contenido completo de
   `scripts/telar_visual_callbacks.py`. **No lo asignes todavía** como
   Callbacks DAT del OSC In — eso se hace una sola vez en el paso del
   dispatcher (ver sección Fase 5 abajo), porque el mismo OSC In alimenta
   tanto el visual como el relay.
4. **Corte de fila por silencio**: agrega un **Timer CHOP** (o un
   **Execute DAT** con `onFrameStart` habilitado, ~cada 0.5s) que llame:
   ```python
   op('/telar_visual/callbacks').module.verificar_silencio()
   ```
5. **Render**: `cuentas` (DAT) → **DAT to CHOP** → usa `tx/ty` como
   `translate`, `r/g/b` como color, `scale` como escala uniforme →
   **Geo COMP** con **Instancing** activado apuntando a esas columnas,
   geometría base un **Circle SOP** o **Sphere SOP** (una "chaquira").
   Cámara ortográfica, fondo negro.
6. **Botón "limpiar telar"**: un Button COMP / Panel cuyo callback (o un
   Execute DAT en su `onOffToOn`) llame:
   ```python
   op('/telar_visual/callbacks').module.limpiar()
   ```

Paleta de vocales y colores de morfema están como constantes al inicio de
`telar_visual_callbacks.py` (`PALETA_VOCAL`, `COLOR_NORMAL`,
`COLOR_DIRECCIONAL`) — ajústalos ahí si Ramón/Hafo prefieren otros tonos.

## `/relay` (Fase 5 — reenvío + derivados hacia Esteban y Carlos)

1. Crea un Container COMP `/relay`.
2. Adentro, crea dos **OSC Out DAT** nativos (sin instalar nada):
   `/relay/oscout_esteban` y `/relay/oscout_carlos`. Déjalos con
   cualquier IP/puerto por ahora — se configuran solos leyendo
   `config.json` (ver paso 4).
3. Crea un **Text DAT** `/relay/callbacks` y pega ahí el contenido
   completo de `scripts/relay_callbacks.py`.
4. **Dispatcher único**: crea un **Text DAT** en la raíz (o donde
   prefieras), pega `scripts/dispatcher_callbacks.py`, y **este sí** es
   el que va en el parámetro **Callbacks DAT** de tu OSC In DAT existente
   (puerto 7000). Reenvía cada mensaje a `/telar_visual/callbacks` y a
   `/relay/callbacks` sin duplicar el bind del puerto UDP.
5. **Inicialización**: corre una vez (al abrir el proyecto, o con un
   botón "recargar config") `op('/relay/callbacks').module.inicializar()`
   — lee `config.json`, configura netaddress/port de los dos OSC Out DAT,
   y desactiva el reenvío a los destinos que sigan con placeholder
   (`[IP_ESTEBAN]` / `[IP_CARLOS]`) sin resolver. Un botón "recargar
   config" que vuelva a llamar `inicializar()` es útil una vez que Hafo
   tenga las IPs reales — no hace falta reabrir TD.
6. **Tick de derivados**: agrega un **Execute DAT** con `onFrameStart`
   habilitado que llame `op('/relay/callbacks').module.tick()` — envía
   `/rumbos/*` con throttle interno (~45Hz, ver `THROTTLE_HZ` en el
   script) y apaga el bang de `/rumbos/silaba`.

**Alternativa nativa (si prefieres CHOPs en vez de la lógica en Python):**
los mismos `/rumbos/f0_norm`, `/rumbos/energia/*` se pueden armar con un
OSC In CHOP → **Lag CHOP** (suavizado) → **Math CHOP** (rango 0-1) →
**OSC Out CHOP** por destino; `/rumbos/silaba` con un **Trigger CHOP**
disparado por el mismo onset. El script en Python (`relay_callbacks.py`)
es más fácil de probar sin abrir TD, que es lo que se hizo en esta
sesión — pero ambas vías cumplen el mismo contrato de `docs/OSC_SPEC.md`.

## Pendiente de tu lado

- Confirmar visualmente que las chaquiras aparecen al correr
  `python src\telar_osc.py --demo --targets td` y `python src\voz_rumbos.py
  --live` (el protocolo OSC ya está verificado con un listener propio, ver
  bitácora — falta la confirmación visual real en tu patch).
- Decidir si el corte de fila por silencio (Timer CHOP) usa 0.5s de
  chequeo o prefieres otro intervalo.
- Dar las IPs reales de Esteban y Carlos para completar `config.json` y
  llamar `inicializar()` de nuevo (o el botón "recargar config").
- Confirmar que `/relay/oscout_esteban` y `/relay/oscout_carlos` existen
  con esos nombres exactos (o ajustar `DESTINOS` en `relay_callbacks.py`
  si prefieres otros).
