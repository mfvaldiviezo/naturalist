# H12.16 — Matriz de decisión para integrar CoLight sin sustitutos

| Criterio | Original de los autores | LibSignal upstream | Requisito en la tesis |
|---|---|---|---|
| Implementación | `CoLight_agent.py` | `agent/colight.py` | Auditar los commits exactos y hashes |
| Algoritmo | Atención multiagente basada en Q-learning | GNN con atención PyTorch + Q-learning | Mantener mecanismo de atención entre nodos, nunca MLP equivalente nominal |
| Dependencias | TensorFlow 1.11, Keras 2.1 | torch, torch-geometric, torch-scatter | Validar compatibilidad Windows en entorno aislado |
| Simulador | Origen CityFlow | LibSignal SUMO/CityFlow | Hangzhou SUMO original y microtick 0.5s |
| Observación | Características por intersección + vecinos | `lane_count`, fase opcional, grafos | Adaptador con nodos en orden validado; no forzar 34D global |
| Acción | Según fases del entorno original | `phase_lengths` y máscara | Dos verdes reales por intersección si lo confirma red; amarillo 3 s |
| Alcance | Multiintersección | Multiintersección | H12.17, no B1 aislado |
| Demanda | Experimental original | Configuraciones propias | Red/demanda fijadas por SHA idénticas a H12.12/H12.14 |
| Reproducibilidad | Commit pin y original | Commit pin y original | Semillas de aprendizaje/SUMO, presupuesto y hardware |
| Estado del hito | Código auditado por referencia | Código auditado por referencia | **Sin entrenamiento ni evaluación de resiliencia** |

**Alerta de denominación:** el `CoLightAgent` histórico simplificado no puede reetiquetarse como CoLight neuronal de CIKM 2019. Ni CoSLight ni CoordLight son sustitutos intercambiables de CoLight.

**Observaciones específicas de LibSignal:** `agent/colight_pytorch_agent.py` es un archivo alternativo distinto del que se registra en `agent/__init__.py`; el ejemplo `sumo1x1_colight.cfg` utiliza Cologne1; y varias expresiones `sorted(...)` no modifican en sitio el orden del listado. Estas advertencias requieren comprobación dinámica posterior.

**Próxima entrega sugerida H12.17:** contrato multi-TLS SUMO sobre las intersecciones reales de Hangzhou, observabilidad por nodo, grafo de adyacencia comprobado por enlaces, amarillos por intersección y smoke nominal/probe, antes de conectar/entrenar CoLight y CoSLight.
