"""Wrapper sobre repos\\wixnlp\\wmorph.py (Mager 2016, GPLv3).

No reescribe el algoritmo de segmentacion; solo corrige problemas
mecanicos del original para poder importarlo desde fuera del repo:
raw strings en los regex "\\+", ruta "data/steam" parametrizada,
import de wixaffixes resuelto por sys.path en vez de import relativo,
y CRLF sin limpiar en data/steam (dejaba un "\\r" pegado a cada raiz,
por lo que ninguna raiz calzaba jamas).
"""

import os
import re
import sys
import codecs

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPOS_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "repos"))
_WIXNLP_DIR = os.path.join(_REPOS_DIR, "wixnlp")
_DEFAULT_STEAM_PATH = os.path.join(_WIXNLP_DIR, "data", "steam")

if _WIXNLP_DIR not in sys.path:
    sys.path.insert(0, _WIXNLP_DIR)

from wix.wixaffixes import pre, post  # noqa: E402


class Verb:
    """Copia patcheada de wmorph.Verb (mismo algoritmo, misma logica)."""

    def __init__(self, verb, steam_path=_DEFAULT_STEAM_PATH, debug=0):
        self.verb = verb.lower()
        self.paths = []
        self.roots = []
        self.debug = debug
        F = codecs.open(steam_path, mode="r", encoding="utf-8")
        line = F.readline()
        while 1:
            line = line.rstrip("\r\n")
            self.roots.append(line)
            line = F.readline()
            if not line:
                break
        self.start()

    def start(self, prev="", pos=0, path=[]):
        if pos > len(pre) - 1:
            return
        gotone = False
        for s in pre[pos]:
            s_reg = s.replace("+", r"\+")
            prev_reg = prev.replace("+", r"\+")
            reg = re.compile("^" + prev_reg + s_reg + "+")
            m = reg.match(self.verb)
            if m:
                gotone = True
                nprev = m.group()
                npath = list(path)
                npath.append(("" + str(pos) + "", s))
                self.start(nprev, pos + 1, npath)
                nprev = nprev.replace("+", r"\+")
                for root in self.roots:
                    root2 = root.replace("+", r"\+")
                    rootmatch = re.compile("^" + nprev + root2 + "+")
                    rm = rootmatch.match(self.verb)
                    if rm:
                        nrprev = rm.group()
                        nrpath = list(npath)
                        nrpath.append(("", root))
                        if len(self.verb) == len(nrprev):
                            self.paths.append(nrpath)
                        self.end(prev=nrprev, path=nrpath)
                        continue
        if not gotone:
            if pos > 17:
                return
            self.start(prev, pos + 1, path)
            return

    def end(self, prev="", pos=1, path=[]):
        if pos <= 0 or pos >= len(post):
            return
        if len(prev) == len(self.verb):
            return
        for s in post[-pos]:
            s_reg = s.replace("+", r"\+")
            prev_reg = prev.replace("+", r"\+")
            reg = re.compile("^" + prev_reg + s_reg + "+")
            m = reg.match(self.verb)
            if m:
                nprev = m.group()
                npath = list(path)
                npath.append(("-" + str(pos) + "", s))
                if len(self.verb) == len(nprev):
                    self.paths.append(npath)
                self.end(nprev, pos + 1, npath)
        self.end(prev, pos + 1, path)


# Plantilla posicional wixarika: 18 prefijos + raiz + 24 sufijos = 43 slots.
# slot = idx_prefijo + 1 (1-18) | 19 para la raiz | 19 + pos_sufijo (20-43).
DIRECCIONALES = sorted({morfema for grupo in pre[-5:] for morfema in grupo})


def _slot(label):
    if label == "":
        return 19
    if label.startswith("-"):
        return 19 + int(label[1:])
    return int(label) + 1


def segmentar(palabra):
    v = Verb(palabra)
    rutas = []
    for path in v.paths:
        morfemas = [m for _, m in path]
        slots = [_slot(label) for label, _ in path]
        direccionales = [m for m in morfemas if m in DIRECCIONALES]
        rutas.append({"morfemas": morfemas, "slots": slots, "direccionales": direccionales})

    if not rutas:
        return {"palabra": palabra, "morfemas": [], "slots": [], "direccionales": [], "rutas": []}

    preferida = min(rutas, key=lambda r: len(r["morfemas"]))
    return {
        "palabra": palabra,
        "morfemas": preferida["morfemas"],
        "slots": preferida["slots"],
        "direccionales": preferida["direccionales"],
        "rutas": rutas,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python wixmorph.py <palabra>")
        sys.exit(1)
    import json
    print(json.dumps(segmentar(sys.argv[1]), ensure_ascii=False, indent=2))
