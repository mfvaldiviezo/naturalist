# H12.6 — Auditoría comparativa offline del piloto `ppo_ideal` de 60 segundos

## Objetivo

Comparar las salidas ya generadas de H12.5: un `pair` nominal/probe de 60 s frente a un `active` Vine protegido de 60 s, con semilla 101. Este paquete **no ejecuta SUMO**, no accede al dataset y no crea ni modifica checkpoints. No requiere importar el repositorio ni el inyector.

## Qué valida

- Estado H12.5 `SMOKE_OK` en las tres salidas, `PAIR_OK` y SHA idéntico nominal/probe.
- Mismos 12 ciclos de PPO y 120 microticks de 0,5 s, tiempo 0–60 s; checkpoints SHA-256 idénticos.
- SHA-256 iguales de red, ruta, configuración SUMO original y fuentes H10; referencia H08 congelada idéntica. El SHA del `sumocfg` *overlay* no se exige idéntico porque su ruta de salida cambia.
- Exactamente 20 comandos en el activo, 20 confirmados, 0 pendientes, 6 vehículos, ventana de 60 s con 20 órdenes, sin `safety_halt`; 20 filas `command_issued` en el CSV originales y `matched_t_plus_dt` positivo.
- Sin colisiones ni inicios de teletransporte en las tres trazas y tiempo continuo en cada microtick.
- Error de aceleración observada frente a la solicitada en **todos los 20 comandos**.
- Métricas descriptivas comparables: velocidad media temporal y ponderada, vehículo-segundos detenidos, llegadas, salidas, cola y demora *proxy* internas al ambiente, Gini y recompensa, primera divergencia cinemática y decisiones PPO diferentes.

No se estiman intervalos de confianza ni significancia: hay una sola semilla y un episodio corto. Tampoco se estima la representatividad de Quito ni la resiliencia general de los controladores.

## Instalación

Descomprime `H12_6_Auditoria_Comparativa_PPO_Vine_v100` directamente dentro de `C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h126 = '.\H12_6_Auditoria_Comparativa_PPO_Vine_v100'
python -m unittest discover -s "$h126\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas H12.6' }
```

## Auditoría de tus dos experimentos ya terminados

```powershell
$pair = '.\resultados\h12_5_pair_20261012_003832_072497_415c5b'
$active = '.\resultados\h12_5_active_20261012_003551_055596_3ef849'

python "$h126\h12_6_auditar.py" `
    --pair-dir $pair `
    --active-dir $active `
    --results-root '.\resultados'

if ($LASTEXITCODE -ne 0) { throw 'H12.6 NO acreditado: deténgase y comparta el error' }
```

Cuando los archivos y las invariantes sean correctos, saldrá `H12_6_AUDITORIA_OK` junto con una ruta nueva: `resultados\h12_6_auditoria_...`.

Allí habrá dos archivos:
- `auditoria_h12_6.json`: dictamen estructurado, métricas y deltas.
- `dictamen_h12_6.md`: informe legible en español para análisis, sin hacer inferencias causales ni generalizaciones de resiliencia.

El código no edita las carpetas nominal/probe/active; solo crea una carpeta de auditoría nueva.

## Próximo paso tras superar la auditoría

Ejecutar `--mode h09` de H12.5 con las mismas 12 decisiones, semilla 101 y `ppo_ideal`, después `--mode hybrid` (combinación protegida). Con H09 se exige verificar el XML de vTypes y cuántos seleccionados efectivamente entraron en el horizonte de 60 s; 45 es la cohorte programada de 300 s, no necesariamente todos circulan durante el piloto.
