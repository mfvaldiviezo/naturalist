# H12.15 v1.0.0 — Baselines físicos B1 (Fixed y MaxPressure proyectado)

**Propósito:** siguiente hito tras `H12_14_SOTA_AUDIT_OK`. Construye dos **adaptadores físicos auditables**, todavía **NO implementaciones originales RESCO ejecutadas ni controladores SOTA certificados**. No importa modelos PPO ni entrena redes. Reutiliza las fuentes intactas del entorno H12.12 y sus controles de ámbar/verde mínimo.

## Hallazgo estructural que condiciona el experimento

RESCO (`config/signal.yaml`) declara ocho `phase_pairs` para Hangzhou, y `B1.fixed_timings` tiene ocho valores. El archivo físico `hangzhou_4x4.net.xml` posee únicamente dos verdes en B1 (`0` y `2`) con amarillos de 3 s (`1` y `3`). Tras inspección de enlaces `linkIndex`, se pueden asociar sin inventar semáforos los pares originales RESCO `0=[S-S,N-N]` y `4=[W-W,E-E]` a las dos fases físicas. **Los otros seis pares no son seis fases físicas disponibles.** El paquete falla ante una geometría o mapeo diferente.

- `fixed_b1`: calendario derivado de la red física: verde objetivo **42 segundos**, muestreado cada cinco segundos. No equivale al plan `FixedAgent` original de RESCO con ocho posiciones.
- `maxpressure_resco_projected_b1`: proyecta el esquema de `states.mplight` y `MAXPRESSURE/MaxAgent/WaveAgent` de RESCO a pares 0/4, midiendo presión como cola de entrada menos cola downstream por dirección. Utiliza `getLastStepHaltingNumber` de TraCI como **proxy** de `Lane.queued` RESCO (que guarda historiales a nivel de vehículo); **no se puede presentar como ejecución exacta de RESCO**.

Esto es una integración técnica del contrato B1, no una nueva afirmación de superioridad de controladores ni un sustituto de la futura homologación de IPPO-PFRL, MPLight-FRAP o CoSLight multiagente.

## Ubicación

Descomprimir la carpeta `H12_15_Baselines_Fisicos_B1_v100` en:
`C:\Proyecto_Tesis_Final_V1\revision_naturalista`

No modificar ni sobrescribir `H12_12_Entorno_Homologado_B1_v100`, `H12_14_Auditoria_SOTA_RESCO_v100`, `baselines/RESCO` ni los modelos históricos.

## 1. Pruebas automatizadas

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h1215 = '.\H12_15_Baselines_Fisicos_B1_v100'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
$smoke = '.\resultados\h12_12_homologado_20261012_155458_787693_46131e'
$audit = '.\resultados\h12_14_sota_20261012_162718_504371_4d2424'

python -m unittest discover -s "$h1215\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Tests H12.15 fallidos' }
```

Esperado: **51 tests OK**; estas pruebas son sintéticas/mocks, no ejecutan SUMO.

## 2. Plan estático (SIN ejecutar SUMO ni crear carpeta)

```powershell
python "$h1215\h12_15_baselines.py" `
    --repo-root $repo `
    --revision-root . `
    --smoke-dir $smoke `
    --h1214-dir $audit `
    --mode plan
if ($LASTEXITCODE -ne 0) { throw 'Falló preflight H12.15' }
```

Esperado `H12_15_PLAN_OK`. Se vuelven a comprobar los SHA-256 de la evidencia H12.12, los archivos auditados H12.14, el XML de la red, el YAML original de RESCO y los mapeos físicos.

## 3. Smoke SUMO: misma demanda/semilla, dos baselines, 120 s cada uno

Ejecutar **solo después** de `PLAN_OK`:

```powershell
python "$h1215\h12_15_baselines.py" `
    --repo-root $repo `
    --revision-root . `
    --smoke-dir $smoke `
    --h1214-dir $audit `
    --mode smoke `
    --seed 101 `
    --rl-steps 24 `
    --min-green 10 `
    --ack-projection PHYSICAL_PROJECTIONS_ONLY `
    --ack-online-control TLS_OVERRIDE

if ($LASTEXITCODE -ne 0) { throw 'H12.15 no fue acreditado' }
```

Esperado `H12_15_PHYSICAL_SMOKE_OK`. Ejecutará cada baseline de manera independiente: 24 decisiones × 10 microticks de 0,5 s = **120 segundos por baseline**. La acción del controlador pasa siempre por el autómata H12.12 (verde mínimo, amarillo real); los demás semáforos de Hangzhou siguen sin control RL centralizado.

Un error conserva `ERROR_h12_15.json` en la última carpeta generada (los datos de una simulación aprobada antes del fallo permanecen allí). Si ocurren colisiones en SUMO, la auditoría bloquea el éxito y guarda `telemetria_no_acreditada.json`.

## 4. Mostrar el informe

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_15_baselines_b1_*' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_h12_15.md') -Encoding UTF8
```

Los resultados se guardan **sin sobrescribir** en un directorio con nombre único:
- `manifiesto_h12_15.json`: SHA, ámbitos, contrato, proyecciones y versiones de entorno.
- `fixed_b1/pilot.json`, `maxpressure_resco_projected_b1/pilot.json`: decisiones 34D, colas, recompensas, presión, eventos TLS y seguridad.
- `resultado_h12_15.json`, `dictamen_h12_15.md`: resumen y límites de interpretación.

## Próximas puertas de homologación

1. **H12.13:** piloto de 64 transiciones por cada nuevo extractor para garantizar que carga y guarda checkpoints; no atribuir desempeño con tan pocos pasos.
2. **H12.16:** adaptadores y entrenamiento genuino de IPPO-PFRL y MPLight-FRAP: preservar arquitecturas, definir entradas originales y espacio efectivo de acciones. Decidir si se requiere cambiar red física para disponer de ocho fases; si se cambia, homologar **todos** los controladores nuevamente.
3. **H12.17:** entorno multiintersección y CoSLight con cooperación real, no un solo B1.
4. **H12.18:** homologar inyección Vine/H09 en el entorno nuevo, ensayos emparejados con semillas y métricas tanto locales como de red.

**H12.15 no genera ni certifica modelos SOTA.** Su valor es demostrar que el control físico admite baselines auditables y registrar rigurosamente dónde difieren del RESCO original.
