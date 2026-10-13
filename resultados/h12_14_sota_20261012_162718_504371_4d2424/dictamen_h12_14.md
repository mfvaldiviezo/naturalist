# H12.14 — Auditoría de compatibilidad SOTA RESCO con H12.12

**Estado:** `H12_14_SOTA_AUDIT_OK` — Código y metadatos auditados, **NO controladores entrenados ni certificados**.

## Evidencia de contrato físico

- H12.12 acreditado: `H12_12_B1_GREEN2_OBS34_V100` · fases verdes [0, 2] · 4 carriles de entrada reales.
- Red RESCO Hangzhou igual byte a byte: **True**.
- Ruta RESCO Hangzhou igual byte a byte: **True**.
- Piloto H12.13: **NOT_RUN_OR_NOT_SUPPLIED**.

## Matriz de implementaciones y brechas

| Controlador | Fuente y registro YAML | Estado RESCO | Reward RESCO | Ámbito | Listo H12.12 |
|---|---|---|---|---|---|
| FIXED | Verificados | `wave` | `wait` | `local_baseline` | **NO** |
| MAXPRESSURE | Verificados | `mplight` | `wait` | `local_baseline` | **NO** |
| IPPO | Verificados | `drq` | `wait` | `local_rl` | **NO** |
| MPLight | Verificados | `mplight` | `pressure` | `shared_rl` | **NO** |
| CoSLight | Verificados | `coslight` | `coslight` | `multiagent_rl` | **NO** |

## Puertas de homologación

- `source_code_and_yaml`: **PASSED**
- `h1212_physical_contract`: **PASSED**
- `resco_hangzhou_network_identity`: **PASSED**
- `resco_hangzhou_routes_identity`: **PASSED**
- `B1_SOTA_state_adapter`: **NOT_IMPLEMENTED**
- `B1_SOTA_action_adapter`: **NOT_IMPLEMENTED**
- `B1_SOTA_transition_adapter`: **NOT_IMPLEMENTED**
- `SOTA_model_training`: **NOT_ACCREDITED**
- `CoSLight_multi_TLS_environment`: **NOT_IMPLEMENTED**
- `Vine_H09_injection_in_new_contract`: **NOT_IMPLEMENTED**
- `SOTA_full_comparison`: **BLOCKED**

## Por qué no son todavía controladores comparables

- IPPO RESCO emplea PFRL y entrada `drq`; H12.12 entrega observaciones 34D. Mantener arquitectura/recompensa documentadas o registrar adaptación.
- MPLight RESCO es FRAP/DQN y usa pares de fases/direcciones; no es un PPO ni puede reemplazarse por una MLP y llamarse MPLight.
- El `MAXPRESSURE` de RESCO delega en `WaveAgent` después de descartar el primer dato; su equivalencia con presión física requiere inspección de `state_builder` y la definición de presiones.
- CoSLight usa `SharedAgent`, `num_agents` y políticas multiagente: un B1 aislado no prueba cooperación de red.
- FIXED no necesita aprendizaje, pero debe fijarse explícitamente su calendario físico y transición de amarillos.
- El experimento H12.13 piloto de 64 transiciones es opcional para esta auditoría y **no** certifica aprendizaje.

## Protocolo propuesto (no ejecutado)

**Nivel A (B1):** Fixed, MaxPressure, IPPO, MPLight y H-SARG-B1/Coop-SARG-B1 bajo el mismo dominio semafórico. Se deben registrar las diferencias de arquitectura y entradas de los SOTA: no se presupone igualdad de representación interna.

**Nivel B (red multi-TLS):** CoSLight auténtico junto con comparadores multiagente; necesidad de control simultáneo y métrica de red. No afirmar cooperación de Coop-SARG-B1 hasta desarrollar versión multiagente.

**Condición previa a resultados de resiliencia:** adaptación y pruebas integradas reales SUMO, checkpoints nuevos certificados, presupuestos y semillas emparejadas, verificación de inyección Vine/H09 en el entorno nuevo.

## Límites

- Los códigos RESCO NO se han importado ni ejecutado
- RESCO puede requerir dependencias/API históricas PFRL y cambios de adaptador
- No existe equivalencia automática entre estados RESCO (drq, mplight, coslight) y H12.12 34D
- No se han certificado modelos entrenados ni métricas de resiliencia
- Una red igual byte a byte NO implica igual demand protocol, amarillo, decisiones, reward o entrenamiento

**Dictamen final:** H12.14 demuestra disponibilidad de fuentes, describe brechas y define gates. No acredita que ningún SOTA esté funcionando con H12.12 ni habilita entrenamiento comparativo todavía.
