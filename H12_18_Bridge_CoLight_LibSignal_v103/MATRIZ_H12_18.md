# H12.18 v1.0.3 — Matriz de puertas

| Puerta | Estado |
|---|---|
| SUMO H12.17 multi-TLS | `H12_17_MULTI_TLS_SMOKE_OK` validado; re-verificación preflight |
| Código original de CoLight / LibSignal | Commit `127af9f9...` y Git blob `b3385826...` fijados |
| Cargador original AST aislado | Verifica blob comprometido, worktree limpio y SHA-256 local; mantiene corrección CRLF; probado offline |
| Falsos negativos Git CRLF/LF | Corregidos mediante `git show HEAD:agent/colight.py`, sin renunciar a comprobaciones |
| Registro de módulo AST para introspección PyG | **CORREGIDO offline**: `types.ModuleType` registrado en `sys.modules` antes de definir `MessagePassing`; limpieza en fallo; falta validación real Windows |
| Dependencias Windows PyG/Scatter | Importadas correctamente en `colight-pyg` por el usuario |
| Forward neuronal auténtico aleatorio | **NO ACREDITADO** hasta `deps` real OK |
| SUMO shadow | **NO ACREDITADO** hasta `shadow` real OK |
| Agente completo CoLightAgent/Trainer y checkpoint | **NO ACREDITADO** |
| Acciones de CoLight ejecutadas | **NO** (prohibidas en modo sombra) |
| Vine/H09 y resultados de resiliencia | **BLOQUEADOS** |

La clase `ColightNet` que se intenta ejecutar es la versión comprometida de LibSignal sin reescritura. La única sustitución externa sigue siendo `gymnasium.spaces.Discrete` por la interfaz histórica `gym.spaces.Discrete`. No se asegura reproducibilidad integral del algoritmo ni ventaja de rendimiento.
