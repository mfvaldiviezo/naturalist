# H12.7 — Diagnóstico del estado 34D de B1

**Propósito:** verificar qué observa realmente PPO durante 60 segundos y qué vehículos están presentes en los carriles de B1. NO evalúa resiliencia; NO recalibra Vine; NO modifica checkpoints, código fuente histórico, red ni rutas.

## Hallazgo que motiva H12.7

H12.6 detectó 20 comandos Vine confirmados, perturbación cinemática desde t=4.5 s y las mismas 12 decisiones PPO (acción 0). Cola, espera, Gini y recompensa del entorno fueron siempre cero. No se sabe aún si B1 estuvo vacío, si sus sensores informaron cero genuinamente o si la representación de estado es insuficiente.

El `TSCEnv` fijado por Git SHA en H12.2 construye 34 componentes (12 cola, 12 espera, 4 presión, 4 fase y 2 edad), pero `_outgoing_lanes` es un placeholder vacío. **No interpretar esas cuatro componentes como presión entrada − salida validada.**

## Instalación

1. Descomprima `H12_7_Diagnostico_Estado_B1_v100.zip` directamente dentro de `C:\Proyecto_Tesis_Final_V1\revision_naturalista`.
2. Mantenga extraídos los paquetes H12.2, H12.5 y los scripts fuente H08/H09/H10 tal como están.
3. No copie ni renombre manualmente los informes anteriores.

## A. Pruebas de código

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h127 = '.\H12_7_Diagnostico_Estado_B1_v100'
python -m unittest discover -s "$h127\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron tests H12.7' }
```

## B. Piloto diagnóstico emparejado

Ejecuta dos sesiones de 60 s, nominal y Vine activo (semilla 101, `ppo_ideal`, B1). Aunque es necesaria una repetición breve para observar las entradas 34D no guardadas en H12.5, **no es una nueva evaluación de robustez**.

```powershell
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
$nom = '.\resultados\h12_5_pair_20261012_003832_072497_415c5b\nominal\piloto_h12_5.json'
$act = '.\resultados\h12_5_active_20261012_003551_055596_3ef849\active\piloto_h12_5.json'

python "$h127\h12_7_estado_b1.py" `
    --revision-root . `
    --repo-root $repo `
    --model ppo_ideal `
    --seed 101 `
    --rl-steps 12 `
    --max-commands 30 `
    --tls-id B1 `
    --old-nominal $nom `
    --old-active $act `
    --ack-active EXPERIMENTAL_ONLY `
    --ack-time-scale NOT_CALIBRATED

if ($LASTEXITCODE -ne 0) { throw 'H12.7 no acreditado' }
```

**Criterio para `H12_7_DIAGNOSTICO_OK`:** misma red, rutas, fuentes, checkpoint, semilla y horizonte; confirmación de comandos; y SHA de trayectoria idéntico a H12.5 anterior para **cada** condición. Si la instrumentación altera las simulaciones, debe detenerse en `ERROR_h12_7.json`.

## C. Leer resultados

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_7_estado_b1_*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_estado_b1.md') -Encoding UTF8
```

El paquete entrega `dictamen_estado_b1.md`, `analisis_estado_b1.json`, dos carpetas originales de ejecución H12.5 con el nuevo campo `h12_7_diagnostic`, y hashes de reproducibilidad.

## Interpretación

- **Vehículos B1 = 0 en todos los microticks:** 60 s insuficientes para observar tráfico local, no acusar defecto del PPO.
- **Vehículos B1 presentes, pero cola/espera = 0:** posible movimiento sin detenciones. La recompensa cero no demuestra fallo por sí sola.
- **Vehículos detenidos en B1 con métricas internas cero:** revisar carriles/semántica de observación y cálculos; NO evaluar robustez aún.
- **Estados 34D nominal/activo distintos con acciones iguales:** el controlador recibió entradas distintas, pero eligió la misma acción; no se puede deducir adaptación o insensibilidad solo de eso.
- **Estados 34D iguales con perturbación global:** puede existir falta de exposición del agente al episodio de comportamiento no nominal, o sensor/mapeo inadecuado.

**Limitaciones:** un episodio corto, condiciones sin calibración temporal representativa de Quito, PPO controla solo B1; interverdes/amarillos y SOTA multiagente siguen pendientes. No se editan fuentes del repositorio.
