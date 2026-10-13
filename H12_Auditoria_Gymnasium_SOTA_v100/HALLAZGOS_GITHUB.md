# Hallazgos verificados en rama `main` de GitHub — H12

**Repositorio:** <https://github.com/mfvaldiviezo/framework_RLT>  
**Árbol auditado:** `fe124c599104f8a4ef8b1fa7b41a92a7da77c646`  
**Método:** lectura estática de ficheros a través de integración GitHub. No se corrió código del repositorio ni SUMO.

## Componentes

1. [`tsc_framework/src/core/tsc_env.py`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/tsc_framework/src/core/tsc_env.py#L152-L195): hereda de `gym.Env`, describe observación 34D y espacio de 4 acciones; en `step()` implementa 5 valores de retorno Gymnasium. `delta_t` se usa como **número de invocaciones** `traci.simulationStep()` (líneas ~481–488), por lo que la duración física depende de `--step-length` de SUMO. Los escenarios H11 con `step-length=0.5 s` requieren puente temporal explícito.
2. [`tsc_framework/src/rl_env/sumo_env.py`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/tsc_framework/src/rl_env/sumo_env.py#L70-L90): segundo entorno `SumoRLEnv`, también Gymnasium, pero con lógica de fases y observaciones propia. No asumir equivalencia ni intercambiar checkpoints sin validar espacios.
3. [`tsc_framework/scripts/run_evaluation.py`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/tsc_framework/scripts/run_evaluation.py#L40-L82): `CoLightAgent` de esta ruta **NO** representa la arquitectura original CoLight; es heurística softmax sobre colas de grupos de carriles. `MaxPressureAgent` selecciona `argmax` de valores `obs[24:28]` (líneas ~58-64); auditar la definición de esa observación para compararla con un MaxPressure formal.
4. [`run_resco.py`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/run_resco.py#L29-L41): asigna el alias `colight -> CoSLight`. La implementación CoSLight existe bajo `baselines/RESCO/resco_benchmark/agents/policy/CoSLight`. CoSLight **no debe llamarse CoLight** sin justificar su identidad algorítmica.
5. [`evaluate_marl.py`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/evaluate_marl.py#L64-L74): etiqueta CoLight, pero lo muestra como “CoSLight (SOTA)” al ejecutar ruta RESCO; potencial ambigüedad editorial que exige precisar el algoritmo.
6. [`run_all_eval.ps1`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/run_all_eval.ps1#L24-L34): muestra modelos `ppo_ideal`, `ppo_chaos`, `ppo_coop_ideal`, `ppo_coop_chaos` y baselines `fixed`, `maxpressure`, `colight`; invoca específicamente el evaluador local que contiene `CoLightAgent` heurístico.
7. [`tsc_framework/src/core/latam_chaos_manager.py`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/tsc_framework/src/core/latam_chaos_manager.py#L100-L119): cambia `setSpeed(v_id,0.0)` por interacción de peatones/bloqueo de intersección. [`transfer_eval_n30_robust.py`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/tsc_framework/transfer_eval_n30_robust.py#L779-L794) tiene hard blocking análogo. Esto sigue siendo una condición de estrés distinta de la inyección H10 Vine/H09 validada.
8. [`tsc_framework/outputs/models`](https://github.com/mfvaldiviezo/framework_RLT/tree/main/tsc_framework/outputs/models): cuatro checkpoints de ~2.7MB disponibles, más `best_model` y checkpoints intermedios. El inventario local **no ha sido ejecutado** y los pesos no fueron cargados; no se presume validez ni presupuestos pareados.
9. [`baselines/RESCO/README.rst`](https://github.com/mfvaldiviezo/framework_RLT/blob/main/baselines/RESCO/README.rst): incluye algoritmos de benchmark, métricas y modelos de control estáticos/por aprendizaje. Su presencia como código fuente NO demuestra que las comparaciones históricas se hayan ejecutado en SUMO con las mismas condiciones.

## Consecuencias para artículo y tesis

- **SOTA:** describir los baselines por su **implementación real**, no por el alias del CLI. Un controlador de cola con softmax no acredita comparación contra el CoLight original.
- **Gymnasium:** antes de añadir inyección H10 Vine/H09, verificar que el entorno no ejecute dos veces `simulationStep()` ni descuadre el reloj al usar 0.5s de microstep.
- **Diseño factorial:** controlar demanda, topología, semáforos, semillas y presupuesto de decisiones para aislar nominal/Vine/H09/híbrido.
- **Controladores:** usar checkpoints y código congelado, no reentrenar salvo necesidad futura científicamente justificada; verificar el protocolo de entrenamiento existente.
- **Seguridad metodológica:** `setSpeed(v,0)` produce intervención externa, no una muestra naturalista. No usar los viejos resultados de bloqueo para atribuir efectos exclusivamente a Vine.

**Alcance de esta revisión:** versión del repositorio disponible en GitHub, no necesariamente idéntica al checkout de Windows ni a los ZIP que el investigador ejecutó en H11. El script H12 compara los hash de los archivos locales y declara divergencias, sin intentar repararlas.
