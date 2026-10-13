# H12.10 — Auditoria offline de sensibilidad de politica PPO

**Estado:** H12_10_POLITICA_OFFLINE_OK · Modelo `ppo_ideal` · 300 s · seed 101
**Checkpoint SHA-256:** `9746662b54730664e1262f7f3f9f0f32d106de403141a0731ac00c24f88f701f`

| Indicador | Resultado |
|---|---:|
| Decisiones analizadas | 60 |
| Estados nominal/activo diferentes | 39 |
| Estados cambiados con probabilidades PPO distintas (TV > 1e-7) | 39 |
| Acciones PPO distintas | 0 |
| Fases fisicas diferentes | 0 |
| Maximo cambio en distribucion de 4 acciones (TV) | 0.005501590669 |
| TV medio de estados modificados | 0.001089308506 |
| Maximo cambio en distribucion agrupada de fases (TV) | 0.001248508692 |
| Maximo Jensen–Shannon (nats) | 1.929764103e-05 |
| Entropia media nominal / Vine (nats) | 1.3319419 / 1.3319184 |
| Margen minimo de la mejor accion nominal / Vine | 0.0083611012 / 0.0031434596 |
| Maxima diferencia nominal-probe (TV) | 0 |

## Discordancia de rango en la observacion heredada
- El Box anunciado exige [0,1] en todas las posiciones, pero la componente 32 (edad/120) no se recorta y puede superar 1 a partir de los 120 s sin transicion de fase.
- Estados de ENTRADA fuera del Box por edad no recortada: nominal: 35/60 (max 2.45833), probe: 35/60 (max 2.45833), active: 35/60 (max 2.45833)
- Se analizaron los valores archivados SIN clipping ni renormalizacion. La compatibilidad de entrenamiento del checkpoint no se demuestra con ello.

## Acciones equivalentes
- Mapeo PPO → fase SUMO: 0→0, 1→2, 2→0, 3→2
- Fases fisicas diferentes: 2 (no 4)
- La politica PPO selecciona la maxima probabilidad entre 4 acciones; agrupar probabilidades por fase **no cambia** ese mecanismo.

## Decisiones con mayor cambio de probabilidades
| Decision | t inicio (s) | 34D componentes distintas | TV | JS (nats) | Accion N/V | Prob. accion 0 N/V |
|---:|---:|---:|---:|---:|:---:|---:|
| 39 | 195.0 | 28 | 0.0055015907 | 1.9297641e-05 | 0/0 | 0.333523/0.329187 |
| 37 | 185.0 | 23 | 0.0042890608 | 1.1203156e-05 | 0/0 | 0.332792/0.329751 |
| 36 | 180.0 | 26 | 0.0039501563 | 1.0614928e-05 | 0/0 | 0.333494/0.330052 |
| 38 | 190.0 | 24 | 0.0039208531 | 9.5598458e-06 | 0/0 | 0.33231/0.329439 |
| 40 | 200.0 | 25 | 0.0037347525 | 8.6188359e-06 | 0/0 | 0.333311/0.330646 |
| 43 | 215.0 | 24 | 0.0025915951 | 3.9415155e-06 | 0/0 | 0.333538/0.331321 |
| 26 | 130.0 | 24 | 0.0023314804 | 3.2880523e-06 | 0/0 | 0.331939/0.333925 |
| 34 | 170.0 | 24 | 0.0016241297 | 1.8461198e-06 | 0/0 | 0.332909/0.331285 |
| 31 | 155.0 | 28 | 0.0015501752 | 1.4921083e-06 | 0/0 | 0.332318/0.333389 |
| 42 | 210.0 | 23 | 0.0015084967 | 1.4842802e-06 | 0/0 | 0.333646/0.332138 |

## Interpretacion
- Un cambio de estado con accion identica NO es prueba de insensibilidad de la politica: consultar cambios de probabilidades y margenes.
- Si hay 39 observaciones diferentes pero TV cercano a 0, la red puede ser localmente insensible ante esos estados (diagnostico, no prueba universal).
- Si TV > 0 pero la accion no cambia, existe respuesta probabilistica sin cambio de argmax; la equivalencia de acciones reduce las fases fisicas disponibles.

## Limites
- Una semilla; no demuestra robustez, generalizacion ni calidad del controlador
- Las probabilidades son de la politica heredada, no del algoritmo sobre fases corregidas
- Probabilidades agregadas por fase solo son descriptivas: PPO elige argmax de 4 acciones
- Estado heredado repite carriles, deja outgoing vacio; fases amarillas no homologadas
- No ejecuta SUMO ni verifica semantica de entrenamiento
- ADVERTENCIA: TSCEnv declara Box [0,1]^34 pero devuelve edad_de_fase/120 sin clip en la posicion 32; el reporte conserva esos valores tal como los recibio PPO
