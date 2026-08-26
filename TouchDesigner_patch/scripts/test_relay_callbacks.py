# test_relay_callbacks.py
# Prueba standalone de relay_callbacks.py, sin TD. Corre con el Python de
# lico-studio: python TouchDesigner_patch/scripts/test_relay_callbacks.py
#
# Las funciones puras (calcular_ganancias, calcular_actualizacion) se prueban
# directo. Las funciones que usan `op`/`me`/`absTime` (propias de TD) se
# prueban con un harness mínimo que simula esos tres objetos.

import importlib.util
import math
import os
import sys


def _cargar_modulo():
    ruta = os.path.join(os.path.dirname(__file__), "relay_callbacks.py")
    spec = importlib.util.spec_from_file_location("relay_callbacks", ruta)
    mod = importlib.util.module_from_spec(spec)

    class _MeMock:
        def __init__(self):
            self._store = {}

        def fetch(self, key, default=None):
            return self._store.get(key, default)

        def store(self, key, val):
            self._store[key] = val

    class _AbsTimeMock:
        seconds = 0.0

    class _OpMock:
        def __call__(self, path):
            return None  # sin OSC Out DAT reales en la prueba

    class _ProjectMock:
        # TouchDesigner_patch/, como el .toe real — config.json vive un nivel arriba
        folder = os.path.dirname(os.path.dirname(__file__))

    mod.me = _MeMock()
    mod.absTime = _AbsTimeMock()
    mod.op = _OpMock()
    mod.project = _ProjectMock()
    spec.loader.exec_module(mod)
    return mod


def test_ganancias_potencia_constante(m):
    for angulo in range(0, 360, 5):
        for densidad in (0.0, 0.25, 0.5, 0.75, 1.0):
            g = m.calcular_ganancias(angulo, densidad)
            suma2 = sum(v ** 2 for v in g.values())
            assert abs(suma2 - 1.0) < 1e-9, f"potencia no constante en angulo={angulo} densidad={densidad}: {suma2}"
    print("OK: potencia constante (suma de cuadrados = 1) en toda la rejilla angulo x densidad")


def test_ganancias_bocinas_cardinales(m):
    casos = {0.0: "FL", 90.0: "FR", 180.0: "BR", 270.0: "BL"}
    for angulo, bocina in casos.items():
        g = m.calcular_ganancias(angulo, 0.0)
        assert abs(g[bocina] - 1.0) < 1e-9, f"esperaba {bocina}=1.0 en angulo={angulo}, dio {g}"
        otras = [v for k, v in g.items() if k != bocina]
        assert all(v < 1e-9 for v in otras), f"esperaba las otras 3 en 0 en angulo={angulo}, dio {g}"
    print("OK: en los 4 ángulos cardinales, toda la potencia va a la bocina correspondiente")


def test_ganancias_mitad_camino(m):
    g = m.calcular_ganancias(45.0, 0.0)
    assert abs(g["FL"] - g["FR"]) < 1e-9, f"esperaba FL==FR a 45°, dio {g}"
    assert abs(g["FL"] - math.sqrt(0.5)) < 1e-9
    print("OK: a 45° (mitad entre FL y FR), ambas bocinas reciben la misma ganancia (~0.707)")


def test_ganancias_densidad_maxima(m):
    for angulo in (0.0, 37.0, 200.0):
        g = m.calcular_ganancias(angulo, 1.0)
        for v in g.values():
            assert abs(v - 0.5) < 1e-9, f"esperaba 0.5 parejo con densidad=1, dio {g}"
    print("OK: densidad=1.0 reparte las 4 bocinas parejo (0.5 cada una) sin importar el ángulo")


def test_silaba_avanza_angulo_fuente_c(m):
    m.inicializar()
    assert m.me.fetch("paneo_estado")["fuente"] == "C"
    for _ in range(3):
        m.onReceiveOSC(None, 0, "", 0, 0, "/voz/silaba", [1], None)
    paneo = m.me.fetch("paneo_estado")
    assert paneo["angulo"] == 3 * m.PANEO_PASO_SILABA_DEG, paneo
    assert paneo["densidad"] == 1.0, paneo
    print(f"OK: 3 sílabas en fuente C avanzan el ángulo a {paneo['angulo']}° y suben densidad a 1.0")


def test_fuente_manual_no_avanza_angulo(m):
    m.inicializar()
    m.onReceiveOSC(None, 0, "", 0, 0, "/paneo/fuente", ["F"], None)
    m.onReceiveOSC(None, 0, "", 0, 0, "/paneo/manual", [123.0], None)
    angulo_antes = m.me.fetch("paneo_estado")["angulo"]
    m.onReceiveOSC(None, 0, "", 0, 0, "/voz/silaba", [1], None)
    paneo = m.me.fetch("paneo_estado")
    assert paneo["angulo"] == angulo_antes, "en modo F el ángulo automático no debería congelarse, pero tampoco lo usa tick() como salida directa"
    assert paneo["manual_angulo"] == 123.0
    print("OK: /paneo/fuente F y /paneo/manual se guardan correctamente; el ángulo base sigue de referencia interna")


def test_densidad_decae_en_tick(m):
    m.inicializar()
    m.onReceiveOSC(None, 0, "", 0, 0, "/voz/silaba", [1], None)
    assert m.me.fetch("paneo_estado")["densidad"] == 1.0
    m.absTime.seconds = 1.0
    for _ in range(50):
        m.tick()
        m.absTime.seconds += 0.1  # bien por encima de 1/THROTTLE_HZ, evita el borde de redondeo del throttle
    densidad_final = m.me.fetch("paneo_estado")["densidad"]
    assert densidad_final < 0.05, f"esperaba que la densidad decayera cerca de 0, quedó en {densidad_final}"
    print(f"OK: densidad decae de 1.0 a {densidad_final:.4f} tras 50 ticks sin nuevas sílabas")


def test_tracks_fuente_solo_ramon(m):
    assert m.TRACKS_FUENTE == [2], f"esperaba que el paneo solo toque la track de Ramón (índice 2), dio {m.TRACKS_FUENTE}"
    print("OK: TRACKS_FUENTE apunta solo a la track de Ramón (índice 2), independiente del resto")


def test_codigo_runcode_es_python_valido(m):
    codigo = m._PANEO_CODIGO.format(fl=0.1234, fr=0.5678, bl=0.9, br=0.0, tracks=(0, 1, 2, 3, 4))
    compile(codigo, "<paneo>", "exec")  # lanza SyntaxError si el template quedó mal formado
    assert "0.1234" in codigo and "(0, 1, 2, 3, 4)" in codigo
    print("OK: el código Python generado para /shell/runCode compila y trae los valores esperados")


def test_tracks_formante_apunta_a_vital(m):
    assert m.TRACKS_FORMANTE == [0, 1], f"esperaba 1-Vital/2-Vital (índices 0,1), dio {m.TRACKS_FORMANTE}"
    print("OK: TRACKS_FORMANTE apunta a 1-Vital/2-Vital (índices 0 y 1)")


def test_formante_device_index_confirmado(m):
    assert m.FORMANTE_DEVICE_INDEX == 1, f"esperaba el EQ Eight en el índice 1 (después de Vital), dio {m.FORMANTE_DEVICE_INDEX}"
    assert m.FORMANTE_PARAM_FREQ == {1: (6, 11), 2: (16, 21)}, m.FORMANTE_PARAM_FREQ
    print("OK: FORMANTE_DEVICE_INDEX y FORMANTE_PARAM_FREQ confirmados en vivo contra el EQ Eight real")


def test_formante_tick_no_crashea_con_device_confirmado(m):
    m.inicializar()
    m.onReceiveOSC(None, 0, "", 0, 0, "/voz/vocal", ["a", 0, 1], None)
    m.absTime.seconds = 1.0
    for _ in range(10):
        m.tick()  # no debe lanzar excepción con FORMANTE_DEVICE_INDEX confirmado (ableton_activo sigue False en la prueba)
        m.absTime.seconds += 0.1
    print("OK: tick() no lanza excepción calculando/formateando el código de Fase F")


def test_hz_a_normalizado_calibrado_en_vivo(m):
    # Puntos medidos a mano contra el EQ Eight real (2026-08-26): 10Hz,
    # 469Hz y 22000Hz en t=0.0/0.5/1.0. No es una fórmula de memoria.
    assert abs(m.hz_a_normalizado(10.0) - 0.0) < 1e-6
    assert abs(m.hz_a_normalizado(469.0) - 0.5) < 2e-3
    assert abs(m.hz_a_normalizado(22000.0) - 1.0) < 1e-6
    print("OK: hz_a_normalizado() reproduce los tres puntos calibrados en vivo (10/469/22000 Hz)")


def test_formante_lookup_por_vocal(m):
    # Directo contra calcular_actualizacion (pura) con una tabla explícita,
    # sin pasar por inicializar()/vocales_ramon.json real — así la prueba no
    # se rompe el día que Ramón calibre de verdad.
    formantes = dict(m.FORMANTES_DEFAULT)
    estado = dict(m.ESTADO_INICIAL); estado["energia"] = dict(estado["energia"])
    for vocal, f1f2 in formantes.items():
        estado = m.calcular_actualizacion(estado, "/voz/vocal", [vocal, 0, 0], formantes)
        assert estado["formante"] == f1f2, f"vocal={vocal}: esperaba {f1f2}, dio {estado['formante']}"
    print("OK: cada vocal actualiza el formante objetivo a su F1/F2 en la tabla dada")


def test_formante_mantiene_ultimo_sin_clasificar(m):
    formantes = dict(m.FORMANTES_DEFAULT)
    estado = dict(m.ESTADO_INICIAL); estado["energia"] = dict(estado["energia"])
    estado = m.calcular_actualizacion(estado, "/voz/vocal", ["u", 4, 4], formantes)
    antes = estado["formante"]
    assert antes == formantes["u"]
    estado = m.calcular_actualizacion(estado, "/voz/vocal", ["", -1, -1], formantes)
    despues = estado["formante"]
    assert despues == antes, "sin clasificación, el formante no debería resetear a None ni cambiar"
    print("OK: sin vocal clasificada, se mantiene el último formante en vez de cortar a silencio")


def test_cargar_formantes_default_sin_archivo(m):
    import tempfile
    with tempfile.TemporaryDirectory() as vacio:
        formantes = m.cargar_formantes(vacio)
    assert formantes == m.FORMANTES_DEFAULT
    print("OK: cargar_formantes() usa FORMANTES_DEFAULT cuando no existe vocales_ramon.json")


def test_codigo_formante_es_python_valido(m):
    t1 = m.hz_a_normalizado(700.0)
    t2 = m.hz_a_normalizado(1300.0)
    codigo = m._FORMANTE_CODIGO.format(tracks=tuple(m.TRACKS_FORMANTE), device_index=m.FORMANTE_DEVICE_INDEX,
                                        params_f1=m.FORMANTE_PARAM_FREQ[1], params_f2=m.FORMANTE_PARAM_FREQ[2],
                                        t1=t1, t2=t2)
    compile(codigo, "<formante>", "exec")
    assert f"{t1:.6f}" in codigo and "(6, 11)" in codigo and "(16, 21)" in codigo
    print("OK: el código Python generado para el EQ Eight de Fase F compila y trae los valores esperados")


if __name__ == "__main__":
    m = _cargar_modulo()
    test_ganancias_potencia_constante(m)
    test_ganancias_bocinas_cardinales(m)
    test_ganancias_mitad_camino(m)
    test_ganancias_densidad_maxima(m)
    test_silaba_avanza_angulo_fuente_c(m)
    test_fuente_manual_no_avanza_angulo(m)
    test_densidad_decae_en_tick(m)
    test_tracks_fuente_solo_ramon(m)
    test_codigo_runcode_es_python_valido(m)
    test_tracks_formante_apunta_a_vital(m)
    test_formante_device_index_confirmado(m)
    test_formante_tick_no_crashea_con_device_confirmado(m)
    test_hz_a_normalizado_calibrado_en_vivo(m)
    test_formante_lookup_por_vocal(m)
    test_formante_mantiene_ultimo_sin_clasificar(m)
    test_cargar_formantes_default_sin_archivo(m)
    test_codigo_formante_es_python_valido(m)
    print("\nTODAS LAS PRUEBAS PASARON")
