"""Interfaz Gradio 3.50.2 para el dataset propio voz <-> texto <-> morfologia.

Regla 5 del brief: esta interfaz NUNCA genera wixarika. El campo de texto
es exactamente lo que Ramon/Hafo escribio a mano; nosotros solo corremos
segmentar() sobre esas palabras para anotar morfologia.
"""

import json
import os
import time
from datetime import datetime

import gradio as gr

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wixmorph import segmentar

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_RAMON = os.path.normpath(os.path.join(_THIS_DIR, "..", "data", "ramon"))
_AUTORIZADO_POR = "Ramón Carrillo"

os.makedirs(_DATA_RAMON, exist_ok=True)


def _listar_audios():
    exts = (".wav", ".mp3", ".flac", ".ogg", ".m4a")
    return sorted(f for f in os.listdir(_DATA_RAMON) if f.lower().endswith(exts))


def _ruta_alineacion(nombre_audio):
    base, _ = os.path.splitext(nombre_audio)
    return os.path.join(_DATA_RAMON, f"{base}.alineacion.json")


def refrescar_audios():
    audios = _listar_audios()
    return gr.Dropdown(choices=audios, value=(audios[0] if audios else None))


def cargar_audio(nombre_audio):
    if not nombre_audio:
        return None
    return os.path.join(_DATA_RAMON, nombre_audio)


def iniciar_marcado(texto):
    palabras = texto.split()
    estado = {"palabras": palabras, "idx": 0, "marcas": [], "t0": time.time()}
    palabra_actual = palabras[0] if palabras else "(sin texto)"
    return estado, palabra_actual, []


def marcar_palabra(estado):
    if not estado or estado["idx"] >= len(estado["palabras"]):
        return estado, "(fin del texto)", estado["marcas"] if estado else []
    t = round(time.time() - estado["t0"], 3)
    texto_palabra = estado["palabras"][estado["idx"]]
    estado["marcas"].append({"t": t, "texto": texto_palabra})
    estado["idx"] += 1
    palabra_actual = (
        estado["palabras"][estado["idx"]] if estado["idx"] < len(estado["palabras"]) else "(fin del texto)"
    )
    tabla = [[m["t"], m["texto"]] for m in estado["marcas"]]
    return estado, palabra_actual, tabla


def guardar_alineacion(nombre_audio, estado):
    if not nombre_audio:
        return "Selecciona un audio primero."
    if not estado or not estado["marcas"]:
        return "No hay marcas registradas todavía."

    palabras_out = []
    for marca in estado["marcas"]:
        seg = segmentar(marca["texto"])
        palabras_out.append({
            "t": marca["t"],
            "texto": marca["texto"],
            "morfemas": seg["morfemas"],
            "slots": seg["slots"],
        })

    registro = {
        "audio": nombre_audio,
        "autorizado_por": _AUTORIZADO_POR,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "palabras": palabras_out,
    }

    ruta = _ruta_alineacion(nombre_audio)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)

    return f"Guardado: {ruta}"


def borrar_entrada(nombre_audio):
    if not nombre_audio:
        return "Nada seleccionado.", refrescar_audios()

    ruta_audio = os.path.join(_DATA_RAMON, nombre_audio)
    ruta_json = _ruta_alineacion(nombre_audio)
    borrados = []
    if os.path.exists(ruta_audio):
        os.remove(ruta_audio)
        borrados.append(ruta_audio)
    if os.path.exists(ruta_json):
        os.remove(ruta_json)
        borrados.append(ruta_json)

    mensaje = "Borrado: " + ", ".join(borrados) if borrados else "No había nada que borrar."
    return mensaje, refrescar_audios()


with gr.Blocks(title="Alineación voz-texto-morfología — Canto de los rumbos") as demo:
    gr.Markdown("## Alineación voz ↔ texto ↔ morfología (dataset propio)")
    gr.Markdown(
        "El texto lo escribe Ramón/Hafo a mano. Esta herramienta solo segmenta "
        "morfológicamente lo ya escrito; nunca genera wixárika."
    )

    with gr.Row():
        audio_dropdown = gr.Dropdown(choices=_listar_audios(), label="Audio en data\\ramon\\")
        btn_refrescar = gr.Button("↻ Refrescar lista")

    audio_player = gr.Audio(label="Reproducir", type="filepath")
    texto_box = gr.Textbox(label="Texto (escrito por Ramón/Hafo)", lines=3)

    with gr.Row():
        btn_iniciar = gr.Button("▶ Iniciar marcado")
        btn_marcar = gr.Button("● Marca palabra (tap)")

    palabra_actual_box = gr.Textbox(label="Palabra actual", interactive=False)
    tabla_marcas = gr.Dataframe(headers=["t", "texto"], label="Marcas registradas")

    with gr.Row():
        btn_guardar = gr.Button("Guardar alineación")
        btn_borrar = gr.Button("BORRAR ENTRADA", variant="stop")

    estado_marcado = gr.State(None)
    mensaje_box = gr.Textbox(label="Estado", interactive=False)

    btn_refrescar.click(refrescar_audios, outputs=audio_dropdown)
    audio_dropdown.change(cargar_audio, inputs=audio_dropdown, outputs=audio_player)

    btn_iniciar.click(
        iniciar_marcado, inputs=texto_box, outputs=[estado_marcado, palabra_actual_box, tabla_marcas]
    )
    btn_marcar.click(
        marcar_palabra, inputs=estado_marcado, outputs=[estado_marcado, palabra_actual_box, tabla_marcas]
    )
    btn_guardar.click(guardar_alineacion, inputs=[audio_dropdown, estado_marcado], outputs=mensaje_box)
    btn_borrar.click(borrar_entrada, inputs=audio_dropdown, outputs=[mensaje_box, audio_dropdown])


if __name__ == "__main__":
    demo.launch()
