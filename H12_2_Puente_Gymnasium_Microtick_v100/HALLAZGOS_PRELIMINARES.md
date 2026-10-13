# H12.2 — Decisiones de diseño y trazabilidad

- Repositorio `mfvaldiviezo/framework_RLT`, `main`, archivo `tsc_framework/src/core/tsc_env.py` blob SHA Git `06095fe94125dcd8e2a7fdd9015740579a9da3ed`.
- `TSCEnv._launch_sumo` fija `--step-length 1.0`; `TSCEnv.step` hace `for _ in range(self.delta_t): traci.simulationStep()`; `delta_t=5` para el evaluador histórico. El código también usa `delta_t` para `phase_age`, de manera que **no** corresponde sustituir ciegamente `delta_t=10`.
- H12.2 trabaja con overlay y cambia solo: longitud microtick 1.0 → 0.5; subpasos 5 → 10, manteniendo edad de fase 5 s; ruta del log SUMO aislada en `resultados/`.
- Confirmación estructural de checkpoints realizada por el usuario: todos observan `(34,)`, producen `Discrete(4)`, `HSARGExtractor` en PPO, `CoopSARGExtractor` en Coop. Sesgo de presupuesto: 20.480 vs 1.007.616 pasos.
- La interfaz H08b descrita en el informe H10 es `FixedRosterInjector.on_step(traci, step)`; `on_step` no avanza SUMO. La firma del constructor debe inspeccionarse en el equipo local.
- La vieja ruta `LatamChaosManager` usa `setSpeed(v,0)`; el overlay se construye con `enable_traci_chaos=False`.
- RESCO SOTA: `run_evaluation.py` usa una clase `CoLightAgent` heurística. `run_resco.py` referencia CoSLight real (código incluido en RESCO), pero utiliza un solo episodio y la configuración por defecto es entrenamiento; por ello los resultados viejos no acreditan evaluación de un CoSLight ya entrenado.
- Escenarios RESCO versionados `hangzhou.rou.xml` (3.600 vehículos) vs `hangzhou_latam.rou.xml` (2.821 vehículos); diferencia 779, que confunde atribución de diferencias solo a conducta.

**Alcance actual:** plataforma preparatoria con piloto nominal de sincronización; **el ensayo híbrido conectado a controlador RL todavía depende de instanciar correctamente los objetos H10 reales**.
