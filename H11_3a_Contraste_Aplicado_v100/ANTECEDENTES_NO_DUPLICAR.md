# Inventario de antecedentes: no repetir estos análisis

| Material | Evidencia existente | ¿Debe repetirse en H11.3a? |
|---|---|---|
| `process_polidriving_verified.py` | Siete sesiones originales; extracción de aceleración y jerk, intervalo válido, QC, sin interpolar | NO |
| `validar_polidriving_sesiones.py` | Seis folds por sesión, independencia / gaussiana / remuestreo empírico pareado; W1, KS, Kendall, ceros; no Vine | NO |
| `validar_polidriving_conductores.py` | Cuatro folds Leave-One-Driver-Out, mismo conjunto de referencias; Richard excluido | NO |
| `validar_coherencia_temporal.py` | Ventanas de desarrollo no superpuestas, consistencia jerk, ACF lag1, ceros y tiempos; no Vine generativo temporal | NO |
| `preparar_transiciones_temporales.py` | Triple temporal `t-2,t-1,t`, segmentos válidos; Richard excluido; datos para ajuste posterior | NO |
| NTVC-Vine-R S01/S02/H01/H02 | Vine Gaussian/Student, validación condicional, muestras de marcha y ceros; usos de reserva definidos | NO |
| NTVC H03/H04/H05 | Integración cinemática y contraste multi-semilla **shadow**, SIN comandos aplicados | NO |
| H06/H08b/H09/H10 | Actuación Vine, perfiles H09 y seguridad; auditoría de comandos, no fidelidad PoliDriving post-SUMO | NO |
| H11.2/H11.2c | Trayectorias 0.5 s observadas, invariancia, tasas de velocidad, seguimiento, jerk y frenado en SUMO | NO |
| **H11.3a presente** | Enlace controlado entre distribución H01 **de desarrollo** y aceleración/jerk realmente observados en SUMO, separando instantes comandados Vine y agrupaciones H09 | **SÍ, faltaba** |

## Diferencia entre congelados

El CSV preliminar de siete sesiones tiene SHA-256 `2E20FE002F360A3319B935ACBB62C6BF6BAEBA16DF3A74B021CE833C7DB9299D` y contiene la reserva final. El conjunto posterior H01 (con velocidad y 5 sesiones de desarrollo) procede de un verificado distinto con SHA-256 `EBBB8BEBE69DBBB55858FCB8F8753A7F33AAAD5CA78B57D4BBA9FEE669162C25`.

**No interpretar automáticamente la diferencia de hashes como corrupción**: corresponden a diferentes artefactos. H11.3a exige explícitamente el segundo, trazado por el manifiesto H01.

**Riesgo metodológico adicional:** la sesión Alonso 20231229_151643 participó en alguna exploración antigua; no tratarla como test completamente virgen. Richard debe conservarse reservado hasta un plan confirmatorio congelado.
