# H12.9 — Exposición de Vine ante PPO, 300 segundos

**Estado:** H12_9_EXTENDED_OK · **Modelo:** `ppo_ideal` · seed 101
**Nominal y probe idénticos:** sí. **Comandos Vine confirmados:** 100
**Cambio cinemático global:** sí.

| Indicador | Nominal | Probe | Vine activo |
|---|---:|---:|---:|
| Microticks B1 con vehículos | 574 | 574 | 574 |
| Microticks B1 con detenidos | 316 | 316 | 348 |
| Microticks B1 con espera | 305 | 305 | 340 |
| Vehículo-microticks en B1 | 8469 | 8469 | 9292 |
| Microticks con cohorte Vine presente en B1 | 475 | 475 | 483 |
| Vehículos Vine distintos presentes en B1 | 13 | 13 | 12 |
| Decisiones con cola local no nula | 34 | 34 | 37 |
| Decisiones con espera local no nula | 34 | 34 | 37 |
| Decisiones con recompensa no nula | 34 | 34 | 37 |
| Comandos aplicados | 0 | 0 | 100 |
| Velocidad media temporal local B1 (m/s) | 10.736058360400692 | 10.736058360400692 | 10.041614209295703 |

## Sensibilidad de estado/acción
- Microticks con diferencias en agregados B1: 389 de 600
- Primer cambio agregado B1: 77.0
- Microticks con velocidad media B1 diferente: 453
- Registros velocidad individual Vine en B1 diferentes: 735
- Primer cambio de velocidad B1: 61.5
- Decisiones con entrada 34D diferente: 39 de 60
- Primera diferencia 34D: 90.0
- Segmentos de observación afectados: {'presion_4': 38, 'espera_12': 36, 'cola_12': 31}
- Decisiones semafóricas diferentes: 0 de 60
- Frecuencia acciones nominal: {'0': 60}
- Frecuencia acciones activo: {'0': 60}

## Contrato heredado que NO se ha corregido
- Fases verdes: [0, 2]
- Carriles únicos B1: 4; 12 posiciones del estado original
- Carriles salientes: 0 (estado heredado)

## Límites
- 300 s/semilla única, NO inferencia estadística de resiliencia
- Estado 34D y mapa de acciones heredados; no corregir sin reentrenar
- No se homologa aquí el tiempo amarillo ni SOTA multiagente
- No demuestra representatividad poblacional de Quito
