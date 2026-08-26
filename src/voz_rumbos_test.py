# voz_rumbos_test.py
# Prueba de regresión standalone de Fase D-bis: confirma que CLASE_VOCAL
# sigue clasificando como antes de restaurar el rumbo, y que el rumbo
# nuevo se calcula correctamente por vocal. Corre con el Python de
# lico-studio: python src/voz_rumbos_test.py

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voz_rumbos as vr


def test_clase_vocal_sin_cambios():
    esperado = {"a": 0, "e": 1, "i": 2, "+": 3, "u": 4}
    assert vr.CLASE_VOCAL == esperado, f"CLASE_VOCAL cambió: {vr.CLASE_VOCAL}"
    print("OK: CLASE_VOCAL sigue igual a como quedó en Fase D")


def test_default_rumbos_fijo_ix_centro():
    assert vr.DEFAULT_RUMBOS["+"] == 0, "ɨ ('+') debe ser siempre 0 (centro) por diseño"
    print("OK: DEFAULT_RUMBOS trae ɨ ('+') fijo en 0 (centro)")


def test_parse_rumbos_default_es_neutro():
    r = vr.parse_rumbos(None)
    assert r == vr.DEFAULT_RUMBOS
    assert set(r.keys()) == {"a", "e", "i", "u", "+"}
    print(f"OK: parse_rumbos(None) devuelve el default neutro: {r}")


def test_parse_rumbos_configurable_por_montaje():
    r = vr.parse_rumbos([4, 3, 2, 1])
    assert r == {"a": 4, "e": 3, "i": 2, "u": 1, "+": 0}, r
    print(f"OK: parse_rumbos configura a/e/i/u por montaje, ɨ sigue fijo en 0: {r}")


def test_analyze_array_emite_clase_y_rumbo_juntos():
    import numpy as np
    centroids = dict(vr.DEFAULT_VOWELS)
    rumbos = vr.parse_rumbos(None)
    sr = vr.SR
    dur = 0.3
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    f1, f2 = centroids["a"]
    y = (0.5 * np.sin(2 * np.pi * 110 * t)
         + 0.2 * np.sin(2 * np.pi * f1 * t)
         + 0.1 * np.sin(2 * np.pi * f2 * t)).astype(np.float32)
    events = vr.analyze_array(y, sr, centroids, rumbos)
    con_vocal = [e for e in events if e[3]]
    assert con_vocal, "no se clasificó ninguna vocal en la señal sintética de prueba"
    for (_t, _hz, _midi, vocal, clase, rumbo, _onset) in con_vocal:
        assert clase == vr.CLASE_VOCAL.get(vocal, -1), (vocal, clase)
        assert rumbo == rumbos.get(vocal, -1), (vocal, rumbo)
    print(f"OK: analyze_array() produce clase y rumbo consistentes juntos ({len(con_vocal)} frames con vocal)")


if __name__ == "__main__":
    test_clase_vocal_sin_cambios()
    test_default_rumbos_fijo_ix_centro()
    test_parse_rumbos_default_es_neutro()
    test_parse_rumbos_configurable_por_montaje()
    test_analyze_array_emite_clase_y_rumbo_juntos()
    print("\nTODAS LAS PRUEBAS PASARON")
