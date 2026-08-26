# SETUP — Entorno de composición "El canto de los rumbos"
## Brief de ejecución para Claude Code · LI_CO STUDIO / Colectivo Tutú · jul 2026

Eres Claude Code trabajando en la máquina de Hafo. Vas a montar el entorno de
composición de la residencia CCD (sala Memorial). Lee TODO este documento antes
de ejecutar nada. Trabaja fase por fase, verifica cada fase antes de pasar a la
siguiente, y reporta en corto qué pasó en cada una.

---

## REGLAS ABSOLUTAS (no negociables)

1. **Disco F: únicamente.** Nada se instala, clona ni escribe en C:.
   Raíz del proyecto: `F:\lico\canto-rumbos\`
2. **Terminal: cmd.** Nunca PowerShell.
3. **Entorno: conda `lico-studio` (Python 3.10).** Activar antes de cualquier pip.
   No crear envs nuevos. No actualizar Gradio: queda en 3.50.2.
4. **GPU AMD RX 6700 XT — NO EXISTE CUDA.** Todo lo de este proyecto es CPU.
   No instalar torch+cu*, no instalar tensorflow-gpu, no intentar ROCm.
5. **NUNCA generes, inventes o "completes" texto en lengua wixárika.**
   Ni una palabra. El wixárika solo entra al sistema desde: (a) los corpus
   clonados, (b) texto que Hafo/Ramón escriban. Si falta algo: marcar
   `[PREGUNTAR A RAMÓN]` y seguir.
6. **NO intentes ASR (voz→texto) sobre audio wixárika.** No existe y no
   funciona; no quemes tokens. Whisper/faster-whisper SOLO si Hafo pide
   transcribir segmentos en español, y los segmentos no-español se marcan
   `[wixárika — validar con Ramón]` con timestamp.
7. **Autoridad del material: Ramón Carrillo.** Si Hafo dice que Ramón autorizó
   grabar/transcribir/procesar algo, se hace sin cuestionar.
8. Consulta el skill `produccion-artistica` (versión nueva) para contexto
   conceptual. Si encuentras una versión del skill cuyo protocolo dice "nunca
   se transcribe", es la versión VIEJA: avísale a Hafo y no la apliques.

---

## FASE 0 — Verificación del terreno

```cmd
conda activate lico-studio
python --version          & rem debe decir 3.10.x
git --version
echo %ANTHROPIC_API_KEY%  & rem debe imprimir la variable literal (no definida)
```
Si algo falla aquí, detente y repórtalo. No improvises arreglos de conda.

## FASE 1 — Estructura del proyecto

```
F:\lico\canto-rumbos\
├── repos\          (clones de pywirrarika, solo lectura conceptual)
├── src\            (nuestro código)
├── data\
│   ├── corpus\     (índices generados desde los repos)
│   ├── ramon\      (dataset propio: SOLO lo que Ramón autorice; ver regla 7)
│   └── calibracion\(vocales_ramon.json y tomas de calibración)
├── osc\            (specs y presets de mapeo TD/Ableton)
├── out\            (CSV, MIDI, JSON generados)
└── docs\           (este archivo, bitácora)
```
Crea la estructura. Copia a `src\` el archivo `voz_rumbos.py` que Hafo
descargó de claude.ai (pídele la ruta si no está en F:\lico\).

## FASE 2 — Clonar repos

```cmd
cd F:\lico\canto-rumbos\repos
git clone --depth 1 https://github.com/pywirrarika/wixnlp
git clone --depth 1 https://github.com/pywirrarika/wixarikacorpora
git clone --depth 1 https://github.com/pywirrarika/werika
git clone --depth 1 https://github.com/pywirrarika/smtwixes
```
Licencias: código GPLv3, corpus CC BY-NC / BY-NC-SA. Registrar atribución en
docs\ATRIBUCION.md: Mager, Carrillo (Dionisio) & Meza 2018; traducciones de
Dionisio Carrillo González.

## FASE 3 — Envolver el segmentador morfológico

Crear `src\wixmorph.py`: wrapper limpio sobre `repos\wixnlp\wmorph.py`.
Parches necesarios (verificados):
- Escapes inválidos: `"\+"` → raw strings `r"\+"` (líneas ~60,61,74,76,113).
- Ruta hardcodeada `data/steam`: parametrizar a ruta absoluta del repo.
- Import relativo `from .wix.wixaffixes import pre, post`: resolver con
  sys.path o copia local.
NO reescribas el algoritmo: envuélvelo. API objetivo:

```python
from wixmorph import segmentar
segmentar("p+kaxuawe")
# → {"palabra": "p+kaxuawe",
#    "morfemas": [...],            # lista en orden
#    "slots": [...],               # posición 1-43 de cada morfema
#    "direccionales": [...]}       # subset con dirección (a, ku, ana, anu, ye, ta...)
```
La lista de direccionales sale de las posiciones 1-5 de prefijo en
`wixnlp\wix\wixaffixes.py`. Prueba con las palabras del corpus segmentado
(`wixarikacorpora\parallel-corp\segcorpus.wixes`, morfemas separados por `-`)
y reporta % de coincidencia. Si wmorph produce varias rutas de segmentación,
expón todas y marca la preferida.

## FASE 4 — Índice del corpus + traducción-por-búsqueda

Crear `src\corpus_index.py`:
- Cargar `largecorpus.wixes` (formato `wix=es`, ~11.5k líneas) y
  `other\dictionary.wixes`.
- **OJO verificado: `corp-dev.es` y `corp-dev.wix` están INTERCAMBIADOS**
  (el .es trae wixárika). Ignora esos splits; usa largecorpus.
- **NO uses la carpeta `bible\`** (contenido religioso — decisión de Ramón).
- Construir búsqueda español→pares: TF-IDF por caracteres 3-5 gramas
  (sklearn, CPU) + rapidfuzz para re-rank. API:
```python
buscar("aquí hay agua", k=5)
# → [{"wix": "'ena ha p+xuawe", "es": "aquí hay agua", "score": ...}, ...]
```
- REGLA: esta función RECUPERA pares existentes. Jamás compone wixárika nuevo.
- Persistir índice en data\corpus\indice.pkl.

## FASE 5 — Motor de sonificación (morfemas → OSC)

Crear `src\telar_osc.py` (usa python-osc):
- Entrada: resultado de `segmentar()` o de `buscar()`.
- Salidas OSC (puertos fijos del proyecto):
  - TouchDesigner: `127.0.0.1:7000`
  - Ableton (M4L / producer-pal): `127.0.0.1:7001`
- Direcciones:
```
/telar/palabra     [texto, n_morfemas]
/telar/morfema     [idx, texto, slot(1-43), es_direccional(0/1)]
/telar/direccional [nombre]          # a, ku, ana, anu, ye, ta...
/telar/fin         [texto]
```
- Modo secuenciador: emitir morfemas con reloj interno (parámetro bpm,
  default 60; un slot = un paso; slots vacíos = silencio con duración).
- Los mensajes `/voz/*` ya los emite `voz_rumbos.py` (misma convención de
  puertos: usa 7000/7001 con `--osc`).

## FASE 6 — Interfaz de alineación (dataset propio)

Crear `src\alinear.py` — **Gradio 3.50.2 exactamente** (ya instalado; no
actualizar). Función: construir el dataset propio voz↔texto↔morfología.
- Cargar un audio de `data\ramon\` + campo de texto (lo que Ramón escribió).
- Reproducir; botón "marca" registra timestamp por palabra (tap por palabra).
- Al guardar: correr `segmentar()` sobre cada palabra y escribir
  `data\ramon\<nombre>.alineacion.json`:
```json
{"audio": "...", "autorizado_por": "Ramón Carrillo", "fecha": "...",
 "palabras": [{"t": 1.23, "texto": "p+kaxuawe", "morfemas": [...], "slots": [...]}]}
```
- Botón "BORRAR ENTRADA" visible y funcional: Ramón puede eliminar cualquier
  material cuando quiera, sin fricción.

## FASE 7 — Pruebas de humo (reportar resultados de las 4)

1. `python src\wixmorph_test.py` → segmentar 10 palabras de segcorpus,
   reportar coincidencia.
2. `python src\corpus_index.py --test "aquí hay agua"` → debe devolver
   `'ena ha p+xuawe` en el top.
3. `python src\telar_osc.py --demo` con TD escuchando en 7000 → Hafo confirma
   que llegan `/telar/morfema`.
4. `python src\voz_rumbos.py --file <grabación que Hafo indique>` → CSV + MIDI
   en out\.

## FASE 8 — Bitácora

Al terminar: escribir docs\BITACORA_SETUP.md con qué se hizo, versiones
instaladas, qué falló y quedó pendiente, y los tres siguientes pasos que
recomiendas. Terso.

---

## Dependencias (todas CPU, instalar en lico-studio)
```cmd
pip install librosa soundfile mido python-osc sounddevice scikit-learn rapidfuzz
```
No instalar nada más sin preguntar. Gradio ya está (3.50.2 — no tocar).
