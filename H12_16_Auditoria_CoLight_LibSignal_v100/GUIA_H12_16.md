# H12.16 — Auditoría CoLight original vs LibSignal

**Objetivo:** conservar CoLight como SOTA auténtico de **coordinación multiintersección**, distinguiéndolo de CoSLight y de la heurística histórica denominada `CoLightAgent`. Esta fase **no** entrena, no ejecuta CoLight, no instala bibliotecas y no cambia H12.12–H12.15.

## 1. Evidencias y decisiones previas

- H12.12: SUMO real, 34D, dos acciones físicas en B1, amarillos de 3 s y verde mínimo.
- H12.14: fuentes RESCO verificadas; red/rutas Hangzhou de RESCO son idénticas a las de H12.12. **RESCO no incluye CoLight auténtico**, pero sí CoSLight.
- H12.15: Fixed-B1 y MaxPressure proyectado completaron sus pilotos SUMO; no son reproducción integral de RESCO.
- CoLight original: https://github.com/wingsweihua/colight (`CoLight_agent.py`, TensorFlow 1.11/Keras 2.1).
- Candidato de integración: https://github.com/DaRL-LibSignal/LibSignal (`agent/colight.py`, PyTorch/torch-geometric/torch-scatter). Este agente se registra mediante `@Registry.register_model('colight')`, aparece importado en `agent/__init__.py` y usa un grafo de vecinos.
- **No confundir** `agent/colight.py` con `agent/colight_pytorch_agent.py`, archivo alternativo no importado en el registro examinado.

Los dos commits y los SHA-1 de los blobs Git se encuentran en `upstream_pins.json`, obtenidos del código público en 2026-10-12. Clonar otros commits sin fijar versión NO es un experimento reproducible.

## 2. Preparación — carpetas aisladas

En **PowerShell**, desde tu directorio de trabajo:

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env

$h1216 = ".\H12_16_Auditoria_CoLight_LibSignal_v100"
$repo = "C:\Proyecto_Tesis_Final_V1\traffic_project"
$h1214 = ".\resultados\h12_14_sota_20261012_162718_504371_4d2424"
$h1215 = ".\resultados\h12_15_baselines_b1_20261012_164454_620962_0816b8"

python -m unittest discover -s "$h1216\tests" -v
if ($LASTEXITCODE -ne 0) { throw "H12.16: pruebas fallidas" }

python "$h1216\h12_16_auditar_colight.py" --mode inventory
if ($LASTEXITCODE -ne 0) { throw "H12.16: inventario fallido" }
```

A continuación, descarga **únicamente el código**, sin instalar `requirements.txt` ni ejecutar scripts de los repositorios:

```powershell
$externos = Join-Path (Get-Location) "externos_h12_16"
New-Item -ItemType Directory -Force -Path $externos | Out-Null

$original = Join-Path $externos "colight_original"
$libsignal = Join-Path $externos "LibSignal"

if (-not (Test-Path $original)) {
    git clone https://github.com/wingsweihua/colight.git "$original"
    if ($LASTEXITCODE -ne 0) { throw "Falló git clone CoLight original" }
}
if (-not (Test-Path $libsignal)) {
    git clone https://github.com/DaRL-LibSignal/LibSignal.git "$libsignal"
    if ($LASTEXITCODE -ne 0) { throw "Falló git clone LibSignal" }
}

git -C "$original" checkout --detach 04440b722e7f36d7043a3f2ad8e40c3df301fad3
if ($LASTEXITCODE -ne 0) { throw "No se pudo fijar commit CoLight" }

git -C "$libsignal" checkout --detach 127af9f93902778e556de2eedb2b606c4c9447e6
if ($LASTEXITCODE -ne 0) { throw "No se pudo fijar commit LibSignal" }
```

> **Advertencia:** `git checkout --detach` puede rechazar cambios locales. No utilices `-f` ni `git reset --hard` para forzarlo: conserva y documenta las modificaciones si las hubiese. Las dos carpetas son independientes de `traffic_project`.

## 3. Preflight de código e integridad, sin salidas

```powershell
python "$h1216\h12_16_auditar_colight.py" `
    --mode plan `
    --repo-root "$repo" `
    --original-dir "$original" `
    --libsignal-dir "$libsignal" `
    --h1214-dir "$h1214" `
    --h1215-dir "$h1215"

if ($LASTEXITCODE -ne 0) { throw "H12.16: no se acreditó el preflight" }
```

**Éxito esperado:** `H12_16_PLAN_OK`.

Este preflight verifica `git rev-parse HEAD`, origen remoto, ausencia de cambios locales en archivos rastreados, SHA-1 de los blobs comprometidos, existencia de archivos checkout, firmas estáticas de CoLight, H12.14 y SHA-256 de la red y rutas Hangzhou. No utiliza Internet: las fuentes deben estar previamente clonadas. No importa paquetes de RL ni ejecuta SUMO.

## 4. Auditoría y dictamen

```powershell
python "$h1216\h12_16_auditar_colight.py" `
    --mode analyze `
    --repo-root "$repo" `
    --original-dir "$original" `
    --libsignal-dir "$libsignal" `
    --h1214-dir "$h1214" `
    --h1215-dir "$h1215" `
    --results-root ".\resultados"

if ($LASTEXITCODE -ne 0) { throw "H12.16: auditoría no acreditada" }

$ultimo = Get-ChildItem ".\resultados" -Directory -Filter "h12_16_colight_*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName "dictamen_h12_16.md") -Encoding UTF8
```

**Éxito esperado:** `H12_16_COLIGHT_SOURCE_AUDIT_OK`.

Salida: `dictamen_h12_16.md`, `dictamen_h12_16.json`, `fuentes_git_h12_16.csv`, `pins_sha256.txt`. El resultado acredita **fuentes y estructura estática**, no entrenamiento, equivalencia dinámica ni resiliencia.

## 5. Riesgos a estudiar antes de H12.17

1. **Orden de nodos del grafo.** El código LibSignal contiene expresiones `sorted(lista, ...)` sin asignación. Hay que comprobar, con un test dinámico, que el orden de las observaciones coincide con `graph['node_id2idx']` y `sparse_adj`. No corregir sin prueba.
2. **Modelo de acciones.** El agente implementa máscaras de longitud de fase (`phase_lengths`); se debe comprobar su correspondencia con verdes SUMO y los interverdes por intersección. No proyectar arbitrariamente ocho pares RESCO sobre dos verdes.
3. **Observaciones y recompensa.** CoLight LibSignal usa generadores de `lane_count` y `lane_waiting_count`, no el estado H12.12 de 34 dimensiones. Debemos adaptar la interfaz preservando las señales y arquitectura reales, y registrar las diferencias.
4. **Dependencias Windows.** Versiones de PyTorch y paquetes `torch_geometric`/`torch_scatter` deben ensayarse en entorno separado. `find_spec` solo informa presencia, no compatibilidad binaria.
5. **Escenario de ejemplo.** `configs/sim/sumo1x1_colight.cfg` apunta a `cologne1`; no sirve para acreditar Hangzhou.
6. **Control multi-TLS.** CoLight necesita varios agentes y conectividad real. H12.12 controla B1: falta implementar un H12.17 con red completa, amarillo coherente y política definida en el resto de intersecciones.

## 6. Criterio de liberación

No utilizar el rótulo `CoLight SOTA evaluado` hasta contar con: código fijado, pruebas de estructura y ejecución de la red, adaptador de acciones seguro, entrenamiento verificable y checkpoints propios, red/demanda/semillas bloqueadas, escenarios Vine/H09 protegidos y métricas emparejadas. **CoSLight es otro SOTA**, no una versión de CoLight.
