# H11.3b — Dictamen de identificabilidad, NO de calibración Quito

- **H01 desarrollo verificado:** 62,398 transiciones; 4 conductores reales; 5 sesiones autorizadas.
- **Muestras en marcha (>5 km/h):** 43,217.
- Las observaciones por fila no son independientes; la duración sumada de `dt` no equivale a duración total de sesión.
- **Richard, la sesión Alonso de reserva y `furious` sintético no se abrieron.**
- **H11.2 nominal/híbrido:** integridad e invariancia pareada revalidadas con el auditor histórico H11.2c.

## Interpretación epistemológica
POLIDriving proporciona mediciones reales de cinemática de recorridos en Quito, pero no un marco muestral de infractores,
ni headways, TTC, fases semafóricas, probabilidades de incumplimiento o gridlock confirmados.
La variable `design_speed` descrita en el dataset público NO se ha homologado con límites legales por tramo para H01.
Las 1980 etiquetas de riesgo en la descripción pública no se usaron para construir una tasa de infracción.
La presencia del conductor sintético `furious` en el repositorio tampoco lo convierte en evidencia de campo.

## Puertas científicas
- P0-01: la cadena TraCI funciona, pero el contraste H11.3a detectó falta de fidelidad de jerk; validez naturalista no acreditada.
- P0-02: ningún indicador de frenado, parada interna o cola debe etiquetarse como bloqueo causado por imprudencia sin validación.
- Las tasas H09 del 15/30/50 % son niveles de intervención, no prevalencias de infractores de Quito.
- Este informe NO estima prevalencia, NO da calibración, NO demuestra seguridad vial y NO evalúa controladores semafóricos.

## Siguiente evidencia necesaria
1. Registro de campo de cruce ante semáforos con denominadores por oportunidad y fase.
2. Seguimiento longitudinal con distancia al líder y velocidad relativa, estratificado por tipo de vía.
3. Límites legales georreferenciados, tipo de vía, velocidad y hora para contrastar exceso de velocidad.
4. Puente instrumental de aceleración/jerk y evaluación por conductor; sin manipular la referencia para mejorar W1.
5. Congelar escenarios de perturbación naturalista sin bloqueo, separar los de bloqueo artificial y recién entonces evaluar controladores.

## Fuentes bibliográficas
- Marcillo et al. (2024), POLIDriving, Applied Sciences 14(14), 6300. DOI: https://doi.org/10.3390/app14146300
- Repositorio oficial: https://github.com/laboratorioAI/polidriving
- Matriz de observaciones del tutor y del PDF T-ITS (P0-01/P0-02), ya auditada en la revisión.

## Integridad técnica
- SHA H01: `1e66f326e76678c250f12032f7e51b0a79503a9cce8b8cfd6a869f5793240af3`
- SHA acciones: `7dd793f9b5dba3ea3b16ef03cfec08225fd5518f75b3897b19a0b093aff81493`

**Dictamen: H11.3b inventario de evidencia completado; representatividad Quito sigue NO ACREDITADA.**
