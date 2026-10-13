# H12.19 v1.0.1 — Piloto off-policy TD con la arquitectura CoLight auténtica

**Objeto:** comprobar que la red `ColightNet` original de LibSignal (commit fijado H12.16) admite entrenamiento con gradientes y un checkpoint nuevo derivado de transiciones reales de SUMO Hangzhou, **sin** permitir todavía que la red controle el tráfico ni afirmar una reproducción experimental completa de CoLight.

**Corrección v1.0.1 (Windows):** seis pruebas `PlanTests` del paquete anterior tenían una ruta `/mnt/data/H12_18...` fija. La suite ahora utiliza una carpeta H12.18 simulada creada dentro del directorio temporal de las pruebas, más dos controles adicionales de rechazo de fuentes faltantes y versiones incorrectas. **No se modificaron `h12_19_offpolicy.py` ni `h12_19_td.py`; el esquema experimental sigue siendo V100.** La nueva suite pasó 60/60 pruebas en un entorno de desarrollo; falta confirmación Windows.

## Qué se hereda

- H12.17 `H12_17_MULTI_TLS_SMOKE_OK` (12 semáforos, 32 aristas dirigidas, fases físicas `[0,2]`, transición vía amarillos `[1,3]`, observación `12x34`, 0.5 s y decisiones cada 5 s).
- H12.18 v1.0.3 `H12_18_COLIGHT_SHADOW_FORWARD_OK` y manifiesto; red `ColightNet` aislada desde el **blob comprometido Git** de `agent/colight.py` del commit `127af9f93902778e556de2eedb2b606c4c9447e6`.
- Entradas **específicas** CoLight `lane_count` por carril, `12x4`, con relleno de ceros; grafo canónico y `2` acciones físicas por nodo. **No** se altera la observación 34D homologada para los otros métodos.
- SHA-256 de red `2590ca460dafb57a4c608f4fe1ad9de072068a5b2ef0ea487f617296d8c627f6`; rutas `a78363c99e1a6eab33028c3a36c82dcb66129adf8e73141612b9e7b2358f1369`.

## Qué hace realmente H12.19

1. **`plan`** (lectura solamente): verifica todos los antecedentes y fuentes, incluyendo el resultado de sombra H12.18, su manifiesto y su grafo.
2. **`probe`** (solo RAM, sin SUMO): carga clases neuronales originales mediante el mismo mecanismo H12.18 y ejecuta un paso real de diferenciación TD con datos sintéticos, para certificar que existe *backpropagation* en `ColightNet`. No guarda nada.
3. **`pilot`**: simula 24 decisiones (120 s, 240 microticks) controlando SUMO exclusivamente con la política alternante de prueba de H12.17; recopila 24 transiciones de 12 semáforos. Después del cierre de SUMO, hace 4 actualizaciones TD off-policy CPU y guarda un **checkpoint exploratorio nuevo** con SHA y etiqueta `TD_PILOT_ONLY_NOT_SOTA`.

La función objetivo del piloto utiliza la recompensa de espera de CoLight (`-12 × promedio de vehículos detenidos` por nodo) derivada de lecturas instantáneas de TraCI. Es una **aproximación documentada**, no una certificación de equivalencia exacta con el *World*, el *Generator* o el *Trainer* nativos de LibSignal. Utiliza RMSprop `lr=0.001`, gamma `0.95`, grad clipping `5.0` y una red objetivo, como en la familia DQN de la fuente. El mecanismo TD del piloto **no es** el entrenador nativo completo: incluye una máscara explícita de final de episodio y usa MSE solo para la acción observada. No hay exploración epsilon-greedy de CoLight sobre SUMO, ni evaluación de mejora/rendimiento.

**Límites:** No existe reproducción SOTA certificada, acción neuronal online, entrenamiento comparativo equitativo, Vine/H09 en el nuevo entorno, ni medida de resiliencia. No declarar ninguna de esas capacidades basándose en este piloto.

## Ejecutar (PowerShell, Windows)

Extraer `H12_19_Piloto_Aprendizaje_CoLight_v101.zip` en `C:\Proyecto_Tesis_Final_V1\revision_naturalista`, junto a las etapas previas, sin editar archivos antiguos.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate colight-pyg

$h1219 = '.\H12_19_Piloto_Aprendizaje_CoLight_v101'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
$lib = (Resolve-Path '.\externos_h12_16\LibSignal').Path
$h1218 = '.\H12_18_Bridge_CoLight_LibSignal_v103'
$h1217run = Get-Item '.\resultados\h12_17_multi_tls_20261012_182005_185768_19e1d1'
$shadowrun = Get-Item '.\resultados\h12_18_colight_shadow_20261012_194524_727195_c65df4'
$h1216run = Get-ChildItem '.\resultados' -Directory -Filter 'h12_16_colight_*' |
    Where-Object { Test-Path (Join-Path $_.FullName 'dictamen_h12_16.json') } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $h1216run) { throw 'Falta resultado H12.16' }

python -m unittest discover -s "$h1219\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'H12.19: fallaron pruebas de validación' }

$h19args = @(
  '--repo-root', $repo,
  '--revision-root', (Get-Location).Path,
  '--h1216-dir', $h1216run.FullName,
  '--h1217-dir', $h1217run.FullName,
  '--h1218-dir', (Resolve-Path $h1218).Path,
  '--h1218-shadow-dir', $shadowrun.FullName,
  '--libsignal-dir', $lib
)

python "$h1219\h12_19_offpolicy.py" @h19args --mode plan
if ($LASTEXITCODE -ne 0) { throw 'Preflight H12.19 bloqueado' }
```

Se espera `H12_19_PLAN_OK`.

Después ejecutar prueba de gradientes en memoria, sin SUMO ni archivos nuevos:

```powershell
python "$h1219\h12_19_offpolicy.py" @h19args --mode probe
if ($LASTEXITCODE -ne 0) { throw 'Forward/backprop CoLight no acreditado' }
```

Se espera `H12_19_GRADIENT_PROBE_OK` y un objeto con `max_parameter_delta` positivo y finito.

**Solo si `plan` y `probe` terminan OK**, permite recolección real y creación de un checkpoint exploratorio:

```powershell
python "$h1219\h12_19_offpolicy.py" @h19args `
    --mode pilot `
    --seed 101 `
    --steps 24 `
    --updates 4 `
    --batch-size 4 `
    --min-green 10 `
    --ack-sumo-test-policy H1217_TEST_POLICY_NOT_NEURAL `
    --ack-new-checkpoint NEW_EXPLORATORY_WEIGHTS_ONLY

if ($LASTEXITCODE -ne 0) { throw 'H12.19 piloto NO acreditado' }
```

Se espera `H12_19_COLIGHT_UPSTREAM_NETWORK_TD_SMOKE_OK`, **no** un resultado científico de rendimiento.

## Informe

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_19_colight_td_*' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_h12_19.md') -Encoding UTF8
Get-Content (Join-Path $ultimo.FullName 'resultado_h12_19.json') -Encoding UTF8
```

Los artefactos serán `manifiesto_h12_19.json`, `telemetria_h12_19.json`, `colight_network_td_pilot_only.pt`, `resultado_h12_19.json` y `dictamen_h12_19.md`. Un fallo tras crear el directorio produce `ERROR_h12_19.json`; cualquier checkpoint incompleto queda **no certificado**. El origen de los pesos del nuevo archivo se limita al piloto local y no puede sustituir un modelo CoLight entrenado de referencia.

## Próximo hito

Desarrollar **adaptación y entrenamiento íntegro de `CoLightAgent`/`TSCTrainer`** sobre el contrato multi-TLS: corregir explícitamente el orden de los generadores respecto al índice del grafo, conservar la mecánica de acciones/replay/epsilon/target y alinear semánticamente recompensas, amarillo y fases; implementar ensayos pareados y comprobar estabilidad del aprendizaje antes de inyectar Vine/H09.
