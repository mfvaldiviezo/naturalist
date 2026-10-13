# H12.8 — Auditoría OFFLINE de exposición y observabilidad en B1

## Objetivo

Resolver, **sin volver a iniciar SUMO**, si los eventos Vine modificaron los agregados de tráfico en B1 entre microticks y si los cuatro microticks con detenciones en B1 coincidieron con los instantes de decisión PPO (5, 10, ..., 60 s).

La observación 34D puede permanecer igual entre corridas aunque ambas tengan tráfico en B1; en particular el estado está definido para un **semáforo** y la intervención Vine puede manifestarse en otra localización. H12.8 NO reconstruye localizaciones por ID, que no fueron registradas en H12.7.

## Alcance y restricciones

- Solo lee `nominal/piloto_h12_5.json`, `active/piloto_h12_5.json` y `analisis_estado_b1.json` del directorio H12.7.
- Verifica modelo, SHA checkpoint, SHA red/rutas/configuración, fuentes, microticks, tiempos y comandos.
- Compara conteos, detenciones y espera en **cada** microtick de B1, frente a nominal.
- Cruza las métricas B1 de los 120 microticks con los **12 instantes de observación/recompensa**, y marca discrepancias del sensor.
- Informa los carriles repetidos en las 12 entradas, la ausencia de outgoing lanes y el mapa efectivo de 4 acciones a fases.
- No importa SUMO, TraCI, Torch, modelos ni módulos del repositorio; no altera el checkpoint ni la representación de entrenamiento.
- Sus pruebas unitarias utilizan **fixtures sintéticos**, no representan validación de tráfico real.

## Instalación

Extraer `H12_8_Auditoria_Exposicion_Observabilidad_v100.zip` directamente en `C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

### A. Pruebas

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h128 = '.\H12_8_Auditoria_Exposicion_Observabilidad_v100'
python -m unittest discover -s "$h128\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'H12.8: pruebas fallidas' }
```

### B. Auditoría de H12.7 (sin simulación)

```powershell
$h127run = '.\resultados\h12_7_estado_b1_20261012_073512_250528_5143e4'
python "$h128\h12_8_auditar.py" `
    --h127-dir $h127run `
    --results-root '.\resultados'
if ($LASTEXITCODE -ne 0) { throw 'H12.8: auditoría bloqueada' }
```

### C. Mostrar dictamen

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_8_offline_*' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_h12_8.md') -Encoding UTF8
```

## Lectura e interpretación

- Si hay detenidos en B1 en microticks, pero **ninguno en fronteras de decisión**, que la cola del PPO sea cero **no es una contradicción**.
- Si hay detenidos en B1 **exactamente en una frontera de decisión**, pero PPO informa cola cero, hay una **discrepancia** que requiere inspección del mapeo y del orden de lectura.
- Si existen diferencias agregadas B1 en microticks intermedios, pero ninguna de las 12 observaciones 34D difiere, la agregación temporal puede estar ocultando los efectos que PPO podría necesitar percibir.
- Si no hay diferencias agregadas B1, no se puede concluir que Vine no afectó velocidades individuales en B1 o en otros lugares. Se requeriría telemetría por ID/posición para ubicar las perturbaciones.
- Con `green_phases=[0,2]` el código heredado mapea 4 acciones PPO a **2 objetivos**: `0→0`, `1→2`, `2→0`, `3→2`.
- Repetir el mismo carril para completar 12 entradas altera la ponderación de métricas; outgoing lanes vacío no representa presión entrante menos saliente. **No cambiar estas semánticas ni reusar checkpoint bajo una nueva representación sin revalidar/reentrenar.**

El dictamen produce `auditoria_h12_8.json` y `dictamen_h12_8.md` en nuevo directorio de `resultados`. No implica evaluación de resiliencia, representatividad del comportamiento poblacional de Quito ni homologación de semáforos SOTA.
