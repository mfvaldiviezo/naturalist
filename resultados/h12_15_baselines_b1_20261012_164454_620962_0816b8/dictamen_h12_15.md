# H12.15 — Baselines físicos auditados en B1

**Estado:** `H12_15_PHYSICAL_SMOKE_OK` — smoke técnico, **NO reproducción integral de RESCO ni comparación SOTA certificada**.

## Brecha estructural RESCO -> B1

- RESCO Hangzhou tiene **8 pares de fase** y FIXED registra 8 duraciones.
- El `net.xml` validado en H12.12 contiene **2 verdes físicos** (0 y 2) y dos amarillos de 3 s.
- Solo proyectamos los pares RESCO 0 (S-S/N-N) y 4 (W-W/E-E), verificados contra los enlaces SUMO de B1.
- Los otros seis pares RESCO no corresponden a seis verdes físicos independientes. No se inventaron fases nuevas.
- Fixed-B1 usa duración objetivo de 42 s según net.xml; no se llama Fixed RESCO 8 fases.
- MaxPressure-B1 conserva la suma de presión por par, pero reemplaza el estado persistente `Lane.queued` RESCO por detenciones instantáneas TraCI.

## Ejecución SUMO (misma semilla/red/rutas)

| Indicador | Fixed-B1 físico | MaxPressure-B1 proyectado |
|---|---:|---:|
| Decisiones | 24 | 24 |
| Microticks | 240 | 240 |
| Entrada en amarillos | 2 | 5 |
| Colisiones | 0 | 0 |
| Recompensa acumulada | -3.130650 | -0.886000 |
| Cola media (B1) | 0.833333 | 0.208333 |
| Espera total media por decisión (s) | 10.666667 | 0.666667 |

## Limitaciones

- No hay evidencia de entrenamientos IPPO/MPLight/CoSLight.
- No se atribuye la mejora/empeoramiento de tráfico a resiliencia: es un smoke de una semilla.
- Este H12.15 NO demuestra ejecución directa de clases RESCO Fixed/MaxPressure; son proyecciones documentadas.
- Los controladores solo actúan en B1; el resto de los semáforos conserva la lógica de SUMO.
- Vine/H09 siguen fuera del contrato nuevo y requieren puente protegido posterior.
- H12.13 piloto funcional de PPO puede ejecutarse independientemente; no es una prueba SOTA.
