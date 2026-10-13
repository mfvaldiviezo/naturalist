# Matriz de decisión H12.14 — catálogo y homologación

| Agente real | Código / algoritmo | Nivel viable | Brecha de H12.12 | Próxima verificación |
|---|---|---|---|---|
| FIXED | RESCO `static.fixed` | B1 | Calendario/ciclo real, amarillo y verde mínimo | Adaptador determinista y smoke SUMO |
| MAXPRESSURE | RESCO `static.maxpressure` + `maxwave.WaveAgent` | B1 | Significado exacto de presión y `phase_pairs` | Auditar `state_builder` y estado `mplight`; adaptar equivalencia física |
| IPPO | RESCO `policy.pfrl_ppo` + PFRL PPO | B1 / red con agentes independientes | `drq` RESCO ≠ 34D H12.12; acciones y reward | Adaptador documentado y entrenamiento nuevo |
| MPLight | RESCO `action_value.mplight` FRAP/DQN | B1 / red compartida | Requiere `phase_pairs`, `directions`, competencia de fases y estado especial | Conservar FRAP, nuevo entrenamiento y pruebas |
| CoSLight | RESCO `policy.CoSLight.coslight`, MAPPO cooperativo | Solo red multi-TLS | `SharedAgent`, buffers compartidos y dimensiones por agente | Entorno multiagente con 16 TLS y evaluación de cooperación |

**Separación científica:** código localizado ≠ entorno homologado ≠ checkpoint entrenado ≠ rendimiento medido. Esto evita repetir el etiquetado erróneo de CoLight como heurística.

**Con H12.12 verificado y H12.13 piloto todavía por ejecutar**, el orden recomendado es auditar los SOTA ahora, ejecutar piloto H12.13, construir adaptadores locales y solo después ampliar presupuesto de entrenamiento. La extensión multi-TLS tiene protocolo separado y no se sustituye por una evaluación B1.
