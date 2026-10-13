# H12.18 — LibSignal CoLight: puente de observación y grafo

**Estado:** `H12_18_COLIGHT_SHADOW_FORWARD_OK`. Solo evidencia de contrato y, cuando corresponde, forward de un modelo con pesos aleatorios.

- Upstream fijado: `127af9f93902778e556de2eedb2b606c4c9447e6`.
- Arquitectura original sin reescribir: clases de `agent/colight.py::ColightNet` cargadas mediante AST aislado para evitar importaciones CityFlow. No se ha importado el agente/entrenador completo.
- Intersecciones: 12. Aristas dirigidas: 32. Orden único: `A1, A2, B0, B1, B2, B3, C0, C1, C2, C3, D1, D2`.
- Entrada del adaptador: lane_count instantáneo `(12,4)` (carriles entrantes únicos ordenados, relleno cero), **NO** el estado 34D.
- Dos acciones correspondientes a fases verdes físicas `[0,2]`; si hay `shadow`, las recomendaciones de CoLight **no se ejecutan**.
- Sin checkpoint; sin entrenamiento; sin Vine/H09; sin comparaciones SOTA, calidad o resiliencia.
- Fuente de carriles: `net.xml` y TraCI directo. Esta adaptación no certifica equivalencia bit a bit con el generador interno de LibSignal.
- La alineación de los tensores de entrada y aristas no certifica aún la semántica total del World/Trainer nativo de LibSignal.

## Gates

- H12.17 SUMO real: validado por manifiesto, reporte y SHA.
- H12.16 código original: validado por commit, blob SHA-1 y reporte.
- Modelo LibSignal PyG/Scatter (solo arquitectura aislada): forward ejecutado con pesos aleatorios.
- Acciones CoLight sobre SUMO: **NO**; aplicado exclusivamente controlador de prueba H12.17.
- Entrenamiento, checkpoint auténtico y evaluación Vine/H09: **BLOQUEADOS**.
