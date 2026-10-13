# H12.6 — Auditoría offline PPO ideal, nominal/probe/Vine activo

**Estado:** H12_6_AUDITORIA_OK. **Seed:** 101. **Horizonte:** 60 s, 120 microticks y 12 decisiones PPO.

**Vine:** 20 comandos, 20 confirmados, 6 vehículos intervenidos.
**Error máximo de aceleración:** 1.776e-15 m/s².
**Primera diferencia cinemática:** microtick 8, t=4.5 s.
**Diferencias de decisiones semafóricas:** 0 de 12, índices [].

| Indicador | Nominal | Probe | Vine activo | Activo − nominal |
|---|---:|---:|---:|---:|
| Velocidad media temporal (km/h) | 37.709347 | 37.709347 | 37.535052 | -0.174295 |
| Velocidad ponderada por vehículos activos (km/h) | 41.486231 | 41.486231 | 41.395180 | -0.091051 |
| Vehículos activos promedio | 30.316667 | 30.316667 | 30.316667 | 0.000000 |
| Vehículo-segundos detenidos | 57.500000 | 57.500000 | 57.500000 | 0.000000 |
| Detenidos promedio | 0.958333 | 0.958333 | 0.958333 | 0.000000 |
| Salidas durante el piloto | 60 | 60 | 60 | 0 |
| Llegadas durante el piloto | 1 | 1 | 1 | 0 |
| Colisiones reportadas | 0 | 0 | 0 | 0 |
| Inicios de teleport | 0 | 0 | 0 | 0 |
| Cola proxy TSCEnv (media por decisión) | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| Demora proxy TSCEnv (media por decisión) | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| Gini TSCEnv (media por decisión) | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| Recompensa acumulada PPO | 0.000000 | 0.000000 | 0.000000 | 0.000000 |

## Advertencias metodológicas
- Una semilla/episodio corto, sin inferencia estadística ni evidencia de resiliencia
- Métricas SUMO agregadas globales; PPO controla B1 solamente
- Queue/delay son indicadores internos TSCEnv, no demora individual medida por tripinfo
- Promedios de velocidad representan medias temporales o ponderación por vehículos presentes, no viajes completados
- Los comandos Vine usan un límite de 20 por ventana de 60 s
- Comparación válida solo con idénticos checkpoint, red, rutas, fuentes y horizonte
- No se han homologado tiempos amarillos/interverdes ni protocolos multiagente SOTA
- No se ha calibrado estadísticamente el traslado temporal POLIDriving-SUMO

El informe NO permite afirmar que PPO mejoró o empeoró causalmente, ni que las perturbaciones sean representativas del tráfico de Quito.
