# Matriz de puertas — H12.17

| Puerta | H12.17 `plan` | H12.17 `smoke` esperado |
|---|---|---|
| SHA net Hangzhou H12.12 | Verificado | Reconocido nuevamente al finalizar |
| SHA ruta Hangzhou H12.12 | Verificado | Reconocido nuevamente al finalizar |
| H12.12 smoke B1 + manifiesto | Verificado contra fuentes y SHA | Protegido contra edición accidental |
| H12.16 CoLight auténtico | Verificado de informe estático acreditado | Sigue sin ejecutarse |
| 12 TLS y carriles de entrada reales | Contrato XML | Contraste con TraCI |
| Amarillos con `y/Y` y verdes retenidos `G/g` | Asegurado por contrato corregido | Transiciones TraCI registradas |
| Grafo dirigido y orden canónico | Determinista por red | Nodo-acción-observación alineados |
| CoLight LibSignal `torch_scatter`/`torch_geometric` | NO VERIFICADO | NO VERIFICADO |
| Identidad de grafo/nodo con interior de LibSignal | NO VERIFICADO | NO VERIFICADO |
| Checkpoint neuronal CoLight | NO EXISTE ACREDITADO | NO EXISTE ACREDITADO |
| Protocolo Vine/H09 multi-TLS | NO IMPLEMENTADO | NO IMPLEMENTADO |
| Resiliencia comparativa | BLOQUEADA | BLOQUEADA |

**Advertencia:** la matriz `(12,34)` no representa automáticamente la entrada original de CoLight; es el estado homologado de H12.12 replicado por TLS. Cualquier adaptación de observaciones para LibSignal debe documentar conversiones exactas y conservar arquitectura del comparador.
