# H12.19 — Matriz de evidencia del piloto TD CoLight

| Gate | Evidencia | Estado antes del piloto real |
|---|---|---|
| H12.17 infraestructura multi-TLS | `H12_17_MULTI_TLS_SMOKE_OK` 12×34, dos fases, 32 aristas | **PASSED** |
| H12.16 fuentes | Original y LibSignal fijados por Git | **PASSED** |
| H12.18 inferencia sombra | `H12_18_COLIGHT_SHADOW_FORWARD_OK`, 12 nodos × 12 decisiones | **PASSED** |
| H12.19 tests offline | 60 tests Python; integraciones con interfaces simuladas | **PASSED EN ENTORNO DE DESARROLLO; WINDOWS PENDIENTE** |
| H12.19 preflight usuario | `plan` sobre resultados reales con SHA | **NOT_RUN** |
| H12.19 backprop ColightNet real | `probe` CPU con PyG/Scatter | **NOT_RUN** |
| H12.19 transiciones SUMO | `pilot`: 24 decisiones, 240 microticks | **NOT_RUN** |
| H12.19 checkpoint experimental | `pilot`: MSE TD RMSprop, pesos nuevos, SHA | **NOT_RUN** |
| Actuación real de CoLight | No se habilita en H12.19 | **BLOCKED BY DESIGN** |
| CoLightAgent/Trainer completo LibSignal | No importado; requiere homologación propia | **NOT_IMPLEMENTED** |
| Entrenamiento SOTA multisemilla y comparación válida | No acreditado | **BLOCKED** |
| Vine/H09 y resiliencia | No conectado al contrato H12.17–H12.19 | **BLOCKED** |

**Precisión metodológica:** distinguir arquitectura neuronal original de **algoritmo integral**. La clase `ColightNet` que se usa en H12.19 procede de LibSignal sin modificar; el ciclo TD y la política de recolección son un protocolo experimental de prueba, no el proceso de entrenamiento original LibSignal. El piloto solo acredita capacidad de optimización numérica, archivo reproducible y control físico conservado; no acredita calidad de decisiones, ni transferencia ni resistencia ante conducción no nominal.
