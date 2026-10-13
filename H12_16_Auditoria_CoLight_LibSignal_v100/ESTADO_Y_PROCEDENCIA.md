# Evidencia H12.16 y alcance de verificación

## Hecho mediante revisión del código remoto, 12-10-2026

- **Fuente de los autores:** https://github.com/wingsweihua/colight — commit `04440b722e7f36d7043a3f2ad8e40c3df301fad3`. La clase `CoLightAgent` y el método `MultiHeadsAttModel` están presentes en `CoLight_agent.py`; `requirements.txt` incluye TensorFlow 1.11 y Keras 2.1.
- **Fuente LibSignal:** https://github.com/DaRL-LibSignal/LibSignal — commit `127af9f93902778e556de2eedb2b606c4c9447e6`. `agent/colight.py` utiliza PyTorch Geometric/`torch_scatter`, está registrado e importado desde `agent/__init__.py`.
- El agente registrado usa un grafo con `sparse_adj`, observaciones del conjunto de intersecciones y un conjunto de acciones con `phase_lengths`. Su implementación no es una MLP de cuatro entradas.
- `agent/colight_pytorch_agent.py` es una implementación alternativa no importada en el registro de agentes examinado.
- El ejemplo `configs/sim/sumo1x1_colight.cfg` especifica `cologne1` y no constituye una prueba experimental con Hangzhou.
- En `agent/colight.py` aparecen expresiones `sorted(...)` sin usar el valor devuelto, que deben verificarse frente al orden de adyacencia. **No se ha demostrado que causen un fallo durante una ejecución real.**

Los identificadores exactos de los blobs fuente se conservan en `upstream_pins.json` y H12.16 exigirá esas versiones al usuario.

## Qué demuestran las pruebas locales del paquete

Las pruebas de H12.16 se ejecutan con repositorios Git sintéticos creados en carpetas temporales. Comprueban lectura inmutable de blobs, coincidencia de hashes, protección ante modificaciones, procedencia de H12.14, estructura de código, informe e integridad. **No se descargaron ni ejecutaron los repositorios CoLight o LibSignal completos en el contenedor de pruebas**; esa comprobación real se realizará en el equipo Windows cuando se ejecuten `plan` y `analyze` con ambos clones fijados.

## Qué NO está acreditado

- La calidad ni disponibilidad de checkpoints entrenados de CoLight;
- Equivalencia exacta del entrenamiento TensorFlow 2019 con implementación PyTorch LibSignal;
- Compatibilidad nativa Windows de `torch_scatter` o `torch_geometric`;
- Coincidencia de índices de nodos, orientación de aristas y orden de agentes en runtime;
- Control simultáneo de los TLS de Hangzhou bajo el contrato H12.12;
- Interverdes, amarillo, recompensa y métricas de red en un experimento emparejado;
- Inyección Vine/H09 operando bajo ese contrato multiintersección;
- Inferencias estadísticas de desempeño o resiliencia.
