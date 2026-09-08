# afinacion_wixa_test.py
# Prueba de regresión standalone de Fase A: valida medición de f0 sobre
# tonos sintéticos antes de confiar el resultado a grabaciones reales del
# xaweri. Corre con el Python de lico-studio: python src/afinacion_wixa_test.py

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afinacion_wixa as aw


def _wav_tono(path, hz, dur=1.0, sr=aw.SR):
    import numpy as np
    import soundfile as sf
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    y = (0.6 * np.sin(2 * np.pi * hz * t)).astype("float32")
    sf.write(path, y, sr)


def _wav_dos_tonos(path, hz_a, hz_b, dur_cada=1.0, sr=aw.SR):
    import numpy as np
    import soundfile as sf
    t = np.linspace(0, dur_cada, int(sr * dur_cada), endpoint=False)
    a = 0.6 * np.sin(2 * np.pi * hz_a * t)
    b = 0.6 * np.sin(2 * np.pi * hz_b * t)
    y = np.concatenate([a, b]).astype("float32")
    sf.write(path, y, sr)


def _wav_tomas(path, hzs, dur=1.0, silencio=0.6, sr=aw.SR):
    """Varias tomas del mismo archivo, separadas por silencio real —
    replica la estructura de las grabaciones reales de calibración."""
    import numpy as np
    import soundfile as sf
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    hueco = np.zeros(int(sr * silencio), dtype=np.float32)
    partes = []
    for hz in hzs:
        partes.append((0.6 * np.sin(2 * np.pi * hz * t)).astype("float32"))
        partes.append(hueco)
    y = np.concatenate(partes[:-1])
    sf.write(path, y, sr)


def _wav_toma_con_evento_interno(path, hz_a, hz_b, dur_a=0.3, dur_b=0.6, hueco_interno=0.15, sr=aw.SR):
    """Una sola toma (silencio interno corto, no llega al umbral de
    voz_rumbos.detectar_tomas) con DOS eventos de arco distintos adentro —
    replica el caso real de UTA/NAUKA: una nota breve, una pausa de
    rearticulación, y otra nota — para que runs_estables() los separe."""
    import numpy as np
    import soundfile as sf
    ta = np.linspace(0, dur_a, int(sr * dur_a), endpoint=False)
    tb = np.linspace(0, dur_b, int(sr * dur_b), endpoint=False)
    hueco = np.zeros(int(sr * hueco_interno), dtype=np.float32)
    a = (0.6 * np.sin(2 * np.pi * hz_a * ta)).astype("float32")
    b = (0.6 * np.sin(2 * np.pi * hz_b * tb)).astype("float32")
    y = np.concatenate([a, hueco, b])
    sf.write(path, y, sr)


def test_etiqueta_cuerda_desde_nombre_de_archivo():
    assert aw.etiqueta_cuerda("Violin_cuerda_01_XEWI.wav") == "XEWI"
    assert aw.etiqueta_cuerda("cuerda_NAUKA.wav") == "NAUKA"
    print("OK: etiqueta_cuerda() lee el nombre wixárika del tramo final del archivo")


def test_etiqueta_pasaje_es_el_nombre_sin_extension():
    assert aw.etiqueta_pasaje("Tonada_01.wav") == "Tonada_01"
    print("OK: etiqueta_pasaje() usa el nombre de archivo sin extensión")


def test_medir_cuerda_detecta_tono_sintetico():
    hz_objetivo = 196.0  # ~G3
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cuerda_XEWI.wav")
        _wav_tono(p, hz_objetivo)
        m = aw.medir_cuerda(p)
    assert m is not None, "no se detectó señal en el tono sintético"
    assert abs(m["hz"] - hz_objetivo) < 5, m
    assert m["nota"].startswith("G"), m
    print(f"OK: medir_cuerda() detecta {hz_objetivo}Hz sintético como {m['hz']:.1f}Hz ({m['nota']})")


def test_medir_pasaje_reporta_rango_y_grados():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "tonada_test.wav")
        _wav_dos_tonos(p, 220.0, 440.0)  # una octava, A3 → A4
        m = aw.medir_pasaje(p)
    assert m is not None, "no se detectó señal en el pasaje sintético"
    assert m["hz_min"] < 300 < m["hz_max"] < 500 or m["hz_max"] > 400, m
    notas = {g["nota"] for g in m["grados_frecuentes"]}
    assert any(n.startswith("A") for n in notas), m
    print(f"OK: medir_pasaje() reporta rango {m['hz_min']:.0f}-{m['hz_max']:.0f}Hz y grados {notas}")


def test_medir_cuerda_detecta_tomas_consistentes():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cuerda_UTA.wav")
        _wav_tomas(p, [196.0, 196.0, 196.0])
        m = aw.medir_cuerda(p)
    assert m is not None
    assert m["n_tomas_usadas"] == 3, m
    assert m["consistente"] is True, m
    print(f"OK: medir_cuerda() con 3 tomas iguales → consistente=True, dispersión={m['dispersion_hz']}Hz")


def test_medir_cuerda_avisa_tomas_inconsistentes():
    """Reproduce el caso real que se pasó por alto la primera vez: un
    archivo de 'cuerda al aire' cuyas tomas no coinciden entre sí
    (registro distinto) no debe promediarse en silencio — debe marcarse
    consistente=False para forzar una revisión."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cuerda_NAUKA.wav")
        _wav_tomas(p, [643.7, 643.7, 321.9])  # dos tomas en E5, una en E4
        m = aw.medir_cuerda(p)
    assert m is not None
    assert m["n_tomas_usadas"] == 3, m
    assert m["consistente"] is False, m
    assert m["dispersion_hz"] > 100, m
    print(f"OK: medir_cuerda() detecta tomas inconsistentes (dispersión={m['dispersion_hz']}Hz) y NO las esconde en el promedio")


def test_runs_estables_separa_dos_eventos_dentro_de_una_toma():
    """Caso real que causó la dispersión de UTA: el arco no 'se apaga en
    ruido', hay una segunda nota distinta pegada a la primera dentro de
    la misma toma (silencio interno demasiado corto para que
    detectar_tomas() las separe)."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cuerda_UTA.wav")
        _wav_toma_con_evento_interno(p, 160.0, 643.7, dur_a=0.3, dur_b=0.6)
        import librosa
        y, sr = librosa.load(p, sr=aw.SR, mono=True)
        tomas = aw.vr.detectar_tomas(y, sr)
        assert len(tomas) == 1, tomas  # el hueco interno NO debe leerse como separación de toma
        f0, mask, n = aw.f0_contour(y, sr)
        runs = aw.runs_estables(f0, mask, aw.HOP, sr)
    assert len(runs) >= 2, runs
    hz_vistos = sorted(r["hz"] for r in runs)
    assert any(abs(h - 160.0) < 5 for h in hz_vistos), runs
    assert any(abs(h - 643.7) < 10 for h in hz_vistos), runs
    print(f"OK: runs_estables() separa los dos eventos de arco dentro de una sola toma: {[(r['hz'], r['dur']) for r in runs]}")


def test_medir_cuerda_usa_el_tramo_mas_largo_dentro_de_la_toma():
    """El evento MÁS LARGO dentro de la toma es el que se reporta —
    coincide con el caso real de NAUKA (Hafo confirmó por oído que la
    nota sostenida más larga, no la breve inicial, es la cuerda correcta)."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cuerda_NAUKA.wav")
        _wav_toma_con_evento_interno(p, 321.9, 643.7, dur_a=0.3, dur_b=0.9)
        m = aw.medir_cuerda(p)
    assert m is not None
    assert abs(m["hz"] - 643.7) < 10, m
    print(f"OK: medir_cuerda() usa el tramo más largo dentro de la toma ({m['hz']:.1f}Hz), no el primero")


def test_medir_cuerda_marca_toma_ambigua_cuando_los_tramos_empatan():
    """Caso real de UTA toma 2: dos tramos de duración casi igual —
    'usar el más largo' ahí es casi una moneda al aire y debe marcarse,
    no reportarse con la misma confianza que una toma sin empate."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cuerda_UTA.wav")
        _wav_toma_con_evento_interno(p, 160.0, 643.7, dur_a=0.66, dur_b=0.70)
        m = aw.medir_cuerda(p)
    assert m is not None
    ambiguas = [t["toma"] for t in m["detalle_tomas"] if t["ambigua"]]
    assert ambiguas == [1], m["detalle_tomas"]
    print(f"OK: medir_cuerda() marca ambigua la toma con dos tramos de duración casi igual")


def test_excluir_toma_por_decision_humana():
    """NAUKA toma 3: ejecución confirmada por oído como incorrecta, no un
    problema de medición — debe poder excluirse explícitamente y quedar
    documentado, sin que el algoritmo la 'arregle' solo."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cuerda_NAUKA.wav")
        _wav_tomas(p, [643.7, 643.7, 321.9])
        m = aw.medir_cuerda(p, excluir_tomas={3})
    assert m is not None
    assert m["n_tomas_usadas"] == 2, m
    assert abs(m["hz"] - 643.7) < 5, m
    assert m["consistente"] is True, m
    excluidas = [t["toma"] for t in m["detalle_tomas"] if t["excluida"]]
    assert excluidas == [3], excluidas
    print(f"OK: excluir_tomas={{3}} → NAUKA queda en {m['hz']:.1f}Hz con toma 3 marcada excluida, no promediada")


def test_parse_excluir_tomas():
    d = aw.parse_excluir_tomas(["NAUKA:3", "uta:2"])
    assert d == {"NAUKA": {3}, "UTA": {2}}, d
    print(f"OK: parse_excluir_tomas() lee 'ETIQUETA:N' sin importar mayúsculas: {d}")


def test_medir_pasaje_reporta_grado_dominante_por_toma():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "tonada_tomas.wav")
        _wav_tomas(p, [220.0, 440.0, 220.0])  # A3, A4, A3
        m = aw.medir_pasaje(p)
    assert m is not None
    assert len(m["grado_dominante_por_toma"]) == 3, m
    assert all(n.startswith("A") for n in m["grado_dominante_por_toma"]), m
    print(f"OK: medir_pasaje() reporta grado dominante por toma: {m['grado_dominante_por_toma']}")


def test_cmd_calibrar_escribe_json_con_ambas_secciones():
    with tempfile.TemporaryDirectory() as d:
        p_cuerda = os.path.join(d, "cuerda_UTA.wav")
        _wav_tono(p_cuerda, 293.7)  # ~D4
        p_pasaje = os.path.join(d, "tonada_x.wav")
        _wav_dos_tonos(p_pasaje, 293.7, 349.2)
        out = os.path.join(d, "afinacion_test.json")
        aw.cmd_calibrar([p_cuerda], [p_pasaje], out)
        import json
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
    assert data["instrumento"] == "xaweri"
    assert "UTA" in data["cuerdas_al_aire"]
    assert "tonada_x" in data["pasajes"]
    print("OK: cmd_calibrar() escribe afinacion_ramon.json con cuerdas_al_aire y pasajes")


if __name__ == "__main__":
    test_etiqueta_cuerda_desde_nombre_de_archivo()
    test_etiqueta_pasaje_es_el_nombre_sin_extension()
    test_medir_cuerda_detecta_tono_sintetico()
    test_medir_pasaje_reporta_rango_y_grados()
    test_medir_cuerda_detecta_tomas_consistentes()
    test_medir_cuerda_avisa_tomas_inconsistentes()
    test_runs_estables_separa_dos_eventos_dentro_de_una_toma()
    test_medir_cuerda_usa_el_tramo_mas_largo_dentro_de_la_toma()
    test_medir_cuerda_marca_toma_ambigua_cuando_los_tramos_empatan()
    test_excluir_toma_por_decision_humana()
    test_parse_excluir_tomas()
    test_medir_pasaje_reporta_grado_dominante_por_toma()
    test_cmd_calibrar_escribe_json_con_ambas_secciones()
    print("\nTODAS LAS PRUEBAS PASARON")
