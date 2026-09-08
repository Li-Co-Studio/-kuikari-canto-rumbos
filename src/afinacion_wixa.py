#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
afinacion_wixa.py — Medición de afinación del xaweri (Fase A)
LI_CO STUDIO / Colectivo Tutú · Residencia CCD Sala Memorial

Mide la rejilla de alturas real del xaweri de Ramón desde grabaciones
autorizadas: cuerdas al aire (arco, sostenidas) y pasajes/tonadas. Mismo
principio que la calibración de vocales: el sistema se afina a la
persona, no al revés (ver docs/KUIKARI_estado_del_proyecto.md, 2.2).
Motor de f0 compartido con voz_rumbos.py (librosa.pyin).

El kanari (guitarra, técnica de pulsado) se procesa aparte cuando lleguen
sus grabaciones — no bloquea esta fase.

Uso:
  python afinacion_wixa.py \
      --cuerdas cuerda_XEWI.wav cuerda_UTA.wav cuerda_AIKA.wav cuerda_NAUKA.wav \
      --pasajes tonada_01.wav tonada_02.wav tonada_03.wav
  → afinacion_ramon.json (Ramón puede regrabar y borrar cuando quiera)

  La etiqueta de cada cuerda sale del nombre de archivo (último tramo
  separado por "_", ej. "Violin_cuerda_01_XEWI.wav" → "XEWI"). La de
  cada pasaje es el nombre de archivo sin extensión.

Env lico-studio (py3.10): pip install librosa soundfile. Todo CPU. Sin CUDA.
"""
import argparse, json, os, sys
from collections import Counter
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voz_rumbos as vr

SR = 22050
FRAME = 1024
HOP = 256
FMIN_HZ = 80    # cuerda más grave del xaweri, con margen
FMAX_HZ = 2000  # armónico agudo de pasajes, con margen
RMS_UMBRAL = 0.01


def etiqueta_cuerda(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.split("_")[-1].upper()


def etiqueta_pasaje(path):
    return os.path.splitext(os.path.basename(path))[0]


def f0_contour(y, sr):
    """f0 por frame (pyin) + máscara de frames con voz y con energía real."""
    import librosa
    f0, voiced, _ = librosa.pyin(y, fmin=FMIN_HZ, fmax=FMAX_HZ, sr=sr,
                                 frame_length=FRAME * 2, hop_length=HOP)
    rms = librosa.feature.rms(y=y, frame_length=FRAME, hop_length=HOP)[0]
    n = min(len(f0), len(rms))
    mask = np.zeros(n, dtype=bool)
    for i in range(n):
        mask[i] = bool(voiced is not None and voiced[i] and not np.isnan(f0[i]) and rms[i] > RMS_UMBRAL)
    return f0[:n], mask, n


def runs_estables(f0, mask, hop, sr, tol_relativa=0.05, max_hueco_seg=0.05, min_frames=3):
    """Segmenta el f0 de UNA toma en tramos de altura estable, cortando en
    cada hueco de voz/energía mayor a max_hueco_seg o en cada salto de
    altura mayor a tol_relativa contra la mediana llevada hasta ahí.

    Hallazgo real (Fase A, corrección del arco corto): el arco del xaweri
    no siempre se apaga en ruido difuso — a veces la toma trae DOS
    eventos de arco distintos (una nota, una pausa breve de
    rearticulación que no baja lo suficiente como para que
    voz_rumbos.detectar_tomas() la lea como silencio ENTRE tomas, y luego
    otra nota). Este método separa esos tramos para que cada uno se mida
    aparte, en vez de promediarlos juntos.

    Devuelve lista de dicts {t0, t1, dur, hz, n} ordenable por duración."""
    n_total = len(f0)
    max_hueco_frames = max(1, int(max_hueco_seg * sr / hop))
    runs = []
    valores, i0, hueco = [], None, 0
    for i in range(n_total):
        if not mask[i]:
            hueco += 1
            if valores and hueco > max_hueco_frames:
                runs.append((i0, i - hueco + 1, list(valores)))
                valores, i0 = [], None
            continue
        hueco = 0
        if valores and abs(f0[i] - np.median(valores)) / np.median(valores) > tol_relativa:
            runs.append((i0, i, list(valores)))
            valores, i0 = [], None
        if not valores:
            i0 = i
        valores.append(f0[i])
    if valores:
        runs.append((i0, n_total, valores))
    out = []
    for (a, b, vals) in runs:
        if len(vals) < min_frames:
            continue
        out.append({
            "t0": round(a * hop / sr, 3), "t1": round(b * hop / sr, 3),
            "dur": round((b - a) * hop / sr, 3),
            "hz": float(np.median(vals)), "n": len(vals),
        })
    return out


def medir_cuerda(path, excluir_tomas=None, umbral_dispersion_hz=20.0, umbral_dispersion_rel=0.03,
                 umbral_ambiguedad_rel=0.85):
    """Mide cada toma por separado (ver voz_rumbos.detectar_tomas), y
    dentro de cada toma usa solo el tramo de altura estable más largo
    (ver runs_estables) — no toda la ventana delimitada por silencio,
    que puede traer más de un evento de arco. excluir_tomas: set de
    índices de toma (1-based) a excluir por decisión humana (ejecución
    confirmada por oído como incorrecta, no por inconsistencia
    algorítmica) — se documenta en el resultado, no se esconde.

    Si los dos tramos más largos de una toma duran casi lo mismo
    (relación >= umbral_ambiguedad_rel), elegir "el más largo" es casi
    una moneda al aire — se marca esa toma como ambigua en vez de
    reportar el resultado con la misma confianza que una toma sin
    empate."""
    import librosa
    excluir_tomas = excluir_tomas or set()
    y, sr = librosa.load(path, sr=SR, mono=True)
    tomas = vr.detectar_tomas(y, sr)
    detalle_tomas = []
    por_toma = []
    for idx, (t0, t1) in enumerate(tomas, start=1):
        s0, s1 = int(t0 * sr), int(t1 * sr)
        f0, mask, n = f0_contour(y[s0:s1], sr)
        runs = sorted(runs_estables(f0, mask, HOP, sr), key=lambda r: -r["dur"])
        excluida = idx in excluir_tomas
        ambigua = (len(runs) >= 2 and runs[1]["dur"] >= umbral_ambiguedad_rel * runs[0]["dur"])
        entrada = {"toma": idx, "tramos": runs, "excluida": excluida, "ambigua": ambigua}
        detalle_tomas.append(entrada)
        if runs and not excluida:
            por_toma.append(runs[0]["hz"])
    if not por_toma:
        return None
    hz = float(np.median(por_toma))
    disp = (max(por_toma) - min(por_toma)) if len(por_toma) > 1 else 0.0
    consistente = disp <= umbral_dispersion_hz or (disp / hz) <= umbral_dispersion_rel
    return {
        "hz": hz,
        "midi": float(librosa.hz_to_midi(hz)),
        "nota": librosa.hz_to_note(hz),
        "duracion_seg": round(len(y) / sr, 2),
        "n_tomas_usadas": len(por_toma),
        "hz_por_toma": [round(v, 1) for v in por_toma],
        "dispersion_hz": round(disp, 1),
        "consistente": consistente,
        "detalle_tomas": detalle_tomas,
    }


def medir_pasaje(path, top_n=6):
    import librosa
    y, sr = librosa.load(path, sr=SR, mono=True)
    f0, mask, n = f0_contour(y, sr)
    voz = f0[mask]
    if len(voz) == 0:
        return None
    hz_lo, hz_hi = np.percentile(voz, [5, 95])
    midis = librosa.hz_to_midi(voz)
    grados = Counter(int(round(m)) for m in midis)
    frecuentes = []
    for midi_i, n_oc in grados.most_common(top_n):
        hz_grado = float(np.median(voz[np.round(midis) == midi_i]))
        frecuentes.append({
            "midi": midi_i, "nota": librosa.midi_to_note(midi_i),
            "hz": hz_grado, "n": n_oc,
        })

    grado_dominante_por_toma = []
    for (t0, t1) in vr.detectar_tomas(y, sr):
        s0, s1 = int(t0 * sr), int(t1 * sr)
        f0t, maskt, _ = f0_contour(y[s0:s1], sr)
        vozt = f0t[maskt]
        if len(vozt) == 0:
            continue
        midist = librosa.hz_to_midi(vozt)
        top1 = Counter(int(round(m)) for m in midist).most_common(1)
        if top1:
            grado_dominante_por_toma.append(librosa.midi_to_note(top1[0][0]))

    return {
        "hz_min": float(hz_lo), "hz_max": float(hz_hi),
        "midi_min": float(np.min(midis)), "midi_max": float(np.max(midis)),
        "n_frames_voiced": int(mask.sum()),
        "duracion_seg": round(len(y) / sr, 2),
        "grados_frecuentes": frecuentes,
        "grado_dominante_por_toma": grado_dominante_por_toma,
    }


def parse_excluir_tomas(specs):
    """specs: lista de 'ETIQUETA:N' (N = número de toma, 1-based).
    Devuelve dict etiqueta -> set(N), para exclusiones decididas por oído
    (ejecución incorrecta), no por el algoritmo."""
    out = {}
    for spec in specs or []:
        etq, n = spec.split(":")
        out.setdefault(etq.upper(), set()).add(int(n))
    return out


def cmd_calibrar(cuerdas_paths, pasajes_paths, out_path, excluir_tomas=None):
    excluir_tomas = excluir_tomas or {}
    cuerdas = {}
    for p in cuerdas_paths:
        etq = etiqueta_cuerda(p)
        m = medir_cuerda(p, excluir_tomas=excluir_tomas.get(etq))
        if m is None:
            print(f"!! {p}: sin frames útiles (silencio o fuera de rango)")
            continue
        cuerdas[etq] = m
        excl = [t["toma"] for t in m["detalle_tomas"] if t["excluida"]]
        ambiguas = [t["toma"] for t in m["detalle_tomas"] if t["ambigua"] and not t["excluida"]]
        nota_excl = f"  (toma(s) {excl} excluida(s) por decisión humana, no algorítmica)" if excl else ""
        nota_amb = (f"  [AVISO: toma(s) {ambiguas} con dos tramos de duración casi igual — "
                     f"'el más largo' es casi al azar ahí, revisar por oído]") if ambiguas else ""
        aviso = "" if m["consistente"] else f"  [AVISO: tomas usadas NO consistentes entre sí — {m['hz_por_toma']} — revisar por oído]"
        print(f"  {etq}: {m['hz']:.1f}Hz ({m['nota']}) — {m['n_tomas_usadas']} tomas usadas: {m['hz_por_toma']}{nota_excl}{nota_amb}{aviso}  ({p})")

    pasajes = {}
    for p in pasajes_paths:
        etq = etiqueta_pasaje(p)
        m = medir_pasaje(p)
        if m is None:
            print(f"!! {p}: sin frames útiles (silencio o fuera de rango)")
            continue
        pasajes[etq] = m
        grados_txt = ", ".join(f"{g['nota']}({g['n']})" for g in m["grados_frecuentes"])
        print(f"  {etq}: {m['hz_min']:.0f}–{m['hz_max']:.0f}Hz — grados frecuentes: {grados_txt}  ({p})")

    out = {
        "instrumento": "xaweri",
        "autorizado_por": "Ramón Carrillo",
        "cuerdas_al_aire": cuerdas,
        "pasajes": pasajes,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"→ {out_path} (Ramón puede regrabar y recalibrar cuando quiera)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuerdas", nargs="+", default=[],
                     help="wavs de cuerdas al aire (arco, sostenidas)")
    ap.add_argument("--pasajes", nargs="+", default=[],
                     help="wavs de pasajes/tonadas")
    ap.add_argument("--out", default="afinacion_ramon.json")
    ap.add_argument("--excluir-toma", nargs="+", default=[], metavar="ETIQUETA:N",
                     help="excluye una toma por decisión humana (ejecución "
                          "confirmada por oído como incorrecta), ej. NAUKA:3. "
                          "No usar para 'arreglar' dispersión algorítmica sin "
                          "haber escuchado la grabación.")
    args = ap.parse_args()
    if not args.cuerdas and not args.pasajes:
        ap.print_help()
    else:
        cmd_calibrar(args.cuerdas, args.pasajes, args.out,
                     excluir_tomas=parse_excluir_tomas(args.excluir_toma))
