"""Motor de sonificacion: morfemas -> OSC.

Entrada: el dict que devuelve wixmorph.segmentar() o corpus_index.buscar().
Salida: mensajes OSC hacia TouchDesigner (127.0.0.1:7000) y Ableton /
producer-pal (127.0.0.1:7001), en la convencion /telar/* que comparte
el proyecto con voz_rumbos.py (este emite /voz/* en los mismos puertos).
"""

import argparse
import time

from pythonosc.udp_client import SimpleUDPClient

PUERTO_TD = 7000
PUERTO_ABLETON = 7001


class TelarOSC:
    def __init__(self, host="127.0.0.1", puerto_td=PUERTO_TD, puerto_ableton=PUERTO_ABLETON, bpm=60, targets=None):
        """targets: lista de nombres de config.json (ej. ["td", "esteban"]).
        Si se da, reemplaza el par host/puerto_td/puerto_ableton de siempre."""
        if targets:
            import os
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import osc_targets
            self.clientes = osc_targets.clientes(targets)
        else:
            self.clientes = [SimpleUDPClient(host, puerto_td), SimpleUDPClient(host, puerto_ableton)]
        self.bpm = bpm

    def _enviar(self, direccion, *args):
        for cliente in self.clientes:
            cliente.send_message(direccion, list(args))

    def emitir_palabra(self, resultado_segmentar):
        texto = resultado_segmentar["palabra"]
        morfemas = resultado_segmentar["morfemas"]
        slots = resultado_segmentar["slots"]
        direccionales = set(resultado_segmentar["direccionales"])

        self._enviar("/telar/palabra", texto, len(morfemas))
        for idx, (morfema, slot) in enumerate(zip(morfemas, slots)):
            es_direccional = 1 if morfema in direccionales else 0
            self._enviar("/telar/morfema", idx, morfema, slot, es_direccional)
            if es_direccional:
                self._enviar("/telar/direccional", morfema)
        self._enviar("/telar/fin", texto)

    def secuenciar_palabra(self, resultado_segmentar):
        """Emite morfemas al ritmo de self.bpm; un slot = un paso, slots vacios = silencio."""
        texto = resultado_segmentar["palabra"]
        morfemas = resultado_segmentar["morfemas"]
        slots = resultado_segmentar["slots"]
        direccionales = set(resultado_segmentar["direccionales"])
        paso_seg = 60.0 / self.bpm

        self._enviar("/telar/palabra", texto, len(morfemas))
        if not slots:
            self._enviar("/telar/fin", texto)
            return

        idx = 0
        for slot in range(min(slots), max(slots) + 1):
            if idx < len(slots) and slots[idx] == slot:
                morfema = morfemas[idx]
                es_direccional = 1 if morfema in direccionales else 0
                self._enviar("/telar/morfema", idx, morfema, slot, es_direccional)
                if es_direccional:
                    self._enviar("/telar/direccional", morfema)
                idx += 1
            time.sleep(paso_seg)
        self._enviar("/telar/fin", texto)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="emite una palabra de prueba a TD/Ableton")
    parser.add_argument("--palabra", default="pakamie")
    parser.add_argument("--bpm", type=int, default=60)
    parser.add_argument("--secuenciador", action="store_true")
    parser.add_argument("--targets", help='nombres de config.json, ej. "td,esteban" (reemplaza TD/Ableton fijos)')
    args = parser.parse_args()

    if args.demo:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from wixmorph import segmentar

        targets = [n.strip() for n in args.targets.split(",")] if args.targets else None
        resultado = segmentar(args.palabra)
        telar = TelarOSC(bpm=args.bpm, targets=targets)
        if args.secuenciador:
            telar.secuenciar_palabra(resultado)
        else:
            telar.emitir_palabra(resultado)
        destino = ",".join(targets) if targets else f"puertos {PUERTO_TD}/{PUERTO_ABLETON}"
        print(f"Emitido '{args.palabra}' -> {resultado['morfemas']} en {destino}")
