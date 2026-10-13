# Hallazgos de la auditoría del ZIP H12.5

- Se recibieron **diez archivos Python y un `manifest_sha256.json`**, todos los archivos Python coinciden con los SHA-256 declarados.
- `H10_Vine_H09_Imprudencia_v112/scripts/piloto_hibrido_h10.py` implementa `prepare`, `build_vine_config`, `run_one` y `step_once`.
- `step_once` ejecuta `traci.simulationStep()`, después un `EventObserver`, luego telemetría H09 y finalmente `injector.on_step(traci, step)`. El inyector **no** avanza el tiempo.
- `FixedRosterInjector` de H08b hereda `on_step()` de `StressInjector` (H08). `StressInjector` solo emite `traci.vehicle.setAcceleration(vehículo, aceleración, duración)` cuando supera las guardas, y en modo probe no emite comandos.
- H10 selecciona una cohorte Vine determinista con `h08b.select_exact(ranked, .15)` sobre el baseline H08 validado, y H09 mediante `exact_selection(planned,15,seed)`.
- H10 `prepare()` exige 300 IDs de H09 programados durante 300 segundos y un baseline H08 compatible con semilla, 600 subpasos y hashes de entrada.
- H09 usa `clone_route` sobre el mismo árbol XML para asignar `H09_EXPLORATORIO_V12` y verifica los IDs seleccionados frente a los guardados; no configura un inyector en los TLS.
- El puente H12.2 ya aisló los logs SUMO y realizó un piloto nominal de 4 decisiones y 40 microticks en el ordenador del usuario; ese piloto estaba sobre otra demanda (`hangzhou_minimal.rou.xml`). En H12.5 se usa la referencia original H10, no la demanda mínima.
- Los métodos de H08/H09/H10 **son bibliotecas de escenarios experimentales** y no demuestran una tasa de «conducción imprudente» de Quito.
- La integración aquí construida conserva la secuencia de `on_step` y la cohorte; **no se ha ejecutado en SUMO real** en este entorno de construcción.
