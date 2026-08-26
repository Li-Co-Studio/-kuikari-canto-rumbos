"""osc_targets.py — config central de destinos OSC (config.json).

Un solo lugar para resolver nombres de destino ("td", "esteban", ...) a
clientes OSC listos para usar, compartido por voz_rumbos.py y telar_osc.py.
"""

import json
import os
import sys

from pythonosc.udp_client import SimpleUDPClient

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")


def cargar_config(path=None):
    path = path or CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _es_placeholder(spec):
    return "[" in spec


def clientes(nombres, config=None):
    """nombres: lista de claves de config['targets'] (ej. ["td", "esteban"]).
    Devuelve lista de SimpleUDPClient; ignora (con warning) targets ausentes,
    mal formados o con placeholder [IP_*] sin resolver."""
    config = config or cargar_config()
    targets = config.get("targets", {})
    out = []
    for nombre in nombres:
        spec = targets.get(nombre)
        if not spec:
            print(f"[osc_targets] destino desconocido: {nombre!r} (no está en config.json)", file=sys.stderr)
            continue
        if _es_placeholder(spec):
            print(f"[osc_targets] {nombre!r} sin resolver ({spec}) — ignorado hasta que se dé la IP real", file=sys.stderr)
            continue
        host, puerto = spec.split(":")
        out.append(SimpleUDPClient(host, int(puerto)))
    return out
