# H12.10 v1.0.1 — Auditoría offline de sensibilidad de la política PPO

## Corrección v1.0.1: contrato REAL de la observación 34D

El validador anterior exigía erróneamente `[0,1]` para las 34 posiciones, por lo que rechazaba los resultados H12.9 a partir de los 120 segundos sin cambio de fase. El `TSCEnv` original devuelve `[32] = edad_fase_s / 120` **sin clipping**, junto a `[33] = clip(edad_fase_s/120,0,1)`. El `spaces.Box` declarado como `[0,1]^34` es inconsistente con los valores realmente emitidos por `_get_state()`. Esta versión conserva el valor real, sin modificar las observaciones ni el checkpoint, valida el límite temporal de 300 segundos y la coherencia entre ambas componentes. También registra la discordancia en el dictamen.

**Advertencia de reproducibilidad:** La aceptación de valores >1 para la posición 32 no demuestra que el checkpoint se haya entrenado con esa semántica; es un diagnóstico de la arquitectura heredada. No entrenar ni transformar las observaciones aquí.

## Motivación experimental

H12.9 acredita que Vine protegida se ejecutó ante `ppo_ideal`, que nominal/probe produjeron idéntica traza y que los 100 comandos longitudinales se confirmaron. En 300 s hubo 39/60 diferencias de entrada 34D y 0/60 diferencias de acción. El presente paquete separa **cambio de distribución de probabilidades** de **cambio en la acción determinista** sin entrenar de nuevo ni ejecutar SUMO.

## Alcance y controles

- Lee los tres `piloto_h12_5.json` de **un mismo** directorio `h12_9_exposicion_300s_...` (`nominal`, `probe`, `active`).
- Exige 60 decisiones, 600 microticks y 300 s por condición; misma red, rutas, configuración, fuente H10 y checkpoint; nominal/probe idénticos; 100 comandos (u otra cifra >0) confirmados en activo.
- Valida el SHA-256 **del checkpoint local** contra el manifest de los resultados.
- Carga la política original mediante `stable_baselines3.PPO.load(..., device='cpu')`, importando `HSARGExtractor` y `CoopSARGExtractor` desde el repositorio local original, igual que H12.5.
- Recalcula `model.predict(state, deterministic=True)` en las 60 observaciones de las tres condiciones y **rechaza** cualquier discrepancia con las decisiones ya guardadas.
- Recupera `policy.get_distribution(...)` para obtener la distribución categórica de las cuatro acciones, su entropía y margen de la acción mayoritaria.
- Calcula distancia de variación total (TV) y divergencia Jensen–Shannon (nats) entre distribuciones nominal/Vine; informa diferencias por instante.
- Suma las probabilidades de las acciones que apuntan a la **misma fase real** (acciones 0 y 2 a fase 0; 1 y 3 a fase 2 para B1), **solo a efectos descriptivos**. PPO continúa decidiendo `argmax` entre cuatro acciones.
- No modifica ninguna fuente, checkpoint, resultados H12.9 o pesos; solo crea una carpeta de informe nueva al ejecutar `--mode analyze`.

**Limitaciones:** Los tests incluidos son locales con fixtures y modelos sintéticos: no acreditan que `stable_baselines3` pueda cargar el checkpoint de Windows hasta que se ejecute el análisis real. No hay evidencia estadística de resiliencia, equivalencia de entrenamiento ni calibración poblacional de Quito. El entorno heredado repite carriles y tiene `outgoing_lanes=[]`.

## Instalación

Extraer el ZIP dentro de `C:\Proyecto_Tesis_Final_V1\revision_naturalista`, manteniendo el directorio `H12_10_Auditoria_Politica_PPO_v101`.

### A. Pruebas sin SUMO

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h1210 = '.\H12_10_Auditoria_Politica_PPO_v101'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
python -m unittest discover -s "$h1210\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'H12.10: pruebas no acreditadas' }
```

### B. Seleccionar resultado H12.9

```powershell
$last129 = Get-ChildItem '.\resultados' -Directory -Filter 'h12_9_exposicion_300s_*' |
  Where-Object { Test-Path (Join-Path $_.FullName 'active\piloto_h12_5.json') } |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $last129) { throw 'No se localizó un resultado H12.9 completo' }
Write-Host $last129.FullName
```

### C. Preflight offline

```powershell
python "$h1210\h12_10_politica.py" `
  --h129-dir $last129.FullName `
  --repo-root $repo `
  --mode plan
if ($LASTEXITCODE -ne 0) { throw 'H12.10: preflight fallido' }
```

Salida esperada: `H12_10_PLAN_OK`.

### D. Auditoría real del checkpoint (SIN SUMO)

```powershell
python "$h1210\h12_10_politica.py" `
  --h129-dir $last129.FullName `
  --repo-root $repo `
  --results-root '.\resultados' `
  --mode analyze
if ($LASTEXITCODE -ne 0) { throw 'H12.10: política no acreditada' }
```

Salida esperada: `H12_10_POLITICA_OFFLINE_OK`.

### E. Ver dictamen

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_10_politica_*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_h12_10.md') -Encoding UTF8
```

Archivos creados: `dictamen_h12_10.md`, `dictamen_h12_10.json`, `probabilidades_pareadas.csv`.

## Cómo interpretar

- Si cambian las probabilidades con idéntica acción 0, la red **sí es sensible** a estos estados, pero no cambia la selección determinista: estudiar márgenes y estado heredado.
- Si casi no cambian las probabilidades, evidencia de **baja sensibilidad local** del checkpoint frente a este conjunto de observaciones, no una conclusión global.
- Si `PREDICCION NO REPRODUCIBLE`, detener el análisis: no podemos explicar las decisiones registradas con el checkpoint disponible; revisar normalización, versiones, fuente y entorno de inferencia.
- Si el modelo falla al cargar, detener: no borrar/reentrenar el checkpoint; conservar error.
- En ninguna circunstancia se debe confundir un cambio en probabilidad por fase con una acción física nueva; el mapeo de dos fases se mantiene por trazabilidad.
