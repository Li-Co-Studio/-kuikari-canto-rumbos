#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analisis_canto.py — Análisis explicativo completo de un canto (Ramón)
LI_CO STUDIO / Colectivo Tutú · "El canto de los rumbos"

Genera 5 figuras + resumen.md en out/analisis_canto/ a partir de una
grabación: forma+tono, espectrograma, vocales (con advertencia de
calibración provisional), piano-roll, respiración.

Uso:
    python scripts/analisis_canto.py [ruta_audio]
    (default: E:\\WIXA\\Audio\\Canto_RAMON0xmodular-02.wav)

Env lico-studio (py3.10). Todo CPU, sin CUDA.
"""
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle, FancyBboxPatch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import voz_rumbos as vr
import librosa
import librosa.display

INK = "#141210"
GOLD = "#8a6b1f"
DPI = 300

BASE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DEFAULT = r"E:\WIXA\Audio\Canto_RAMON0xmodular-02.wav"
OUTDIR = os.path.join(BASE, "..", "out", "analisis_canto")
CENTROIDES_PATH = os.path.join(BASE, "..", "vocales_ramon.json")

CMAP_ESPECTRO = LinearSegmentedColormap.from_list("lico_espectro", ["#ffffff", INK, GOLD])
VOCAL_ORDEN = ["u", "+", "i", "e", "a"]  # cerrada -> abierta


def _estilo_fig(fig):
    fig.patch.set_facecolor("white")


def _estilo_ejes(ax, titulo, xlabel="Tiempo (s)", ylabel=""):
    ax.set_facecolor("white")
    ax.set_title(titulo, color=INK, fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, color=INK, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK, fontsize=10)
    ax.tick_params(colors=INK, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(INK)
        spine.set_linewidth(0.8)
    ax.grid(True, color=INK, alpha=0.08, linewidth=0.5)


def fig_forma_tono(y, sr, t, hz, onset_t, path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True,
                                    gridspec_kw={"height_ratios": [1, 1.2]})
    _estilo_fig(fig)
    t_wave = np.arange(len(y)) / sr
    ax1.plot(t_wave, y, color=INK, linewidth=0.4)
    for ot in onset_t:
        ax1.axvline(ot, color=GOLD, alpha=0.35, linewidth=0.7)
    _estilo_ejes(ax1, "Forma de onda + sílabas detectadas", ylabel="Amplitud")
    ax1.set_xlabel("")

    hz_plot = np.where(hz > 0, hz, np.nan)
    ax2.plot(t, hz_plot, color=GOLD, linewidth=1.3)
    for ot in onset_t:
        ax2.axvline(ot, color=INK, alpha=0.12, linewidth=0.7)
    _estilo_ejes(ax2, "Contorno de tono (f0)", ylabel="f0 (Hz)")

    fig.suptitle("El canto de los rumbos — forma y tono", color=INK,
                 fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def fig_espectrograma(y, sr, path):
    S = librosa.stft(y, n_fft=2048, hop_length=vr.HOP)
    S_db = librosa.amplitude_to_db(np.abs(S), ref=np.max)
    fig, ax = plt.subplots(figsize=(11, 5))
    _estilo_fig(fig)
    img = librosa.display.specshow(S_db, sr=sr, hop_length=vr.HOP, x_axis="time",
                                    y_axis="log", ax=ax, cmap=CMAP_ESPECTRO,
                                    vmin=-70, vmax=0)
    _estilo_ejes(ax, "Espectrograma (STFT, escala log)", ylabel="Frecuencia (Hz)")
    cbar = fig.colorbar(img, ax=ax, format="%+.0f dB")
    cbar.ax.yaxis.set_tick_params(color=INK, labelcolor=INK)
    cbar.outline.set_edgecolor(INK)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def fig_vocales(t, vocal, hz, calibrado, path):
    fig, ax = plt.subplots(figsize=(11, 5))
    _estilo_fig(fig)
    ys = [VOCAL_ORDEN.index(v) if v in VOCAL_ORDEN else -1 for v in vocal]
    mask = np.array(ys) >= 0
    tt = np.array(t)[mask]
    yy = np.array(ys)[mask]
    voz_activa = hz[mask] > 0
    ax.scatter(tt, yy, s=14, color=GOLD, alpha=np.where(voz_activa, 0.85, 0.25),
               edgecolors=INK, linewidths=0.3)
    ax.set_yticks(range(len(VOCAL_ORDEN)))
    etiquetas = {"a": "a", "e": "e", "i": "i", "+": "ɨ", "u": "u"}
    ax.set_yticklabels([etiquetas[v] for v in VOCAL_ORDEN], color=INK, fontsize=11)
    _estilo_ejes(ax, "Vocales clasificadas en el tiempo", ylabel="Vocal")
    ax.set_ylim(-0.7, len(VOCAL_ORDEN) - 0.3)

    if not calibrado:
        aviso = ("ADVERTENCIA: calibración provisional — estos centroides F1/F2 "
                 "NO son de la voz de Ramón.\nPendiente: voz_rumbos.py --calibrate "
                 "a.wav e.wav i.wav ix.wav u.wav")
        ax.text(0.5, 1.14, aviso, transform=ax.transAxes, ha="center", va="bottom",
                fontsize=9.5, color=INK, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#f4ecd8",
                          edgecolor=GOLD, linewidth=1.4))

    fig.tight_layout(rect=[0, 0, 1, 0.90])
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def _agrupar_notas(t, midi, min_dur=0.08):
    notas = []
    cur, start, last_t = None, 0.0, 0.0
    for ti, m in zip(t, midi):
        mi = int(round(m)) if m > 0 else None
        if mi != cur:
            if cur is not None and ti - start >= min_dur:
                notas.append((start, ti, cur))
            cur, start = mi, ti
        last_t = ti
    if cur is not None and last_t - start >= min_dur:
        notas.append((start, last_t, cur))
    return notas


def fig_piano_roll(t, midi, path):
    notas = _agrupar_notas(t, midi)
    fig, ax = plt.subplots(figsize=(11, 5))
    _estilo_fig(fig)
    if notas:
        m_min = min(n[2] for n in notas) - 2
        m_max = max(n[2] for n in notas) + 2
    else:
        m_min, m_max = 48, 72
    for m in range(m_min, m_max + 1):
        if m % 12 in (1, 3, 6, 8, 10):  # teclas "negras"
            ax.axhspan(m - 0.5, m + 0.5, color=INK, alpha=0.05, linewidth=0)
    for (s, e, m) in notas:
        ax.add_patch(Rectangle((s, m - 0.4), e - s, 0.8, facecolor=GOLD,
                                edgecolor=INK, linewidth=0.6))
    ax.set_ylim(m_min, m_max)
    if t.size:
        ax.set_xlim(0, t[-1])
    _estilo_ejes(ax, "Piano-roll — contorno melódico estabilizado", ylabel="Nota MIDI")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def fig_respiracion(y, sr, path, umbral=0.012, min_gap=0.3):
    win = int(0.3 * sr / vr.HOP) | 1
    rms = librosa.feature.rms(y=y, frame_length=vr.FRAME, hop_length=vr.HOP)[0]
    rms_suave = np.convolve(rms, np.ones(win) / win, mode="same")
    t_rms = librosa.frames_to_time(np.arange(len(rms_suave)), sr=sr, hop_length=vr.HOP)

    bajo = rms_suave < umbral
    gaps = []
    i = 0
    while i < len(bajo):
        if bajo[i]:
            j = i
            while j < len(bajo) and bajo[j]:
                j += 1
            dur = t_rms[j - 1] - t_rms[i]
            if dur >= min_gap:
                gaps.append((t_rms[i], t_rms[j - 1]))
            i = j
        else:
            i += 1

    fig, ax = plt.subplots(figsize=(11, 5))
    _estilo_fig(fig)
    ax.plot(t_rms, rms_suave, color=INK, linewidth=1.1)
    ax.axhline(umbral, color=GOLD, linestyle="--", linewidth=0.9, alpha=0.7)
    for (s, e) in gaps:
        ax.axvspan(s, e, color=GOLD, alpha=0.22, linewidth=0)
    _estilo_ejes(ax, f"Energía (respiración) — {len(gaps)} pausas de respiro detectadas",
                 ylabel="RMS suavizado")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return gaps


def main():
    audio_path = sys.argv[1] if len(sys.argv) > 1 else AUDIO_DEFAULT
    os.makedirs(OUTDIR, exist_ok=True)

    y, sr = librosa.load(audio_path, sr=vr.SR, mono=True)
    dur = len(y) / sr
    print(f"[{audio_path}: {dur:.1f}s @ {sr}Hz]")

    calibrado = os.path.exists(CENTROIDES_PATH)
    centroids = vr.load_centroids(CENTROIDES_PATH)
    rumbos = vr.DEFAULT_RUMBOS
    events = vr.analyze_array(y, sr, centroids, rumbos)

    t = np.array([e[0] for e in events])
    hz = np.array([e[1] for e in events])
    midi = np.array([e[2] for e in events])
    vocal = [e[3] for e in events]
    onset = np.array([e[6] for e in events])
    onset_t = t[onset == 1]

    fig_forma_tono(y, sr, t, hz, onset_t, os.path.join(OUTDIR, "01_forma_tono.png"))
    fig_espectrograma(y, sr, os.path.join(OUTDIR, "02_espectrograma.png"))
    fig_vocales(t, vocal, hz, calibrado, os.path.join(OUTDIR, "03_vocales.png"))
    fig_piano_roll(t, midi, os.path.join(OUTDIR, "04_piano_roll.png"))
    gaps = fig_respiracion(y, sr, os.path.join(OUTDIR, "05_respiracion.png"))

    from collections import Counter
    voc_validas = [v for v in vocal if v]
    conteo_vocales = Counter(voc_validas)
    hz_validos = hz[hz > 0]
    n_silabas = int(onset.sum())

    resumen = f"""# Análisis del canto — {os.path.basename(audio_path)}

LI_CO STUDIO / Colectivo Tutú · "El canto de los rumbos"

## Datos generales
- Archivo: `{audio_path}`
- Duración: {dur:.1f} s
- Sample rate de análisis: {sr} Hz

## Tono
- f0 detectado en {len(hz_validos)} de {len(hz)} frames ({100*len(hz_validos)/max(1,len(hz)):.0f}%)
- Rango: {hz_validos.min():.0f}–{hz_validos.max():.0f} Hz (mediana {np.median(hz_validos):.0f} Hz)
  si hubo voz sonora detectada.

## Sílabas y vocales
- Sílabas (onsets) detectadas: {n_silabas}
- Distribución de vocales clasificadas: {dict(conteo_vocales)}

{"" if calibrado else '''**ADVERTENCIA — calibración provisional**: la clasificación de vocales
usa los centroides F1/F2 por defecto (`DEFAULT_VOWELS` en `voz_rumbos.py`),
NO calibrados con la voz real de Ramón. Antes de usar estos resultados para
decisiones artísticas, calibrar con:
`python src/voz_rumbos.py --calibrate a.wav e.wav i.wav ix.wav u.wav`'''}

## Respiración
- Pausas de respiro detectadas (energía sostenida por debajo del umbral): {len(gaps)}
- Duración de cada pausa (s): {[f"{e-s:.2f}" for s, e in gaps]}

## Figuras generadas
1. `01_forma_tono.png` — forma de onda + contorno de tono, con sílabas marcadas
2. `02_espectrograma.png` — espectrograma STFT (escala log)
3. `03_vocales.png` — vocales clasificadas en el tiempo (con advertencia de calibración)
4. `04_piano_roll.png` — contorno melódico estabilizado como piano-roll
5. `05_respiracion.png` — envolvente de energía con pausas de respiro señaladas

Estilo: tinta {INK} / oro {GOLD}, fondo blanco, 300dpi, etiquetas en español.
"""
    with open(os.path.join(OUTDIR, "resumen.md"), "w", encoding="utf-8") as f:
        f.write(resumen)

    print(f"→ {OUTDIR}\\ (5 figuras + resumen.md)")


if __name__ == "__main__":
    main()
