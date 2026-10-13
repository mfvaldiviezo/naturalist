# H12.11 — Procedencia y compatibilidad del PPO heredado

**Estado:** H12_11_PROVENIENCIA_DIAGNOSTICADA (**diagnostico, NO certificacion de entrenamiento**).

## Respuesta de ppo_ideal ante Vine — H12.10
- Estados 34D modificados: 39/60; distribuciones modificadas: 39/39; acciones distintas: 0/60.
- TV maxima 0.005501591; TV media en estados modificados 0.001089309.
- Entropia nominal media 1.331942 nats = 96.08% del maximo ln(4). NO equivale a un criterio de calidad.

## Metadatos de los ZIP SB3 (solo lectura, sin deserializar)
| Archivo | Disponible | SHA-256 prefijo | num_timesteps archivado | n_envs archivado |
|---|:---:|---|---:|---:|
| `ppo_ideal` | si | `9746662b54730664` | 20480 | 1 |
| `ppo_chaos` | si | `b213029728b7a718` | 20480 | 1 |
| `ppo_coop_ideal` | si | `ecb9039caad7d9fb` | 1007616 | 4 |
| `ppo_coop_chaos` | si | `e4e1f710e1152b02` | 1007616 | 4 |

- El contador `num_timesteps` describe un campo del checkpoint; por si solo no certifica dataset, tiempos ni esquema de entrenamiento.
- Ratio Coop-ideal / ideal de contadores archivados: 49.20x.

## Contrato ACTUAL del TSCEnv (no probatorio de entrenamiento antiguo)
- `state_shape_34_present`: True
- `state_age_first_unclipped`: True
- `outgoing_empty_placeholder`: True
- `controlled_lane_padding_last`: True
- `action_maps_modulo_phases`: True
- `direct_traci_setPhase`: True
- `sumo_train_step_length_1s`: True
- `age_box_normalization_warning`: True

## Script train.py del repositorio local (indicadores estaticos)
- `training_program_constructs_TSCEnv`: True
- `training_uses_random_xml_flag`: True
- `training_route_selection_sorted`: True
- `training_does_not_pass_reward_weights`: True
- `training_can_enable_legacy_chaos`: True
- `training_cli_supports_extractor`: True
- `training_script_has_configurable_total_timesteps`: True

## No acreditado
- ZIP SB3 no contiene obligatoriamente ruta de demanda usada para entrenar ni SHA de archivo .rou.xml
- ZIP SB3 no certifica por si solo commit de TSCEnv, semantica de fases o protocolos de interverde
- flags de train.py corresponden a CODIGO PRESENTE, no a prueba de ejecucion historica
- checkpoint de clases chaos no equivale a entrenado con Vine/H09
- cualquier brecha de timesteps observados impide comparacion de entrenamiento igualado
- no se acreditan sensibilidad poblacional, robustez ni transferencia Quito

**Decisión metodológica:** preservar checkpoints y resultados originales; reconstruir manifiestos de entrenamiento con red/ruta SHA, semantica 34D, numero de fases, version SUMO, seeds, recompensas y presupuestos antes de una comparacion SOTA definitiva.
