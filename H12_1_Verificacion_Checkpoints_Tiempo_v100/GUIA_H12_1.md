# H12.1 — Verificación de checkpoints y sincronización Gymnasium/SUMO

Versión 1.0.0 · solo lectura de archivos existentes · no entrena · no ejecuta SUMO · no invoca `PPO.load` · no deserializa pickle.

## Objetivo

Verificar, con hashes SHA-256, el inventario de los cuatro checkpoints PPO del repositorio; leer de forma segura sus metadatos SB3 (ZIP/JSON, sin deserialización), describir los presupuestos de entrenamiento y auditar estáticamente el contrato de tiempo entre el microtick de SUMO y el periodo RL. Las observaciones y acciones serializadas con pickle permanecen como **no verificadas**; una prueba posterior y aislada de carga real es necesaria antes de usar `predict`.

## PowerShell (desde revision_naturalista)

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h121 = '.\H12_1_Verificacion_Checkpoints_Tiempo_v100'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
python -m unittest discover -s "$h121\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'H12.1 tests fallaron' }
python "$h121\h12_1_verificar.py" --repo-root $repo --revision-root . --microtick-s 0.5 --rl-period-s 5
if ($LASTEXITCODE -ne 0) { throw 'H12.1 preflight fallo' }
python "$h121\h12_1_verificar.py" --repo-root $repo --revision-root . --microtick-s 0.5 --rl-period-s 5 --guardar
if ($LASTEXITCODE -ne 0) { throw 'H12.1 guardar fallo' }
```

Se escribe solo dentro de una nueva carpeta `resultados/h12_1_verificacion_YYYYMMDD_...`:

- `checkpoints_h12_1.csv` — hash SHA-256, metadatos, pasos de entrenamiento, estado seguro de ZIP.
- `contrato_temporal_h12_1.csv` — fórmula temporal suponiendo microtick explícito de 0,5 s.
- `puertas_h12_1.csv` — puertas pendientes antes de comparar controladores.
- `dictamen_h12_1.md` — resumen científico prudente.
- `evidencia_h12_1.json` y `manifiesto_h12_1.json` — registro auditable.

## Precauciones

- `0.5 s` es **hipótesis aportada de los pilotos H11** y debe contrastarse contra el paso real configurado en futuras ejecuciones; este script no lo modifica.
- La observación serializada en SB3 usa pickle/cloudpickle; no se puede verificar `Box(34,)` o `Discrete(4)` mediante mera inspección textual del JSON. Se deja constancia de ello. **No afirmar compatibilidad aún.**
- Con un microtick de 0,5 segundos, un bucle `for _ in range(self.delta_t)` de 5 pasos avanza 2,5 segundos, no 5. Para cinco segundos harían falta 10 microticks *si* la longitud de paso efectiva es 0,5 segundos.
- NO cambiar de manera automática `delta_t` en el código: otros temporizadores del control semafórico pueden depender de esa variable. La validación debe incluir fase amarilla/despeje, tiempo verde mínimo y lógica de las recompensas.
- Los cuatro checkpoints pueden servir para evaluar comportamiento histórico, pero 20.480 vs 1.007.616 pasos de entrenamiento impide una afirmación causal de superioridad de arquitectura.
- No mezclar el gestor histórico `LatamChaosManager` con Vine/H09 para evaluar conducción no nominal sin una ablación separada.
