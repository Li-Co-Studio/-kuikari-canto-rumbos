#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voz_rumbos.py — Análisis de voz para "El canto de los rumbos"
LI_CO STUDIO / Colectivo Tutú · Residencia CCD Sala Memorial

Extrae de la voz (archivo o micrófono): tono (f0), sílabas (onsets),
vocal (formantes F1/F2 → a e i ɨ u) y emite MIDI + CSV + OSC en vivo.
NADA se graba en modo vivo: solo rasgos. Protocolo Tutú: la autoridad es Ramón.

Pivote 2026-08 (ver docs/KUIKARI_estado_del_proyecto.md, sección 2.1):
se retira el discurso de vocal→rumbo cuadrafónico. La vocal clasificada
ya no elige bocina, colorea el timbre del acorde (Fase F, filtro de
formantes, aún sin construir).

Fase D-bis 2026-08-25: el rumbo se restaura como canal PARALELO a la
clase, no en su lugar. `/voz/vocal` ahora manda tres argumentos:
vocal, clase (Fase F, ver CLASE_VOCAL) y rumbo (ver DEFAULT_RUMBOS /
--rumbos). El paneo espacial real del montaje sigue siendo Fase E
(paneo cuadrafónico en Ableton) — este rumbo es un dato disponible para
uso futuro (visual, registro), configurable por montaje, no canónico.

Uso:
  Analizar grabación (habla o canto):
      python voz_rumbos.py --file grabacion.wav
      → grabacion.analisis.csv  (t, f0_hz, midi, vocal, clase_vocal, rumbo)
      → grabacion.melodia.mid   (contorno melódico como notas MIDI)

  Calibrar vocales con la voz de Ramón (5 archivos, uno por vocal):
      python voz_rumbos.py --calibrate a.wav e.wav i.wav ix.wav u.wav
      → vocales_ramon.json  (centroides F1/F2 de SU voz)

  Listar dispositivos de entrada de audio:
      python voz_rumbos.py --list-devices

  En vivo (micrófono o grabación ruteada a una entrada → OSC, sin grabar nada):
      python voz_rumbos.py --live --device 2 --targets td,esteban
      python voz_rumbos.py --live --osc 127.0.0.1:7000
      (requiere: pip install sounddevice)
      --targets usa nombres de config.json (osc_targets.py); se suma a --osc
      si se dan ambos. Sin ninguno de los dos, --live apunta a "td" por
      default. El device y el hop en vivo (ms) por default salen de
      config.json (audio.device_in / audio.live_hop_ms) si no se pasan.
      --rumbos A E I U asigna el rumbo (int) de a/e/i/u para este montaje
      (ɨ/'+' es siempre 0, centro, por diseño). Sin --rumbos usa
      DEFAULT_RUMBOS, que es solo para que el script corra en pruebas —
      no es una asignación artística.

OSC que emite (para TouchDesigner y Ableton/M4L):
  /voz/silaba   [idx]                        cada onset de sílaba
  /voz/vocal    [vocal_str, clase, rumbo]    vocal clasificada + clase
                                              (índice estable, insumo del
                                              filtro de formantes de Fase F,
                                              no espacial) + rumbo (config.
                                              de montaje, ver --rumbos)
  /voz/f0       [hz, midi_float]       tono continuo (por frame)
  /voz/nota     [midi_int, vel]        nota estable (para el modular vía MIDI-CV)

Env lico-studio (py3.10):  pip install librosa soundfile mido python-osc sounddevice
Todo CPU. Sin CUDA. Sin subir nada a ningún lado.
"""
import argparse, json, csv, sys, os
import numpy as np

SR = 22050
FRAME = 1024
HOP = 256

# Centroides F1/F2 (Hz) provisionales para voz masculina; se REEMPLAZAN
# con la calibración de la voz real (vocales_ramon.json).
# ɨ se escribe '+' siguiendo la ortografía práctica de los corpus.
DEFAULT_VOWELS = {
    "a": (700, 1300),
    "e": (450, 1900),
    "i": (280, 2250),
    "+": (350, 1500),   # ɨ: central alta — F2 intermedio, F1 bajo
    "u": (310, 800),
}

# Índice de clase por vocal — estable, NO espacial (el rumbo cuadrafónico
# se retiró como discurso, ver docs/KUIKARI_estado_del_proyecto.md 2.1).
# Insumo crudo para el filtro de formantes de Fase F, todavía sin construir.
CLASE_VOCAL = {"a": 0, "e": 1, "i": 2, "+": 3, "u": 4}

# Rumbo espacial (0-4) por vocal — CONFIGURABLE POR MONTAJE, no un mapeo
# canónico. El único valor fijo por diseño: ɨ ('+') siempre es 0 (centro).
# a/e/i/u se asignan a las 4 direcciones perimetrales antes de cada
# función según lo que decidan Hafo/Ramón (ver --rumbos). El default de
# abajo es SOLO para que el script corra sin --rumbos (pruebas, uso
# exploratorio) — NO es la asignación artística de ningún montaje.
DEFAULT_RUMBOS = {"a": 1, "e": 2, "i": 3, "u": 4, "+": 0}


def parse_rumbos(vals):
    """vals: [a, e, i, u] (int, del flag --rumbos) o None.
    Devuelve el dict vocal->rumbo para esta función. ɨ ('+') es siempre 0
    (centro) por diseño, no se configura. Sin vals, usa DEFAULT_RUMBOS
    (solo pruebas, no la asignación artística — esa la da Hafo/Ramón
    antes de cada montaje)."""
    if vals is None:
        return dict(DEFAULT_RUMBOS)
    a, e, i, u = vals
    return {"a": a, "e": e, "i": i, "u": u, "+": 0}


def lpc_formants(frame, sr, n_formants=2):
    """F1..Fn por LPC. frame: audio mono ya ventaneado."""
    frame = frame * np.hamming(len(frame))
    frame = np.append(frame[0], frame[1:] - 0.97 * frame[:-1])  # pre-énfasis
    order = 2 + sr // 1000
    try:
        import librosa
        a = librosa.lpc(frame.astype(float), order=int(order))
    except Exception:
        return None
    roots = [r for r in np.roots(a) if np.imag(r) > 0.01]
    freqs = sorted(np.angle(roots) * (sr / (2 * np.pi)))
    freqs = [f for f in freqs if 90 < f < 4000]
    return freqs[:n_formants] if len(freqs) >= n_formants else None


def classify_vowel(f1, f2, centroids):
    best, bd = None, 1e12
    for v, (c1, c2) in centroids.items():
        d = ((f1 - c1) / 150.0) ** 2 + ((f2 - c2) / 300.0) ** 2  # ponderado
        if d < bd:
            bd, best = d, v
    return best


def analyze_array(y, sr, centroids, rumbos, osc_client=None, emit_tmin=None):
    """Núcleo compartido archivo/vivo: devuelve lista de eventos
    (t, hz, midi, vocal, clase, rumbo, onset).

    rumbos: dict vocal->rumbo (ver parse_rumbos/DEFAULT_RUMBOS).
    emit_tmin: si se da, solo se emite OSC para frames con t >= emit_tmin
    (evita reemitir la parte solapada de una ventana deslizante en vivo)."""
    import librosa
    f0, voiced, _ = librosa.pyin(y, fmin=65, fmax=800, sr=sr,
                                 frame_length=FRAME * 2, hop_length=HOP)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, hop_length=HOP, units="frames",
                                        backtrack=True)
    onset_set = set(onsets)
    rms = librosa.feature.rms(y=y, frame_length=FRAME, hop_length=HOP)[0]
    events, silaba = [], 0
    n = min(len(f0), len(rms))
    for i in range(n):
        t = i * HOP / sr
        hz = float(f0[i]) if voiced is not None and voiced[i] and not np.isnan(f0[i]) else 0.0
        midi = float(librosa.hz_to_midi(hz)) if hz > 0 else 0.0
        vocal, clase, rumbo = "", -1, -1
        if hz > 0 and rms[i] > 0.01:
            s, e = i * HOP, i * HOP + FRAME
            if e <= len(y):
                fs = lpc_formants(y[s:e], sr)
                if fs and len(fs) >= 2:
                    vocal = classify_vowel(fs[0], fs[1], centroids)
                    clase = CLASE_VOCAL.get(vocal, -1)
                    rumbo = rumbos.get(vocal, -1)
        is_onset = i in onset_set
        if is_onset:
            silaba += 1
        events.append((t, hz, midi, vocal, clase, rumbo, 1 if is_onset else 0))
        if osc_client and (emit_tmin is None or t >= emit_tmin):
            if is_onset:
                osc_client.send_message("/voz/silaba", silaba)
            if hz > 0:
                osc_client.send_message("/voz/f0", [hz, midi])
            if vocal:
                osc_client.send_message("/voz/vocal", [vocal, clase, rumbo])
    return events


def events_to_midi(events, path, min_dur=0.08):
    """Contorno f0 → notas MIDI estables (canto → melodía)."""
    import mido
    mid = mido.MidiFile(); tr = mido.MidiTrack(); mid.tracks.append(tr)
    tempo = mido.bpm2tempo(120); tr.append(mido.MetaMessage("set_tempo", tempo=tempo))
    tpb = mid.ticks_per_beat
    def t2tick(t): return int(mido.second2tick(t, tpb, tempo))
    cur, start, last_t = None, 0.0, 0.0
    notes = []
    for (t, hz, midi, *_ ) in events:
        m = int(round(midi)) if midi > 0 else None
        if m != cur:
            if cur is not None and t - start >= min_dur:
                notes.append((start, t, cur))
            cur, start = m, t
        last_t = t
    if cur is not None and last_t - start >= min_dur:
        notes.append((start, last_t, cur))
    pos = 0
    for (s, e, m) in notes:
        tr.append(mido.Message("note_on", note=max(0, min(127, m)), velocity=90,
                               time=t2tick(s) - pos))
        tr.append(mido.Message("note_off", note=max(0, min(127, m)), velocity=0,
                               time=t2tick(e) - t2tick(s)))
        pos = t2tick(e)
    mid.save(path)
    return len(notes)


def load_centroids(path="vocales_ramon.json"):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        print(f"[calibración cargada: {path}]")
        return {k: tuple(v) for k, v in d.items()}
    print("[sin calibración — usando centroides provisionales; calibrar con la voz de Ramón]")
    return dict(DEFAULT_VOWELS)


def make_osc(spec):
    if not spec:
        return None
    from pythonosc.udp_client import SimpleUDPClient
    host, port = spec.split(":")
    return SimpleUDPClient(host, int(port))


class _MultiOSC:
    """Envía el mismo mensaje a varios clientes OSC (mismo shape que SimpleUDPClient)."""
    def __init__(self, clients):
        self.clients = clients

    def send_message(self, address, value):
        for c in self.clients:
            c.send_message(address, value)


def _audio_config():
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import osc_targets
        return osc_targets.cargar_config().get("audio", {})
    except Exception:
        return {}


def resolve_device(cli_device):
    if cli_device is not None:
        return cli_device
    return _audio_config().get("device_in")


def resolve_hop_ms(cli_hop_ms=None):
    if cli_hop_ms is not None:
        return cli_hop_ms
    return _audio_config().get("live_hop_ms", 250)


def build_osc_client(osc_spec, targets_str, default_live_target=False):
    """Combina --osc (host:puerto suelto) y --targets (nombres de config.json)."""
    clients = []
    single = make_osc(osc_spec)
    if single:
        clients.append(single)
    nombres = [n.strip() for n in targets_str.split(",") if n.strip()] if targets_str else []
    if not nombres and not osc_spec and default_live_target:
        nombres = ["td"]
    if nombres:
        import osc_targets
        clients.extend(osc_targets.clientes(nombres))
    if not clients:
        return None
    return clients[0] if len(clients) == 1 else _MultiOSC(clients)


def cmd_file(path, centroids, rumbos, osc):
    import librosa
    y, sr = librosa.load(path, sr=SR, mono=True)
    print(f"[{path}: {len(y)/sr:.1f}s @ {sr}Hz]")
    events = analyze_array(y, sr, centroids, rumbos, osc)
    base = os.path.splitext(path)[0]
    with open(base + ".analisis.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["t_seg", "f0_hz", "midi", "vocal", "clase_vocal", "rumbo", "onset_silaba"])
        w.writerows([(f"{t:.3f}", f"{hz:.1f}", f"{m:.2f}", v, c, r, o) for t, hz, m, v, c, r, o in events])
    nn = events_to_midi(events, base + ".melodia.mid")
    sil = sum(e[6] for e in events)
    voc = [e[3] for e in events if e[3]]
    from collections import Counter
    print(f"→ {base}.analisis.csv  ({len(events)} frames)")
    print(f"→ {base}.melodia.mid   ({nn} notas)")
    print(f"   sílabas detectadas: {sil} | vocales: {Counter(voc).most_common()}")


def cmd_calibrate(paths):
    import librosa
    order = ["a", "e", "i", "+", "u"]
    out = {}
    for v, p in zip(order, paths):
        y, sr = librosa.load(p, sr=SR, mono=True)
        f1s, f2s = [], []
        for s in range(0, len(y) - FRAME, HOP * 4):
            fs = lpc_formants(y[s:s + FRAME], sr)
            if fs and len(fs) >= 2 and fs[0] < 1100:
                f1s.append(fs[0]); f2s.append(fs[1])
        if not f1s:
            print(f"!! {p}: sin frames útiles"); continue
        out[v] = [float(np.median(f1s)), float(np.median(f2s))]
        print(f"  {v}: F1={out[v][0]:.0f} F2={out[v][1]:.0f}  ({p})")
    with open("vocales_ramon.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("→ vocales_ramon.json (Ramón puede regrabar y recalibrar cuando quiera)")


def cmd_live(centroids, rumbos, osc, device=None, hop_ms=250, window_sec=0.5, channel=1):
    import sounddevice as sd
    import time
    hop = hop_ms / 1000.0
    win_n = int(window_sec * SR)
    canal_idx = channel - 1
    n_channels = max(channel, 1)
    HEARTBEAT_SEG = 2.0
    RMS_UMBRAL = 0.005
    SOSTENIDO_SEG = 3.0
    AVISO_COOLDOWN = 60.0
    print(f"[EN VIVO — device={device if device is not None else 'default'} canal={channel} "
          f"hop={hop_ms}ms ventana={window_sec}s — no se graba nada. Ctrl+C para salir]")
    buf = np.zeros(0, dtype=np.float32)

    def cb(indata, frames, t_, status):
        nonlocal buf
        buf = np.concatenate([buf, indata[:, canal_idx]])

    latencias = []
    silabas_totales = 0
    ultimo_vocal = "-"
    ultimo_f0 = 0.0
    ultimo_rms = 0.0
    last_heartbeat = time.perf_counter()
    rms_bajo_desde = None
    ultimo_aviso = -AVISO_COOLDOWN
    with sd.InputStream(samplerate=SR, channels=n_channels, callback=cb, blocksize=HOP, device=device):
        next_t = time.perf_counter()
        try:
            while True:
                next_t += hop
                sleep_for = next_t - time.perf_counter()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                if len(buf) >= win_n:
                    chunk = buf[-win_n:]
                    buf = buf[-win_n:]  # ventana deslizante acotada en memoria
                    t0 = time.perf_counter()
                    events = analyze_array(chunk, SR, centroids, rumbos, osc, emit_tmin=window_sec - hop)
                    latencias.append(time.perf_counter() - t0)
                    if len(latencias) % 20 == 0:
                        prom = sum(latencias[-20:]) / 20
                        print(f"[proceso/hop ~{prom * 1000:.0f}ms (hop pedido {hop_ms}ms)]")

                    emitidos = [e for e in events if e[0] >= window_sec - hop]
                    silabas_totales += sum(e[6] for e in emitidos)
                    for e in emitidos:
                        if e[3]:
                            ultimo_vocal = e[3]
                        if e[1] > 0:
                            ultimo_f0 = e[1]
                    seg = chunk[-int(hop * SR):]
                    ultimo_rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0

                    ahora = time.perf_counter()
                    if ultimo_rms < RMS_UMBRAL:
                        if rms_bajo_desde is None:
                            rms_bajo_desde = ahora
                        elif (ahora - rms_bajo_desde > SOSTENIDO_SEG
                              and ahora - ultimo_aviso > AVISO_COOLDOWN):
                            print(f"[sin señal en el canal {channel} — revisa ganancia/ruteo]")
                            ultimo_aviso = ahora
                    else:
                        rms_bajo_desde = None

                    if ahora - last_heartbeat >= HEARTBEAT_SEG:
                        print(f"[oye: {silabas_totales} sílabas · vocal: {ultimo_vocal} · "
                              f"f0: {ultimo_f0:.0f}Hz · rms: {ultimo_rms:.3f}]")
                        last_heartbeat = ahora
        except KeyboardInterrupt:
            if latencias:
                prom = sum(latencias) / len(latencias)
                print(f"[latencia media de proceso por hop: {prom * 1000:.0f}ms "
                      f"sobre {len(latencias)} hops (hop pedido {hop_ms}ms, "
                      f"real ~{max(hop_ms, prom * 1000):.0f}ms si el proceso no alcanza)]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file"); ap.add_argument("--live", action="store_true")
    ap.add_argument("--calibrate", nargs=5, metavar=("A", "E", "I", "IX", "U"))
    ap.add_argument("--rumbos", nargs=4, type=int, metavar=("A", "E", "I", "U"),
                     help="rumbo (int) de a/e/i/u para este montaje — configurable, "
                          "no un mapeo fijo. ɨ ('+') siempre es 0 (centro). Sin esta "
                          "opción usa DEFAULT_RUMBOS (solo pruebas, no la asignación "
                          "artística del montaje)")
    ap.add_argument("--osc", help="host:puerto, ej. 127.0.0.1:7000")
    ap.add_argument("--targets", help='nombres de config.json, ej. "td,esteban" (se suma a --osc)')
    ap.add_argument("--list-devices", action="store_true", help="lista entradas de audio disponibles")
    ap.add_argument("--device", type=int, default=None, help="índice de entrada de audio (ver --list-devices)")
    ap.add_argument("--hop-ms", type=int, default=None, help="hop del modo --live en ms (default: config.json)")
    ap.add_argument("--channel", type=int, default=1,
                     help="canal de entrada a analizar, 1=primero (default). "
                          "Permite abrir el stream con varios canales (condensador + línea Ableton) "
                          "sin desconectar cables.")
    args = ap.parse_args()
    if args.list_devices:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                print(f"{i}: {d['name']}  (in={d['max_input_channels']}, sr={d['default_samplerate']:.0f})")
        sys.exit(0)
    if args.calibrate:
        cmd_calibrate(args.calibrate); sys.exit(0)
    cent = load_centroids()
    rumbos = parse_rumbos(args.rumbos)
    osc = build_osc_client(args.osc, args.targets, default_live_target=args.live)
    if args.file:
        cmd_file(args.file, cent, rumbos, osc)
    elif args.live:
        cmd_live(cent, rumbos, osc, device=resolve_device(args.device), hop_ms=resolve_hop_ms(args.hop_ms),
                 channel=args.channel)
    else:
        ap.print_help()
