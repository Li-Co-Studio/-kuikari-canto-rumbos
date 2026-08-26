# Kuikari Iyari — canto-rumbos

Sistema en vivo que escucha el canto wixárika de Ramón Carrillo, lo
analiza en tiempo real (f0, vocal, sílaba) y distribuye ese análisis por
OSC hacia TouchDesigner, Ableton Live (paneo cuadrafónico), Resolume y
Blender, para una instalación/performance montada en Sala Memorial.

Dossier completo (contexto artístico y curatorial): *[link al PDF en
Drive — pendiente]*.

## Qué está verificado (no solo implementado)

- **Segmentación morfológica wixárika** (`wixmorph.py`, sobre
  `wixnlp`/`pywirrarika`): 90% de coincidencia exacta (9/10) contra
  palabras reales de `segcorpus.wixes`.
- **Paneo cuadrafónico end-to-end con audio real**: `voz_rumbos.py`
  corriendo sobre una grabación real de Ramón → TouchDesigner (relay) →
  Ableton Live. Verificado leyendo directamente los 4 *sends* reales de
  la track en Ableton (no solo el mensaje de éxito de un script):
  ángulo y ganancias esperadas coincidieron exactamente con lo medido.
- **Clasificación vocal + rumbo espacial emitidos juntos por OSC**
  (`/voz/vocal [vocal, clase, rumbo]`), con suite de pruebas de
  regresión propia.
- Reparto de fases documentado en `docs/KUIKARI_estado_del_proyecto.md`
  (fila D: retiro/reintroducción del rumbo espacial; fila E: motor de
  paneo en Ableton) y bitácora completa de decisiones y verificaciones
  en `docs/BITACORA_SETUP.md`.

## Estructura

```
src/                    Análisis de voz, segmentación wixárika, utilidades OSC
scripts/analisis_canto.py   Reporte offline (figuras + resumen) sobre un audio
TouchDesigner_patch/scripts/  Callbacks del patch: dispatcher, relay, telar visual
docs/                   Especificación OSC, bitácora, atribución, guías de montaje
```

## Cómo correrlo

Entorno: conda `lico-studio` (Python 3.10), CPU (sin CUDA — no aplica
para este módulo).

```
conda activate lico-studio
python src/voz_rumbos.py --file <ruta_a_un_wav> --rumbos 1 2 3 4
```

Sin `--rumbos`, usa una asignación neutra de prueba (no es el mapeo
artístico del montaje — ese lo define Hafo/Ramón por sesión, ver
`docs/OSC_SPEC.md`). Con `--osc <ip:puerto>` emite en vivo hacia el hub
de TouchDesigner (puerto 7000 por convención, ver `docs/OSC_SPEC.md`).

Pruebas:

```
python src/voz_rumbos_test.py
python TouchDesigner_patch/scripts/test_relay_callbacks.py
```

## Boceto sonoro

Boceto sonoro del acorde (dos instancias de Vital): [`media/boceto_acorde_vital.wav`](media/boceto_acorde_vital.wav)

## Fuera de este repo

Corpus de terceros (`repos/`, con licencias propias — ver
`docs/ATRIBUCION.md`), proyectos binarios de TouchDesigner (`.toe`) y
configuración local con IPs de infraestructura no se versionan aquí.
Ver `.gitignore`.
