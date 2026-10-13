# Matriz de identidad algorítmica — H12.15

| Algoritmo | Referencia original verificada | Implementación H12.15 | ¿Misma implementación exacta? | Estado |
|---|---|---|---|---|
| Fixed (RESCO) | `agents/static/fixed.py` — plan de ocho posiciones de `B1.fixed_timings` | Dos verdes físicos y duración objetivo de 42 s del XML, muestreo 5 s | **NO** | Smoke funcional B1 pendiente |
| MaxPressure (RESCO) | `agents/static/maxpressure.py` usa `MaxAgent(WaveAgent)` y estado `mplight` (`Lane.queued` y downstream por dirección) | Par RESCO 0/4 únicamente; `Lane.queued` aproximado con halting actual TraCI | **NO** | Smoke funcional B1 pendiente |
| IPPO | `agents/policy/pfrl_ppo.py`, PFRL | Sin adaptación en H12.15 | — | Bloqueado |
| MPLight | `agents/action_value/mplight.py`, FRAP/DQN con ocho acciones originalmente configuradas | Sin adaptación en H12.15 | — | Bloqueado |
| CoSLight | `agents/policy/CoSLight/coslight.py`, coordinación multiagente | Sin adaptación en H12.15 | — | Bloqueado hasta multi-TLS |

## Afirmación experimental permitida

> Se verificó la geometría física de Hangzhou B1 y se diseñaron dos proyecciones auditables de baselines no neuronales compatibles con el controlador semafórico H12.12. Los resultados de pruebas unitarias no implican entrenamiento ni equivalencia de las implementaciones originales de RESCO. La acreditación funcional requiere ejecutar el smoke SUMO H12.15.

## Afirmaciones prohibidas en esta etapa

- «Los cinco SOTA han sido homologados».
- «Se entrenó MPLight/IPPO/CoSLight».
- «Fixed/MaxPressure H12.15 son ejecuciones originales de RESCO sin adaptaciones».
- «Una diferencia de recompensa en un smoke de semilla 101 demuestra resiliencia».
- «Coop-SARG-B1 demuestra cooperación de red».
