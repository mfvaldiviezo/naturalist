# H12.14 v1.0.0 — Auditoría de SOTA auténticos RESCO y preparación de homologación

## Objetivo y límites

Esta entrega **no entrena ni ejecuta** algoritmos RESCO. Audita por inspección estática fuentes originales y `agent.yaml`, verifica la topología B1 y la procedencia H12.12, compara SHA-256 de las fuentes de Hangzhou originales RESCO frente a las utilizadas en H12.12 y emite una **matriz de compatibilidad con puertas de paso**. No altera ninguno de los ficheros fuente, redes, rutas o checkpoints y no importa SUMO, Gymnasium, Stable-Baselines3 ni los agentes RESCO.

- `FIXED`: baseline no neuronal, pero depende de calendario y estados de fases RESCO.
- `MAXPRESSURE`: en este árbol RESCO delega en `WaveAgent`, cuya semántica depende de `cfg.phase_pairs`, `cfg.directions` y del `state=mplight`. **No se declarará automáticamente equivalente al MaxPressure físico en H12.12**.
- `IPPO`: fuente en `baselines/RESCO/resco_benchmark/agents/policy/pfrl_ppo.py`; utiliza PFRL y estado `drq`.
- `MPLight`: fuente FRAP/DQN en `agents/action_value/mplight.py`; utiliza pares de fases y estado `mplight`; no sustituir por PPO/MLP.
- `CoSLight`: `agents/policy/CoSLight/coslight.py`; arquitectura multiagente con buffers compartidos y `len(obs_act)`. No se homologa como B1 único porque eso elimina la cooperación de intersecciones.

**CoLight no es CoSLight.** El `CoLightAgent` histórico del estudio inicial era una heurística no certificada como modelo CoLight auténtico: no se incorporará bajo una etiqueta SOTA.

Los controles nominal y Vine/H09 no se usan para **optimizar** ni para fabricar congestión; el objetivo final es evaluar resiliencia de controladores ante comportamientos no nominales inspirados en POLIDriving Quito, **sin extrapolación poblacional**.

## Ubicación

Extraer `H12_14_Auditoria_SOTA_RESCO_v100` dentro de:
`C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

Requisitos: Python y `PyYAML` en `tsc-env`; los tests usan biblioteca estándar, excepto la validación YAML. El repositorio local debe conservar `baselines/RESCO` (no descargar código automáticamente).

## 1. Ejecutar las pruebas

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h1214 = '.\H12_14_Auditoria_SOTA_RESCO_v100'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
$smoke = '.\resultados\h12_12_homologado_20261012_155458_787693_46131e'

python -m unittest discover -s "$h1214\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Tests H12.14 fallidos' }
```

## 2. Plan de solo lectura (sin crear carpeta de resultados)

```powershell
python "$h1214\h12_14_auditar.py" `
    --repo-root $repo `
    --revision-root . `
    --smoke-dir $smoke `
    --mode plan
if ($LASTEXITCODE -ne 0) { throw 'Plan H12.14 fallido: conservar registro' }
```

Resultado deseado: `H12_14_PLAN_OK`. Si falla por un SOTA ausente, **no inventar sustituto**: comprobar que `baselines/RESCO` está presente en tu clon de `framework_RLT`.

## 3. Generar la matriz de compatibilidad y el dictamen

```powershell
python "$h1214\h12_14_auditar.py" `
    --repo-root $repo `
    --revision-root . `
    --smoke-dir $smoke `
    --mode analyze
if ($LASTEXITCODE -ne 0) { throw 'Auditoría H12.14 fallida' }

$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_14_sota_*' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_h12_14.md') -Encoding UTF8
```

Esperado: `H12_14_SOTA_AUDIT_OK`. Archivos: `dictamen_h12_14.md`, `dictamen_h12_14.json`, `matriz_sota_h12_14.csv`.

**Opcional**, si ya completaste H12.13 con `H12_13_PILOT_OK` o `H12_13_TRAINING_OK`, añade `--h1213-run $h1213run.FullName` a los comandos `plan` y `analyze`. El resultado H12.13 no es requisito para auditar fuentes RESCO.

## Fases posteriores obligatorias (no implementadas en H12.14)

1. **H12.15 — adaptadores de control local:** Fixed, MaxPressure, IPPO, MPLight → dominio B1 de **dos acciones**, 5 s por decisión, 0,5 s por microtick, verde mínimo 10 s y amarillo 3 s. Cada adaptación debe documentar en qué se diferencia del código original. Verificar acciones legales, observaciones e invariantes sin entrenar primero. No declarar equivalencia basada únicamente en nombre.
2. **H12.16 — entrenamiento y evaluación B1:** los dos PPO nuevos H12.13, IPPO-PFRL y MPLight-FRAP bajo el mismo dominio físico; semilla y rutas emparejadas; los presupuestos comparables se definen en interacciones del entorno, no épocas. No mezclar resultados entrenados con checks de código.
3. **H12.17 — extensión multiagente:** controlador de las 16 intersecciones de Hangzhou y evaluación real de CoSLight y otros comparadores cooperativos. La observación/espacio de acción puede variar por algoritmo, pero se documenta el dominio físico y el alcance coordinado. Coop-SARG-B1 no equivale a un Coop-SARG multiagente.
4. **H12.18 — resiliencia:** después de certificar integración Vine, H09 e híbrido en H12.12/H12.17, correr nominal/probe/activo con semillas/demanda emparejadas y métricas locales/de red, sin afirmar representatividad poblacional de Quito.

## Criterios de rechazo

No declarar `SOTA_READY` si falta fuente/configuración, si se ha sustituido MPLight por otro modelo, si CoSLight solo controla B1, si hubo saltos verde→verde sin amarillo, si la recompensa no es comparable/documentada, si el checkpoint no está identificado por SHA y presupuesto, si nominal/probe cambian la demanda o si Vine/H09 no tiene exposición verificable.

**Un `H12_14_SOTA_AUDIT_OK` certifica solo que el análisis estático pudo realizarse; deliberadamente mantiene `SOTA_full_comparison=BLOCKED`.**
