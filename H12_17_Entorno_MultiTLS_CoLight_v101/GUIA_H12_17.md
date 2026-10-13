# H12.17 v1.0.1 — Corrección de prueba en Windows

La versión v1.0.1 modifica **solo** `tests/test_h12_17.py`, en `test_h1212_source_tamper_rejected`: sustituye la lectura/escritura en la codificación regional por `read_bytes()`/`write_bytes()`. Evita `UnicodeDecodeError` al ejecutar Python con `cp1252`, sin cambiar los SHA esperados, los contratos, la lógica SUMO, el controlador multi-TLS ni los antecedentes. **No indica que SUMO haya sido probado en Windows**.

# H12.17 — Red Hangzhou 12 TLS y contrato para SOTA multiagente

## Alcance y estado

**H12.17 v1.0.0** crea un entorno Gymnasium de control simultáneo para los 12 semáforos del escenario Hangzhou congelado en H12.12. Amplía la observación a una matriz `(12,34)` y la actuación a `MultiDiscrete([2]*12)`. Construye **un grafo dirigido** directamente desde los enlaces `<edge from="..." to="...">` del `net.xml`, utilizando el mismo orden inmutable de nodos para grafo, estados y acciones.

**No ejecuta ni entrena CoLight, CoSLight, IPPO, MPLight o nuestras redes PPO.** El controlador usado en `smoke` es una política alternante y escalonada de prueba, sin aprendizaje. Tampoco inyecta Vine/H09. Un resultado `H12_17_MULTI_TLS_SMOKE_OK` acredita únicamente la infraestructura física multiintersección, no reproducción de SOTA ni resiliencia.

La versión actual está restringida por SHA-256 a las fuentes Hangzhou originales de H12.12:

- Red `2590ca460dafb57a4c608f4fe1ad9de072068a5b2ef0ea487f617296d8c627f6`.
- Rutas `a78363c99e1a6eab33028c3a36c82dcb66129adf8e73141612b9e7b2358f1369`.

**Requisitos previos:** H12.12 smoke acreditado (`manifiesto_h12_12.json` + `smoke_h12_12.json`), H12.16 auditado (`dictamen_h12_16.json`), `H12_12_Entorno_Homologado_B1_v100` intacto y entorno `tsc-env` con SUMO, TraCI, Gymnasium, NumPy.

## 1. Descomprimir y ejecutar 58 pruebas automatizadas

Desde PowerShell:

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env

$h1217 = ".\H12_17_Entorno_MultiTLS_CoLight_v100"
$repo = "C:\Proyecto_Tesis_Final_V1\traffic_project"

python -m unittest discover -s "$h1217\tests" -v
if ($LASTEXITCODE -ne 0) { throw "Fallaron las pruebas H12.17" }
```

Las pruebas incluyen integración **simulada** con TraCI/Gymnasium. No son un piloto SUMO real.

## 2. Ubicar antecedentes acreditados

```powershell
$h1212run = Get-ChildItem ".\resultados" -Directory -Filter "h12_12_homologado_*" |
    Where-Object { Test-Path (Join-Path $_.FullName "smoke_h12_12.json") } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

$h1216run = Get-ChildItem ".\resultados" -Directory -Filter "h12_16_colight_*" |
    Where-Object { Test-Path (Join-Path $_.FullName "dictamen_h12_16.json") } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $h1212run -or -not $h1216run) { throw "Faltan auditorías H12.12/H12.16" }
Write-Host "H12.12:" $h1212run.FullName
Write-Host "H12.16:" $h1216run.FullName
```

La selección automática identifica los informes existentes; el preflight además verifica estado, fuentes y SHA, no confía exclusivamente en el nombre del directorio.

## 3. Preflight estrictamente offline

```powershell
python "$h1217\h12_17_multi_tls.py" `
    --repo-root $repo `
    --revision-root . `
    --h1212-smoke-dir $h1212run.FullName `
    --h1216-dir $h1216run.FullName `
    --mode plan

if ($LASTEXITCODE -ne 0) { throw "H12.17 preflight rechazado" }
```

**Resultado esperado:** `H12_17_PLAN_OK`. No usa SUMO ni crea archivos. Verifica los 12 TLS y 32 aristas dirigidas (dos verdes 0/2, amarillos 1/3 de duración ≥3 s), carriles, SHA, caminos semafóricos y conectividad del grafo. La fase amarilla tiene prioridad semántica si contiene `y/Y`, incluso cuando conserva verdes `G/g` de otros enlaces.

## 4. Piloto multi-TLS SUMO real de 60 segundos

Solo después de `H12_17_PLAN_OK`:

```powershell
python "$h1217\h12_17_multi_tls.py" `
    --repo-root $repo `
    --revision-root . `
    --h1212-smoke-dir $h1212run.FullName `
    --h1216-dir $h1216run.FullName `
    --mode smoke `
    --seed 101 `
    --rl-steps 12 `
    --min-green 10 `
    --ack-new-contract NEW_MULTIAGENT_MODELS_ONLY `
    --ack-online-control MULTI_TLS_OVERRIDE

if ($LASTEXITCODE -ne 0) { throw "H12.17 smoke SUMO no acreditado" }
```

**Resultado esperado** si pasa en el equipo: `H12_17_MULTI_TLS_SMOKE_OK`, 12 semáforos, 12 decisiones conjuntas, 120 microticks (60 s), amarillos verificados y ninguna colisión detectada por TraCI. No hay inferencia RL.

Si falla, **no borres** `resultados\h12_17_multi_tls_*`: inspecciona `ERROR_h12_17.json` y compártelo. Al detectar condiciones que invalidan integridad física, el programa no declara éxito.

## 5. Verificar el dictamen

```powershell
$ultimo = Get-ChildItem ".\resultados" -Directory -Filter "h12_17_multi_tls_*" |
    Where-Object { Test-Path (Join-Path $_.FullName "dictamen_h12_17.md") } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $ultimo) { throw "No hay dictamen H12.17" }
Get-Content (Join-Path $ultimo.FullName "dictamen_h12_17.md") -Encoding UTF8
```

Archivos de resultado:

- `manifiesto_h12_17.json`: 12 geometrías, aristas dirigidas, `node_order`, `node_to_index`, fuentes/SHA y estado de puertas.
- `runtime_h12_17.json`: versión SUMO, Gymnasium, NumPy, ubicación de TraCI.
- `smoke_h12_17.json`: observaciones por nodo/decisión, acciones, colas, esperas, fases, recompensas y eventos.
- `dictamen_h12_17.md`: auditoría legible.
- `ERROR_h12_17.json` en caso de fallo (solo si se creó un directorio de ejecución).

## Próximas puertas — no incluidas

H12.18: revisar el orden interno de nodos CoLight/LibSignal **en tiempo de ejecución**, probar dependencias Torch Geometric/Torch Scatter en Windows o ambiente aislado, y construir adaptador que conserve los mecanismos de atención originales. A continuación CoSLight, IPPO, MPLight y adaptación controlada de nuestros modelos para red. Solo cuando los controladores estén homologados y entrenados con presupuestos acreditados habrá evaluación de resiliencia ante Vine/H09 con comparaciones emparejadas.
