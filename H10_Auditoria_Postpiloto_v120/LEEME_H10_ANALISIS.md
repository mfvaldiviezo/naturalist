# H10 — Auditoría posterior al piloto v1.2.0

## Propósito

Auditar **en modo solo lectura** las seis condiciones ya terminadas en H10 v1.1.2, semilla 101, sin abrir SUMO, sin repetir Vine, sin modificar modelos ni escenarios.

Combina los tres manifiestos conservados de `resultados/h10_vine_h09_imprudencia_v111_piloto_101` y los tres manifiestos nuevos de `resultados/h10_vine_h09_imprudencia_v112_piloto_101`. Verifica sus hashes de salidas y la comparabilidad de hashes de fuentes. Falla si falta información o si hay modificaciones.

## Instalación

Descomprima `H10_Auditoria_Postpiloto_v120.zip` dentro de `C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

Desde PowerShell en `(tsc-env)`:

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
$h12 = '.\H10_Auditoria_Postpiloto_v120'
python -m unittest discover -s "$h12\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Pruebas del analizador fallidas' }
python "$h12\scripts\auditar_h10_completo.py" --root .
if ($LASTEXITCODE -ne 0) { throw 'Auditoría H10 incompleta' }
```

## Resultados

Se crea la carpeta NUEVA `resultados/h10_auditoria_postpiloto_v120` con:

- `auditoria_h10_101_tabla.csv`: eficiencia, retraso aproximado (`mean_halted`), velocidad, cruces, comandos y elegibilidad por condición.
- `auditoria_h10_101.json`: recuentos por cohortes; ventanas y razones de rechazo de Vine; contrastes factoriales de las dos políticas y rutas de procedencia.

No sobrescribe carpetas ni manifiestos. Si repite la ejecución y la carpeta de análisis ya existe, se detiene; es intencional para mantener trazabilidad. Puede pasar `--output .\resultados\h10_auditoria_postpiloto_v120_segunda` para otro destino nuevo.

## Interpretación y limitaciones

- En el piloto H10, la ruta completa contiene 3600 vehículos, pero H09 selecciona 45 de los 300 programados para salir **antes de 300 segundos**. La cohorte Vine se selecciona por baseline H08 observado y no tiene necesariamente la misma base. La intersección registrada es 7 vehículos.
- `100 comandos` puede reflejar agotamiento de cuota, no equivalencia de oportunidades ni eficacia de las políticas. Se informan vehículos distintos comandados, decisiones y motivos de descarte o cuota.
- `rojos` identifica eventos aproximados de transición de línea de parada clasificados como confirmados por el instrumento, NO infracciones probadas en campo. Los cruces amarillos tampoco son, por sí solos, una violación.
- La distribución de cruces entre `ambas`, `solo_vine`, `solo_h09`, `ninguna` es una clasificación por identidad del vehículo, **no una atribución causal**. Una perturbación a un vehículo puede afectar a otro.
- No se dispone de posiciones/TLS en el CSV Vine de acciones: este análisis **no certifica** que un comando se emitió a menos de X metros de un semáforo. Para responder esa pregunta se necesita añadir telemetría espacial en un ensayo posterior.
- Sólo una semilla; no extraer significancia estadística. No incluye controladores RL. No equivale a calibrar Quito.
