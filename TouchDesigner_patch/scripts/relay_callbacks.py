# relay_callbacks.py
# Callbacks del container /relay: reenvía /voz/* y /telar/* recibidos en
# :7000 hacia Esteban y Carlos, calcula canales derivados /rumbos/* y
# el motor de paneo cuadrafónico /paneo/* hacia Ableton (TDAbleton)
# (ver docs/OSC_SPEC.md para la tabla completa de direcciones).
#
# Fase F (2026-08-26): motor de formantes vocal->timbre (vocal->F1/F2, ver
# FORMANTES_DEFAULT/cargar_formantes). Parte 2: EQ Eight real agregado a
# 1-Vital/2-Vital (índice 1, banda 1/2 en Bell) vía MCP con Ableton
# abierto; índices de parámetro e índice de dispositivo confirmados en
# vivo con get_device_parameters, no adivinados — ver
# FORMANTE_DEVICE_INDEX/FORMANTE_PARAM_FREQ y docs/BITACORA_SETUP.md.
#
# Decisión de implementación: los derivados se calculan aquí en Python
# (más fácil de probar sin TD abierto — ver smoke test 4 / verificacion.py)
# en vez de una red de CHOPs (Lag/Trigger/Math). Si Hafo prefiere la vía
# nativa, la alternativa con CHOPs queda anotada en MONTAJE.md.
#
# Requiere en /relay tres OSC Out DAT nativos (sin dependencias pip):
#   /relay/oscout_esteban, /relay/oscout_carlos, /relay/oscout_ableton
# Se configuran (address/port) leyendo config.json vía inicializar().

import json
import math
import os

DESTINOS = {"esteban": "/project1/relay/oscout_esteban", "carlos": "/project1/relay/oscout_carlos"}
DESTINO_ABLETON = "/project1/relay/oscout_ableton"
THROTTLE_HZ = 45  # dentro del rango 30-60Hz pedido por el brief
LAG = 0.15        # coeficiente de suavizado exponencial (0-1, mayor = más rápido)
RUMBO_NOMBRES = {1: "1", 2: "2", 3: "3", 4: "4", 0: "centro"}

ESTADO_INICIAL = {
    "f0_norm": 0.0,
    "energia": {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0},
    "fila": 0,
    "formante": None,  # (F1, F2) de la última vocal clasificada, o None
}

# ---- Paneo cuadrafónico (Fase E) ----
# Orden horario de las 4 bocinas, 90° entre cada una. FL en el origen (0°).
ORDEN_BOCINAS = ["FL", "FR", "BR", "BL"]
PANEO_PASO_SILABA_DEG = 30.0   # cuánto avanza el ángulo por cada onset de sílaba (fuente "C")
PANEO_LAG_DENSIDAD = 0.08      # suavizado de la densidad — más lento que LAG de voz a propósito
PANEO_F_AMPLITUD_DEG = 20.0    # en modo manual "F", cuánto oscila la modulación automática
                                # alrededor del centro que fija Hafo — valor de arranque, ajustable

# Control real confirmado en vivo (2026-08-09): TDA_Level/TDA_Mapper no
# reciben OSC (solo emiten). El control de Ableton es el shell remoto de
# TDAbleton (puerto 58888): /shell/runCode ejecuta Python contra SONG
# (Live API). Se probó escribiendo SONG.tracks[0].mixer_device.sends[0]
# y confirmando el valor leído + visualmente en Ableton.
TRACKS_FUENTE = [2]  # solo "3-Canto_RAMON..." — Ramón va independiente del resto de las tracks, a pedido de Hafo
PANEO_THROTTLE_HZ = 20  # más bajo que THROTTLE_HZ: cada envío es un exec() de Python dentro de Ableton, no un binding liviano
TDA_RECONNECT_PORT = 58811  # puerto "de respuesta" que se declara en el handshake — no lo escuchamos, solo hace falta un valor válido

_PANEO_CODIGO = """\
_g = ({fl:.4f}, {fr:.4f}, {bl:.4f}, {br:.4f})
for _i in {tracks}:
    _s = SONG.tracks[_i].mixer_device.sends
    for _j in range(4):
        _s[_j].value = _g[_j]
"""

PANEO_INICIAL = {
    "angulo": 0.0,
    "densidad": 0.0,
    "fuente": "C",        # "C" (sílaba) o "F" (manual). "B" (respiración) queda pendiente:
                           # no existe todavía una señal viva de pausa de respiro (solo se
                           # calcula offline en analisis_canto.py) — ver bitácora.
    "manual_angulo": None,
}

# ---- Filtro de formantes vocal a timbre (Fase F — 2026-08-26) ----
# Motor puro (lookup vocal->F1/F2) y throttle, mismo patrón que Fase E parte 1
# (calcular_ganancias) antes de tocar Ableton.

FORMANTES_DEFAULT = {
    "a": (700, 1300),
    "e": (450, 1900),
    "i": (280, 2250),
    "+": (350, 1500),
    "u": (310, 800),
}  # espejo de DEFAULT_VOWELS en voz_rumbos.py — provisional hasta que
   # exista vocales_ramon.json real de Ramón

TRACKS_FORMANTE = [0, 1]  # 1-Vital, 2-Vital — mismo orden de tracks que
                           # confirmó Fase E (TRACKS_FUENTE=[2] es "3-Canto_RAMON...")

# EQ Eight agregado a mano por MCP (Ableton abierto, 2026-08-26) en el
# índice 1 de la cadena de dispositivos (después del Vital) en las dos
# tracks — confirmado con get_track_info/get_device_parameters, no
# asumido. Banda 1 = F1, banda 2 = F2, las dos puestas en modo Bell (tipo
# 3) a mano; cada banda expone Frecuencia por canal A y B (EQ Eight
# siempre separa A/B aunque el modo sea Stereo), así que se escriben las
# dos por banda para que no queden desincronizados los canales.
FORMANTE_DEVICE_INDEX = 1
FORMANTE_PARAM_FREQ = {
    1: (6, 11),    # "1 Frequency A", "1 Frequency B"
    2: (16, 21),   # "2 Frequency A", "2 Frequency B"
}

# El parámetro Frequency de EQ Eight es 0.0-1.0, NO Hz directo. Curva
# calibrada en vivo contra el dispositivo real (no de memoria/documentación,
# que no la especifica): t=0.0->10Hz, t=0.5->469Hz, t=1.0->22000Hz. La
# fórmula log fmin*(fmax/fmin)^t predice 469.04Hz en t=0.5 — coincide con
# los 469Hz leídos en pantalla, confirma la curva.
EQ8_FREQ_MIN_HZ = 10.0
EQ8_FREQ_MAX_HZ = 22000.0

FORMANTE_THROTTLE_HZ = 20  # mismo orden que PANEO_THROTTLE_HZ

_FORMANTE_CODIGO = """\
for _i in {tracks}:
    _d = SONG.tracks[_i].devices[{device_index}]
    for _p in {params_f1}:
        _d.parameters[_p].value = {t1:.6f}
    for _p in {params_f2}:
        _d.parameters[_p].value = {t2:.6f}
"""


def hz_a_normalizado(hz):
    """Hz -> 0.0-1.0 para el parámetro Frequency de EQ Eight, según la
    curva calibrada en vivo (ver EQ8_FREQ_MIN_HZ/EQ8_FREQ_MAX_HZ)."""
    hz = max(EQ8_FREQ_MIN_HZ, min(EQ8_FREQ_MAX_HZ, hz))
    return math.log(hz / EQ8_FREQ_MIN_HZ) / math.log(EQ8_FREQ_MAX_HZ / EQ8_FREQ_MIN_HZ)


def cargar_formantes(config_dir):
    """Lee vocales_ramon.json junto a config.json (mismo formato que genera
    voz_rumbos.py --calibrate: {"a": [F1, F2], ...}). Sin el archivo, usa
    FORMANTES_DEFAULT (provisional, no la voz real de Ramón)."""
    path = os.path.join(config_dir, "vocales_ramon.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return {k: tuple(v) for k, v in d.items()}
    return dict(FORMANTES_DEFAULT)


def _lerp(actual, objetivo, coef):
    return actual + (objetivo - actual) * coef


def _ganancias_par(angulo_deg):
    """Ley de potencia constante entre las 2 bocinas adyacentes al ángulo.
    Imagen concentrada (densidad 0), pura, testable fuera de TD."""
    a = angulo_deg % 360.0
    idx = int(a // 90)
    t = (a % 90) / 90.0
    b1, b2 = ORDEN_BOCINAS[idx], ORDEN_BOCINAS[(idx + 1) % 4]
    g = {s: 0.0 for s in ORDEN_BOCINAS}
    g[b1] = math.cos(t * math.pi / 2)
    g[b2] = math.sin(t * math.pi / 2)
    return g


def _ganancias_repartidas():
    """Las 4 bocinas a la misma potencia — imagen totalmente abierta (densidad 1)."""
    return {s: 0.5 for s in ORDEN_BOCINAS}  # sum(g^2) = 4 * 0.25 = 1.0, potencia constante


def calcular_ganancias(angulo_deg, densidad):
    """Pura (sin llamadas a TD). densidad 0-1: 0 = imagen concentrada en el
    ángulo, 1 = repartida pareja en las 4 bocinas. Mezcla en potencia (no en
    amplitud) para que la suma de cuadrados sea 1 en todo el rango."""
    densidad = max(0.0, min(1.0, densidad))
    par = _ganancias_par(angulo_deg)
    repartida = _ganancias_repartidas()
    return {
        s: math.sqrt((1 - densidad) * par[s] ** 2 + densidad * repartida[s] ** 2)
        for s in ORDEN_BOCINAS
    }


def calcular_actualizacion(estado, address, args, formantes=None):
    """Pura (sin llamadas a TD): dado el estado y un mensaje entrante,
    devuelve el estado nuevo. Testable fuera de TouchDesigner. `formantes`
    es el dict vocal->(F1, F2) (Fase F); sin pasarlo, ese campo no cambia."""
    nuevo = dict(estado)
    nuevo["energia"] = dict(estado["energia"])

    if address == "/voz/f0":
        hz, midi = args[0], args[1]
        if hz and hz > 0:
            objetivo = max(0.0, min(1.0, (midi - 36) / (84 - 36)))
            nuevo["f0_norm"] = _lerp(nuevo["f0_norm"], objetivo, LAG)
        else:
            for k in nuevo["energia"]:
                nuevo["energia"][k] = _lerp(nuevo["energia"][k], 0.0, LAG)

    elif address == "/voz/vocal":
        # Fase D-bis (2026-08-25): /voz/vocal vuelve a traer 3 argumentos
        # [vocal, clase, rumbo]. Antes de esto, este bloque leía args[1]
        # (clase, no rumbo) por un pendiente desde Fase D — ver
        # docs/OSC_SPEC.md. Con el rumbo real disponible de nuevo, vuelve
        # a leerse aquí.
        vocal, _clase, rumbo = args[0], args[1], args[2]
        for k in nuevo["energia"]:
            objetivo = 1.0 if k == rumbo else 0.0
            nuevo["energia"][k] = _lerp(nuevo["energia"][k], objetivo, LAG if k == rumbo else LAG * 0.4)
        if formantes is not None:
            # Sin clasificación (vocal == "") mantiene el último formante:
            # el timbre no debe cortar a silencio entre frames sin vocal.
            nuevo["formante"] = formantes.get(vocal, nuevo["formante"])

    elif address == "/telar/palabra":
        nuevo["fila"] = estado["fila"] + 1

    return nuevo


# ---- Config / init (llamadas reales a TD desde aquí en adelante) ----

def cargar_config():
    path = os.path.join(project.folder, "..", "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolver(nombre, config):
    spec = config.get("targets", {}).get(nombre)
    if not spec or "[" in spec:
        return None
    host, puerto = spec.split(":")
    return host, int(puerto)


def inicializar():
    """Llamar una vez al arrancar (o desde un botón 'recargar config').
    Configura address/port de cada OSC Out DAT desde config.json;
    desactiva el reenvío a los destinos con placeholder sin resolver."""
    config = cargar_config()
    for nombre, ruta in DESTINOS.items():
        resuelto = _resolver(nombre, config)
        dest = op(ruta)
        if resuelto and dest is not None:
            host, puerto = resuelto
            dest.par.address = host
            dest.par.port = puerto
            me.store(f"{nombre}_activo", True)
        else:
            me.store(f"{nombre}_activo", False)
            print(f"[relay] {nombre}: sin IP real en config.json — no se reenvía todavía")
    resuelto_ableton = _resolver("ableton", config)
    dest_ableton = op(DESTINO_ABLETON)
    if resuelto_ableton and dest_ableton is not None:
        host, puerto = resuelto_ableton
        dest_ableton.par.address = host
        dest_ableton.par.port = puerto
        me.store("ableton_activo", True)
        dest_ableton.sendOSC("/tda/command", ["connect", TDA_RECONNECT_PORT, "kuikari-relay"])
    else:
        me.store("ableton_activo", False)
        print("[relay] ableton: sin oscout_ableton en el patch o sin IP en config.json — paneo no se envía todavía")

    me.store("rumbos_estado", dict(ESTADO_INICIAL))
    me.store("paneo_estado", dict(PANEO_INICIAL))
    me.store("formantes", cargar_formantes(os.path.join(project.folder, "..")))
    me.store("ultimo_envio_ts", 0.0)
    me.store("paneo_ultimo_envio_ts", 0.0)
    me.store("formante_ultimo_envio_ts", 0.0)
    me.store("silaba_activa", False)


def _enviar_a_activos(address, args):
    for nombre, ruta in DESTINOS.items():
        if me.fetch(f"{nombre}_activo", False):
            op(ruta).sendOSC(address, list(args))


def _enviar_ableton(address, args):
    if me.fetch("ableton_activo", False):
        op(DESTINO_ABLETON).sendOSC(address, list(args))


def onReceiveOSC(dat, rowIndex, message, bytes, timeStamp, address, args, peer):
    if address.startswith("/voz/") or address.startswith("/telar/"):
        _enviar_a_activos(address, args)  # passthrough crudo

    if address == "/voz/silaba":
        _enviar_a_activos("/rumbos/silaba", [1])
        me.store("silaba_activa", True)
        me.store("silaba_on_time", absTime.seconds)

        paneo = me.fetch("paneo_estado", dict(PANEO_INICIAL))
        if paneo["fuente"] == "C":
            paneo["angulo"] = (paneo["angulo"] + PANEO_PASO_SILABA_DEG) % 360.0
        paneo["densidad"] = 1.0  # D siempre activa: cada sílaba sube la densidad, decae en tick()
        me.store("paneo_estado", paneo)

    elif address == "/paneo/fuente":
        paneo = me.fetch("paneo_estado", dict(PANEO_INICIAL))
        if args[0] in ("C", "F"):
            paneo["fuente"] = args[0]
        me.store("paneo_estado", paneo)

    elif address == "/paneo/manual":
        paneo = me.fetch("paneo_estado", dict(PANEO_INICIAL))
        paneo["manual_angulo"] = float(args[0]) % 360.0
        me.store("paneo_estado", paneo)

    estado = me.fetch("rumbos_estado", dict(ESTADO_INICIAL))
    formantes = me.fetch("formantes", dict(FORMANTES_DEFAULT))
    me.store("rumbos_estado", calcular_actualizacion(estado, address, args, formantes))
    return


def tick():
    """Llamar cada frame (Execute DAT onFrameStart): apaga el bang de
    /rumbos/silaba y envía los derivados suavizados, con throttle a
    THROTTLE_HZ para no saturar la red."""
    ahora = absTime.seconds

    if me.fetch("silaba_activa", False) and ahora - me.fetch("silaba_on_time", 0) > 0.05:
        _enviar_a_activos("/rumbos/silaba", [0])
        me.store("silaba_activa", False)

    if ahora - me.fetch("ultimo_envio_ts", 0.0) < (1.0 / THROTTLE_HZ):
        return
    me.store("ultimo_envio_ts", ahora)

    estado = me.fetch("rumbos_estado", dict(ESTADO_INICIAL))
    _enviar_a_activos("/rumbos/f0_norm", [estado["f0_norm"]])
    for k, nombre in RUMBO_NOMBRES.items():
        _enviar_a_activos(f"/rumbos/energia/{nombre}", [estado["energia"][k]])
    _enviar_a_activos("/rumbos/fila", [estado["fila"]])

    paneo = me.fetch("paneo_estado", dict(PANEO_INICIAL))
    paneo["densidad"] = _lerp(paneo["densidad"], 0.0, PANEO_LAG_DENSIDAD)
    angulo_final = paneo["angulo"]
    if paneo["fuente"] == "F" and paneo["manual_angulo"] is not None:
        vaiven = ((paneo["angulo"] % 360.0) / 360.0 - 0.5) * 2 * PANEO_F_AMPLITUD_DEG
        angulo_final = (paneo["manual_angulo"] + vaiven) % 360.0
    me.store("paneo_estado", paneo)

    if ahora - me.fetch("paneo_ultimo_envio_ts", 0.0) >= (1.0 / PANEO_THROTTLE_HZ):
        me.store("paneo_ultimo_envio_ts", ahora)
        g = calcular_ganancias(angulo_final, paneo["densidad"])
        codigo = _PANEO_CODIGO.format(fl=g["FL"], fr=g["FR"], bl=g["BL"], br=g["BR"],
                                       tracks=tuple(TRACKS_FUENTE))
        _enviar_ableton("/shell/runCode", [codigo])

    if (FORMANTE_DEVICE_INDEX is not None and estado["formante"] is not None
            and ahora - me.fetch("formante_ultimo_envio_ts", 0.0) >= (1.0 / FORMANTE_THROTTLE_HZ)):
        me.store("formante_ultimo_envio_ts", ahora)
        f1, f2 = estado["formante"]
        codigo = _FORMANTE_CODIGO.format(tracks=tuple(TRACKS_FORMANTE), device_index=FORMANTE_DEVICE_INDEX,
                                          params_f1=FORMANTE_PARAM_FREQ[1], params_f2=FORMANTE_PARAM_FREQ[2],
                                          t1=hz_a_normalizado(f1), t2=hz_a_normalizado(f2))
        _enviar_ableton("/shell/runCode", [codigo])
