# H12.5 v1.0 — Puente H10 v112 ↔ PPO/Gymnasium (Vine/H09)

## Qué contiene

Se revisaron los diez archivos Python compartidos, y su manifiesto SHA-256 coincidió 10/10. Este paquete NO incluye ni modifica copias de H08/H09/H10/H11/H12, datos, pesos ni resultados anteriores. Solo entrega un orquestador nuevo y sus pruebas.

**Propósito inmediato:** comprobar en SUMO real que el PPO `ppo_ideal` conserva decisiones cada 5 s con microticks de 0,5 s y que un hook `probe` del inyector H08b/H10 original no altera el tráfico frente al nominal. Hasta completar la prueba, la integración es **candidata, no verificada en Windows**.

## Contrato preservado

- Fuente TSCEnv de GitHub fijada por H12.2: blob SHA-1 `06095fe94125dcd8e2a7fdd9015740579a9da3ed`; se crea overlay bajo `resultados`.
- Fuentes H10 v112, H09 v12, H08b/H08/H06/H03/H04 y H12.2 comprobadas contra SHA-256 del ZIP aportado.
- Una sola sesión TraCI y una única llamada `simulationStep()` por microtick, desde Gymnasium.
- Secuencia dentro del microtick: avanzar SUMO → medir tráfico → ejecutar `FixedRosterInjector.on_step` original; efecto y confirmación en microtick posterior.
- Decisión PPO cada 5 segundos = 10 subpasos de 0,5 segundos; `delta_t` permanece en 5 en `TSCEnv`.
- Cohorte Vine exacta seleccionada en el baseline H08 auditado de **600 microticks, semilla 101**, y H09 seleccionada entre los **300 vehículos programados** para 300 s. No se vuelve a seleccionar a partir de la demanda que aparece en el episodio PPO.
- Configuración Vine H10 protegida (`penetration=.15`, cuota de 2 comandos por microtick, 20 por ventana de 60 s, 12 por vehículo, enfriamiento de 8 microticks, `speedMode=31`). Se llama al original `load_frozen_cohorts`, que *reajusta determinísticamente* el kernel desde cohortes H01 congeladas del pipeline anterior, sin acceder a datos brutos; no es una nueva calibración de Quito.
- En el piloto corto se cierra la ventana Vine 0,5 s antes del final para que las acciones puedan confirmarse en `t+Δt`; esta restricción debe declararse si se comparan conteos contra H10 de 300 s.
- Para H09 se clona el mismo árbol XML de H10, se verifica la asignación de vTypes y se comprueba que IDs, salidas, rutas y atributos no intervenidos permanecen iguales.
- El ZIP solo incluye scripts nuevos, no el material de investigación protegido.

## Paso 1: instalación y pruebas (no inicia SUMO)

Extraiga la carpeta `H12_5_Integracion_Vine_Gymnasium_v100` del ZIP directamente dentro de `C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h125 = '.\H12_5_Integracion_Vine_Gymnasium_v100'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
python -m unittest discover -s "$h125\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron tests H12.5' }
```

El paquete pasó 18 pruebas unitarias en el entorno de construcción. No hay SUMO, TraCI ni Stable-Baselines3 disponibles allí; **las simulaciones reales no se han probado**.

## Paso 2: plan de solo lectura, sin SUMO y sin escribir resultados

```powershell
python "$h125\h12_5_integrar.py" --revision-root . --repo-root $repo --mode plan
if ($LASTEXITCODE -ne 0) { throw 'Falló el plan H12.5; compartir error y detenerse' }
```

Este paso verifica versiones, localiza el baseline H08 compatible de 600 microticks y comprueba los insumos originales H01/H09. No reentrena ni ejecuta SUMO. Puede detectar varias referencias H08 compatibles: si es así, **no elegir al azar**; revise cuál utilizó H10 y pase la opción `--reference-baseline-dir 'RUTA'`.

## Paso 3: nominal vs probe, SUMO real

Solo después de `PLAN_OK`, ejecute:

```powershell
python "$h125\h12_5_integrar.py" --revision-root . --repo-root $repo --mode pair --model ppo_ideal --seed 101 --rl-steps 4 --tls-id B1
if ($LASTEXITCODE -ne 0) { throw 'Pareado H12.5 no acreditado; revisar ERROR_h12_5.json' }
```

El par consta de dos ejecuciones consecutivas de 20 s (40 microticks cada una). En nominal no se activa Vine. En probe se llama al **mismo inyector original** en modo de solo propuestas y lecturas. El programa exige que ambas trazas temporales de telemetría sean idénticas mediante SHA-256 y que el conteo de comandos sea cero.

Resultado esperado si se satisface el contrato: `PAIR_OK` y `PAREADO_NOMINAL_PROBE_OK`. Si hay diferencias, la auditoría **falla**; no se ocultan ni se interpretan como efectos Vine.

El resultado se escribe en una nueva carpeta `resultados\h12_5_pair_...`. Puede enviar aquí la salida PowerShell y el `pareado_h12_5.json`.

## Modos posteriores (NO ejecutar antes de validar pair)

Una vez acreditado el par, el programa deja disponibles pilotos cortos:

- `--mode active`: Vine protegido original; exige dos acuses explícitos, al menos un comando aplicado y confirmación en `t+Δt`.
- `--mode h09`: rutas H09 exploratorias con cohortes congeladas; verifica XML, tipos y ausencia de comandos Vine.
- `--mode hybrid`: Vine protegido + H09 bajo el mismo control PPO; requiere todos los chequeos anteriores.

Acuses para modos de intervención: `--ack-active EXPERIMENTAL_ONLY --ack-time-scale NOT_CALIBRATED`. Se recomienda esperar el análisis del `PAIR_OK` para decidir si procede probarlos.

## Restricciones científicas — no negociables

1. Los pilotos de 20 segundos **no** estiman resiliencia ni prueban una distribución representativa del comportamiento de Quito. Las cohortes y los perfiles son escenarios exploratorios.
2. `TSCEnv` aplica la transición de fase heredada mediante `traci.trafficlight.setPhase`, sin demostrar que respeta tiempos amarillos/interverdes. Hay que auditar y corregir ese contrato antes de la batería de evaluación definitiva.
3. `TSCEnv` controla `B1` con 34D y 4 acciones; esto **no es equivalente** a evaluación MARL auténtica sobre todas las intersecciones. RESCO/CoSLight deben evaluarse por un protocolo comparable aparte.
4. Los checkpoints H-SARG y Coop-SARG tienen presupuestos de entrenamiento diferentes (20.480 frente a 1.007.616 pasos). No atribuir diferencias exclusivamente a la arquitectura.
5. H10 guarda resultados de sus pilotes sin RL. Este paquete crea nuevas salidas; no reinterpreta automáticamente métricas históricas de H10/H11 como evaluaciones de controladores.
6. El modo de prueba `probe` no emite comandos. La lectura pasiva se realiza antes de `on_step`; la instrumentación H11.2 completa para eventos de semáforos se añadirá una vez comprobada la integración básica.
7. El plan usa una referencia H08 ligada a **semilla 101**; para otras semillas hay que construir un baseline H08 equivalente antes de comparaciones multi-semilla.
