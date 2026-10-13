# H12.16 — CoLight auténtico: código original versus LibSignal

**Estado:** `H12_16_COLIGHT_SOURCE_AUDIT_OK` — Auditoría **estática de código y trazabilidad**, NO ejecución del algoritmo ni certificación SOTA.

## Fuentes congeladas

| Código | Commit fijado | Uso previsto |
|---|---|---|
| CoLight original (wingsweihua/colight) | `04440b722e7f36d7043a3f2ad8e40c3df301fad3` | Referencia de arquitectura TensorFlow/Keras |
| LibSignal (DaRL-LibSignal/LibSignal) | `127af9f93902778e556de2eedb2b606c4c9447e6` | Candidato de integración PyTorch + SUMO |

Los archivos de ambos repositorios fueron cotejados mediante SHA-1 de blobs Git y SHA-256 del contenido comprometido; no se ejecutaron.

## Hallazgos de implementación

- Agente original: TensorFlow 1.11 / Keras 2.1 (fuente histórica, no ejecutada).
- Agente LibSignal registrado: `agent/colight.py::CoLightAgent`; PyTorch / torch_geometric / torch_scatter (fuente auditada, no importada).
- Variante alternativa no registrada: `agent/colight_pytorch_agent.py no registrado en agent/__init__.py`.
- Atención entre intersecciones y adyacencia dispersa: **presentes en fuente**; identidad del orden de nodos **sin validar en runtime**.
- **Advertencia de orden:** llamadas `sorted(...)` cuyo resultado no se usa (líneas del agente LibSignal: `[54, 65, 77, 89, 100, 143, 154, 165, 177, 189]`). Debe evaluarse el riesgo de desalineación índice-grafo, sin modificar el algoritmo original a ciegas.
- Configuración SUMO de ejemplo LibSignal: `cologne1`; **NO es Hangzhou**.
- Dependencias PyTorch Geometric y `torch_scatter`: declaradas/importadas por la fuente; compatibilidad de ruedas Windows no certificada.

## Condiciones físicas Hangzhou

- La red local (SHA-256 validado) posee **12 semáforos** con conexiones; B1 verdes `[0, 2]`, amarillos `[1, 3]`.
- Primeros semáforos: A1:[0, 1, 2, 3]; A2:[0, 1, 2, 3]; B0:[0, 1, 2, 3]; B1:[0, 2]; B2:[0, 2]; B3:[0, 1, 2, 3]; C0:[0, 1, 2, 3]; C1:[0, 2]; C2:[0, 2]; C3:[0, 1, 2, 3]; D1:[0, 1, 2, 3]; D2:[0, 1, 2, 3].
- H12.14: `H12_14_SOTA_AUDIT_OK`. H12.15: `H12_15_PHYSICAL_SMOKE_OK`.
- Red y rutas iguales a H12.12. Eso NO acredita el grafo de vecindad ni igualdad de semántica de acciones/amarillos.

## Puertas de homologación

| Gate | Estado |
|---|---|
| `upstream_orig_authenticity` | **PASSED_PINNED_COMMIT_AND_BLOBS** |
| `upstream_libsignal_authenticity` | **PASSED_PINNED_COMMIT_AND_BLOBS** |
| `colight_network_attention` | **PRESENT_STATICALLY** |
| `registered_colight_pytorch` | **PRESENT_STATICALLY** |
| `libsignal_sumo_support` | **PRESENT_STATICALLY** |
| `h1212_hangzhou_network_and_demand` | **PASSED_IDENTITY** |
| `node_order_graph_runtime` | **NOT_VERIFIED** |
| `yellow_transition_equivalence` | **NOT_VERIFIED** |
| `phase_action_masking_network` | **NOT_VERIFIED** |
| `libs_binary_compatibility` | **NOT_VERIFIED** |
| `multi_tls_h1212_adapter` | **NOT_IMPLEMENTED** |
| `colight_training_checkpoint` | **NOT_ACCREDITED** |
| `training_equal_budget` | **NOT_ACCREDITED** |
| `Vine_H09_injection_multi_TLS` | **NOT_IMPLEMENTED** |
| `sota_resilience` | **BLOCKED** |

## Decisión

**CoLight queda incorporado formalmente como comparador multiagente**, preferentemente a través de LibSignal. El siguiente paso NO es iniciar entrenamiento comparativo: primero construir adaptador multi-TLS que conserve la atención basada en adyacencia y ejecutar pilotos de control real SUMO con observaciones, fases y transiciones trazables. CoSLight sigue siendo un SOTA distinto.

## Limitaciones

- No se importó CoLight ni se ejecutaron SUMO, PyTorch, CityFlow o entrenamientos.
- `torch_scatter`/`torch_geometric` detectados o ausentes por `find_spec` no implican compatibilidad binaria.
- El agente PyTorch no es identidad de parámetros frente al CoLight TensorFlow de los autores.
- No hay checkpoint de CoLight verificado, ni robustez, transferencia o representatividad de Quito.
- H12.16 no altera H12.12–H12.15 ni los PPO históricos.
