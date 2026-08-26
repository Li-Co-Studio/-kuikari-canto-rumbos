"""Indice de busqueda espanol -> wixarika sobre pares existentes.

Esta funcion RECUPERA pares (wix, es) ya presentes en el corpus.
Jamas compone wixarika nuevo (regla 5 del brief).

Fuentes: largecorpus.wixes (formato "wix = es") y other/dictionary.wixes
(formato "wix=es"). Se ignoran corp-dev/test/train (ver nota abajo) y la
carpeta bible/ (decision de Ramon).

Nota verificada: corp-dev.es / corp-dev.wix estan intercambiados (el .es
trae texto en wixarika y el .wix trae espanol). Por eso el indice se
construye solo desde largecorpus.wixes + dictionary.wixes.
"""

import argparse
import os
import pickle

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPOS_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "repos"))
_DATA_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "data"))

_LARGECORPUS_PATH = os.path.join(_REPOS_DIR, "wixarikacorpora", "parallel-corp", "largecorpus.wixes")
_DICTIONARY_PATH = os.path.join(_REPOS_DIR, "wixarikacorpora", "other", "dictionary.wixes")
_INDICE_PATH = os.path.join(_DATA_DIR, "corpus", "indice.pkl")


def _cargar_pares(path):
    pares = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if "=" not in line:
                continue
            wix, es = line.split("=", 1)
            wix, es = wix.strip(), es.strip()
            if wix and es:
                pares.append((wix, es))
    return pares


def _construir_indice():
    pares = _cargar_pares(_LARGECORPUS_PATH) + _cargar_pares(_DICTIONARY_PATH)
    textos_es = [es for _, es in pares]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
    matriz = vectorizer.fit_transform(textos_es)
    return {"pares": pares, "vectorizer": vectorizer, "matriz": matriz}


def _cargar_o_construir_indice():
    if os.path.exists(_INDICE_PATH):
        with open(_INDICE_PATH, "rb") as f:
            return pickle.load(f)
    indice = _construir_indice()
    os.makedirs(os.path.dirname(_INDICE_PATH), exist_ok=True)
    with open(_INDICE_PATH, "wb") as f:
        pickle.dump(indice, f)
    return indice


_INDICE = None


def _indice():
    global _INDICE
    if _INDICE is None:
        _INDICE = _cargar_o_construir_indice()
    return _INDICE


def buscar(consulta, k=5, candidatos_tfidf=30):
    idx = _indice()
    vec = idx["vectorizer"].transform([consulta])
    similitudes = cosine_similarity(vec, idx["matriz"])[0]
    top_tfidf = similitudes.argsort()[::-1][:candidatos_tfidf]

    resultados = []
    for i in top_tfidf:
        wix, es = idx["pares"][i]
        score = fuzz.ratio(consulta, es) / 100.0
        resultados.append({"wix": wix, "es": es, "score": score})

    resultados.sort(key=lambda r: r["score"], reverse=True)
    return resultados[:k]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", required=True, help="frase en espanol a buscar")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    import json
    print(json.dumps(buscar(args.test, k=args.k), ensure_ascii=False, indent=2))
