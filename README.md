# Propuesta de corrección: integración naturalista

Los tres archivos son una propuesta de trabajo independiente. No se ha modificado el repositorio original ni se han ejecutado simulaciones SUMO.

## Alcance

- `src/copulas/vine_generator.py`: conserva observaciones conjuntas de aceleración y jerk. No combina demanda macro y telemetría micro sin una correspondencia temporal documentada.
- `src/core/latam_chaos_manager.py`: asigna perfiles por vehículo de forma determinista y elimina las detenciones artificiales. Exige un CSV con `tau,sigma,speed_factor` previamente calibrado y validado; **no transforma automáticamente aceleración y jerk en parámetros SUMO**.
- `scripts/validate_copula_polidriving.py`: compara datos empíricos reservados con muestras sintéticas mediante Wasserstein, KS, cuantiles y Kendall tau.

## Condiciones para uso experimental

1. Definir la unidad de observación, segmentación por viaje/conductor y separación de entrenamiento/prueba sin fuga de información.
2. Ajustar la Vine con datos de entrenamiento. Comparar contra muestreo independiente y cópula gaussiana.
3. Calibrar explícitamente el mapeo de cinemática a `tau`, `sigma` y `speed_factor` con una función objetivo sobre trayectorias SUMO. Guardar los perfiles validados en CSV.
4. Repetir la validación en SUMO, con demanda y rutas idénticas entre controladores, y comprobar equivalencia de escenarios.
5. Integrar las nuevas interfaces en `tsc_env.py` y los scripts de evaluación; no sustituir los archivos en producción sin pruebas de integración.

## Ejecución orientativa

```bash
python src/copulas/vine_generator.py --micro-csv data/processed/micro_behavior_train.csv --output data/processed/stress_scenarios_candidate.csv
python scripts/validate_copula_polidriving.py --reference data/processed/micro_behavior_test.csv --generated data/processed/stress_scenarios_candidate.csv --output outputs/validation_candidate.json
```

El generador requiere `numpy`, `pandas`, `scipy` y `pyvinecopulib`. El gestor necesita `traci` al ejecutar `step()` salvo que se inyecte una conexión de pruebas.

## Verificación

Se comprobaron sintaxis, conservación de pares cinemáticos, partición disjunta por conductor y asignación determinista mediante una conexión TraCI simulada. No se han comprobado compatibilidad completa con el proyecto, fidelidad naturalista, ajuste Vine real ni funcionamiento de SUMO.

## Transparencia académica

Los archivos contienen comentarios técnicos ordinarios. No se han incluido marcas decorativas ni referencias innecesarias a herramientas de generación. La procedencia y el uso de herramientas deben declararse cuando así lo exijan la revista, la universidad o los acuerdos entre autores. No se recomienda alterar el historial o la atribución para ocultarlos.
