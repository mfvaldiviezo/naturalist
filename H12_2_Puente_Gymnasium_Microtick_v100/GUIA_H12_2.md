# H12.2 — Puente temporal Gymnasium ↔ SUMO a 0,5 segundos

**Versión 1.0.0 · 12 de octubre de 2026 · paquete experimental de integración, no evaluación de resiliencia.**

## Qué resuelve

La implementación auditada de `TSCEnv` lanza SUMO con `--step-length 1.0` y ejecuta `delta_t=5` llamadas `simulationStep()` por decisión. Los experimentos Vine/H09 H10/H11 se desarrollaron con un **microtick de 0,5 segundos**. Este puente construye, **solo durante el piloto**, una copia instrumental del entorno que fuerza `--step-length 0.5` y ejecuta **10** subpasos por macrodecisión; mantiene `delta_t=5` para que la edad de fase de la observación y de `info` siga expresada en segundos.

El puente verifica que la fuente exacta coincide con el SHA Git **`06095fe94125dcd8e2a7fdd9015740579a9da3ed`** de `tsc_framework/src/core/tsc_env.py`. Si hay divergencias, se detiene sin modificar archivos. Rechaza configuraciones SUMO con `<output>` definido, porque podrían sobrescribir ficheros del usuario. Redirige `*.sumo.log` del entorno a la carpeta nueva de resultados, para no escribir en `traffic_project`.

**No cambia** `traffic_project`, datasets POLIDriving, ZIP originales de los cuatro PPO, scripts H08/H09/H10/H11, ni informes históricos. **No entrena**. En el piloto nominal, la política PPO se carga desde el checkpoint existente para tomar decisiones semafóricas en un horizonte de hasta 20 decisiones.

## Ejecución recomendada: tres fases

Descomprimir `H12_2_Puente_Gymnasium_Microtick_v100.zip` dentro de `C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

### A. Pruebas automáticas (sin SUMO)

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h122 = '.\H12_2_Puente_Gymnasium_Microtick_v100'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
python -m unittest discover -s "$h122\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Tests H12.2 fallaron' }
```

Las 17 pruebas comprueban el parche restringido, protección contra doble paso, duración, bloqueo de comandos de detención, cuotas de aceleración, inputs `.sumocfg` y creación única de resultados.

### B. Preflight y detección de interfaces H10 (sin SUMO)

```powershell
python "$h122\h12_2_puente.py" --repo-root $repo --revision-root .
if ($LASTEXITCODE -ne 0) { throw 'Preflight H12.2 fallo' }

python "$h122\h12_2_puente.py" --repo-root $repo --revision-root . --guardar-auditoria
if ($LASTEXITCODE -ne 0) { throw 'No se pudo guardar la auditoria' }
```

El primero NO escribe. El segundo genera bajo `revision_naturalista\resultados\h12_2_microtick_*` un `preflight_h12_2.json`, `h10_simbolos_h12_2.json` y `dictamen_h12_2.md` (tampoco ejecuta SUMO). `h10_simbolos_h12_2.json` enumera de forma estática clases, funciones y firmas Python de los paquetes `H10_`, `H08*`, `H09_` de primer nivel, sin importar esos módulos ni leer archivos de datos.

### C. Piloto nominal con el modelo PPO: 4 decisiones, 20 segundos

```powershell
python "$h122\h12_2_puente.py" `
  --repo-root $repo --revision-root . `
  --pilot --mode nominal `
  --model ppo_ideal --policy ppo `
  --tls-id B1 --seed 101 --rl-steps 4
if ($LASTEXITCODE -ne 0) { throw 'Piloto nominal H12.2 fallo: revisar error_h12_2.json' }
```

**Precaución:** este paso **sí inicia SUMO** y carga un checkpoint propio mediante SB3/PyTorch. El `.sumocfg` utilizado por defecto es `tsc_framework/sumo_configs/hangzhou.sumocfg` (rutas minimal). No equivale a la demanda `hangzhou_dense.rou.xml` ni a los escenarios emparejados H11; por ello sirve solo para comprobar el contrato temporal y la ejecución Gymnasium.

Salida esperada si el entorno y dependencias locales son compatibles:

```
SMOKE_OK: 4 decisiones, 40 microticks, 0 comandos. Tiempo: 0.0 -> 20.0 s
```

Si SUMO usa otra versión/configuración, alguna entrada está ausente o falla la observación 34D, el piloto se detiene y deja `error_h12_2.json` en carpeta nueva. No afirmar que hubo éxito hasta observar **`SMOKE_OK`** real.

## Sobre integrar Vine/H09

El puente expone un hook **una vez después de cada `simulationStep()` de 0,5 s**, compatible conceptualmente con `FixedRosterInjector.on_step(traci, step)` de H08b. Pero **NO construye automáticamente ese objeto**, ya que sus parámetros, la cohorte congelada, la semilla y los artefactos Vine/H09 deben obtenerse de los archivos reales de H10. El preflight H10 registra las firmas para construir el adaptador fiel en el siguiente paso.

Los modos `probe` y `active` están disponibles **solo con factoría explícita** `--hook-file ... --hook-factory create_hook` que devuelve un objeto con `on_step(traci, tick)` o una función. **NO usar aún**: hasta disponer del adaptador, no se han comprobado sus requisitos completos. Para `active` se requiere además `--ack-active EXPERIMENTAL_ONLY`. No debe interpretarse una simulación que solo carga el `vType` H09 como evidencia de ejecución Vine.

Las llamadas al hook reciben un proxy que prohíbe `simulationStep()` y escrituras habituales como `setSpeed`, `setSpeedMode`, `setStop` y `setTau`; `setAcceleration` únicamente se autoriza en `active`, con `speedMode=31`, duración 0,5 s y cuota. Esta es una **defensa de integración de mejor esfuerzo, no un sandbox de Python**: un hook que importe directamente `traci` podría saltarse ese proxy. Solo utilizar código H10 ya auditado y revisado, y verificar los logs de comandos y hashes.

H09 debe aplicarse a una configuración `.sumocfg` preconstruida que conserve exactamente la demanda/cohortes, no mediante el antiguo gestor `LatamChaosManager` ni su `setSpeed(v,0)`. El `TSCEnv` del overlay se construye forzosamente con `enable_traci_chaos=False`.

## Advertencias científicas que no deben borrarse

- La nueva frecuencia interna 0,5 s es una **variante experimental del simulador**, aunque el periodo de decisión RL continúe siendo de 5 s. **No comparar directamente con resultados históricos SUMO 1 s**, ni con H11, sin igualdad de escenarios, demanda, semillas y condiciones.
- La semántica de cambios de fase/amárillo de `TSCEnv` heredado no se ha corregido con este puente. Se comprobará en la revisión de control semafórico anterior a H13; no presentarlo como control semafórico físicamente validado.
- La métrica `delay` histórica del entorno está basada en la suma instantánea de esperas por carril y necesita armonización de estimandos antes de resultados del artículo.
- No inferir prevalencia representativa de Quito, imprudencia, causalidad de cruce rojo ni fidelidad cinemática de jerk.
- No usar `run_all_eval.ps1` para afirmar que se evaluó CoLight neuronal; esa suite carga `CoLightAgent` heurístico.

## Archivos finales del piloto

- `preflight_h12_2.json`: SHA origen, checkpoint, dependencias del `.sumocfg`, símbolos H10, contrato temporal.
- `h10_simbolos_h12_2.json`: identificación de clases y firmas de los scripts H10/H08/H09 locales.
- `h12_2_tsc_env_overlay.py`: **copia derivada** del entorno con parche exacto; no está en GitHub ni reemplaza al original.
- `sumo_stderr.log`: log de SUMO confinado en la carpeta H12.2.
- `smoke_h12_2.json`: lista de decisiones, microticks, recompensas descriptivas y comandos.
- `error_h12_2.json`: excepciones del piloto, cuando corresponde.
- `dictamen_h12_2.md`: explicación de alcance y limitaciones.

## Qué enviar al chat

La salida de **A, B y C** (si C alcanza `SMOKE_OK`); y, si la integración H10 no aparece claramente, copiar solo las entradas con `FixedRosterInjector` o `on_step` de `h10_simbolos_h12_2.json`. Con ello podremos preparar la factoría auténtica de Vine/H09 sin inventar los argumentos del generador.
