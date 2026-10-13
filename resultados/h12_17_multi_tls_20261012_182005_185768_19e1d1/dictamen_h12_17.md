# H12.17 — Contrato físico y grafo multi-TLS Hangzhou

**Estado:** `H12_17_MULTI_TLS_SMOKE_OK`. Ejecución: **12** decisiones, **120** microticks, **30** entradas en amarillo.

**Afirmación acotada:** el piloto usa política de prueba escalonada, NO CoLight, NO Coop-SARG ni controlador entrenado.

## Grafo para futuro CoLight

- **12 nodos:** `A1, A2, B0, B1, B2, B3, C0, C1, C2, C3, D1, D2` (orden fijo, compartido por acciones y filas observación).
- **32 aristas dirigidas:** derivadas de `<edge from=... to=...>` con ambos extremos bajo TLS.
- `edge_index` 2×32, sin self-loops; grafo sin pesos y sin inferencia de adyacencia a partir de distancias.
- Nodo→fila: `node_to_index` en `manifiesto_h12_17.json`.
- **LibSignal CoLight NO ha consumido todavía este grafo**; no se declara identidad de su nodo interno.

## Semáforos

| TLS | Carriles de entrada únicos | Verdes físicos | Amarillos (índice XML) |
|---|---:|---|---|
| A1 | 3 | [0, 2] | [1, 3] |
| A2 | 3 | [0, 2] | [1, 3] |
| B0 | 3 | [0, 2] | [1, 3] |
| B1 | 4 | [0, 2] | [1, 3] |
| B2 | 4 | [0, 2] | [1, 3] |
| B3 | 3 | [0, 2] | [1, 3] |
| C0 | 3 | [0, 2] | [1, 3] |
| C1 | 4 | [0, 2] | [1, 3] |
| C2 | 4 | [0, 2] | [1, 3] |
| C3 | 3 | [0, 2] | [1, 3] |
| D1 | 3 | [0, 2] | [1, 3] |
| D2 | 3 | [0, 2] | [1, 3] |

El lector H12.17 clasifica como **amarillo cualquier etapa con y/Y**, incluso si otras conexiones conservan G/g. Corrige el riesgo observado al generalizar H12.12 a más intersecciones, sin alterar la fuente H12.12.

## Observación y actuación

- Matriz de observación `(12, 34)`, una fila por TLS, usando exactamente la fórmula de H12.12.
- `MultiDiscrete([2]×12)`, acción 0→fase verde 0, acción 1→fase verde 2.
- Cada transición respeta verde mínimo y ejecuta íntegramente la fase amarilla del `net.xml`.
- Rutas/red y fuentes protegidas por SHA-256; sin renombrar checkpoints anteriores.

## Puertas pendientes

| Área | Resultado |
|---|---|
| Protocolo B1 H12.12 | Anclado al smoke y manifest previos |
| Fuentes originales de CoLight y LibSignal | Auditadas H12.16; no ejecutadas aquí |
| Identidad orden `node_to_index` con LibSignal en runtime | **PENDIENTE** |
| Dependencias `torch_geometric`/`torch_scatter` en Windows | **PENDIENTE** |
| Reproducción y entrenamiento de CoLight | **NO REALIZADOS** |
| Comparación multiagente SOTA | **BLOQUEADA** |
| Conexión Vine/H09 a 12 TLS | **NO IMPLEMENTADA** |

## Alcance científico

Este hito acredita **infraestructura física** si se obtiene `H12_17_MULTI_TLS_SMOKE_OK`; no demuestra robustez, calidad del tráfico, cooperación aprendida o representatividad poblacional de Quito.
