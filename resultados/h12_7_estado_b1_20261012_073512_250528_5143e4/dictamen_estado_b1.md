# H12.7 — Auditoría real del estado 34D de B1

**Estado:** H12_7_DIAGNOSTICO_OK
**Controlador:** `ppo_ideal` · 12 decisiones · 120 microticks
**Comandos activos confirmados:** 20
**Observaciones distintas antes de decisión:** 0/12
**Acciones diferentes:** 0/12
**Primera decisión con observación distinta:** ninguna
**Estados posteriores distintos:** 0/12

## Exposición local en B1 (no global)
- Microticks con vehículos: nominal 94/120 vs activo 94/120
- Microticks con detenidos: nominal 4 vs activo 4
- Máximo de vehículos simultáneos en B1: nominal 6 vs activo 6
- Carriles únicos crudos de B1: 4
- Carriles usados en la observación 12D: 12; únicos 4
- Carriles salientes en TSCEnv: 0 (vacío implica que la 'presión' no resta salientes)
- Fases verdes detectadas: [0, 2]

## Comparación del vector de entrada por decisión
| Decisión | t fin (s) | Acción N/V | Entrada 34D distinta | Salida 34D distinta | Segmentos distintos de entrada |
|---:|---:|:---:|---:|---:|---|
| 0 | 5.0 | 0/0 | 0 | 0 | ninguno |
| 1 | 10.0 | 0/0 | 0 | 0 | ninguno |
| 2 | 15.0 | 0/0 | 0 | 0 | ninguno |
| 3 | 20.0 | 0/0 | 0 | 0 | ninguno |
| 4 | 25.0 | 0/0 | 0 | 0 | ninguno |
| 5 | 30.0 | 0/0 | 0 | 0 | ninguno |
| 6 | 35.0 | 0/0 | 0 | 0 | ninguno |
| 7 | 40.0 | 0/0 | 0 | 0 | ninguno |
| 8 | 45.0 | 0/0 | 0 | 0 | ninguno |
| 9 | 50.0 | 0/0 | 0 | 0 | ninguno |
| 10 | 55.0 | 0/0 | 0 | 0 | ninguno |
| 11 | 60.0 | 0/0 | 0 | 0 | ninguno |

## Interpretación y límites
- Cero diferencias de acciones no implica entradas 34D iguales; leer la columna de observaciones.
- Si B1 no tiene vehículos durante el horizonte, los ceros de cola/recompensa podrían ser reales para esta intersección.
- Si B1 tiene detenidos pero espera/cola permanecen cero, corresponde investigar el mapeo de carriles y las lecturas.
- Para pruebas de resiliencia son necesarios tráfico con exposición efectiva, horizonte suficiente y semillas independientes.
- Los datos observados provienen del piloto y no de una calibración poblacional a Quito.
