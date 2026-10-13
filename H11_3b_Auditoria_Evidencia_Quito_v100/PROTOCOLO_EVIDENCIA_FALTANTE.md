# Protocolo mínimo para validar conductas no nominales de Quito (propuesta, NO ejecutado)

## Distinción de estimandos

1. **Magnitud condicional:** distribución de una maniobra dada una condición/contexto (aceleración, jerk, velocidad relativa, frenado).
2. **Frecuencia por oportunidad:** probabilidad de una maniobra/violación entre oportunidades verdaderamente observadas y elegibles (por fase, vía, intensidad, tipo de vehículo).
3. **Prevalencia poblacional:** proporción de conductores/vehículos reales que siguen un perfil. **No se deduce de 15/30/50% de cohortes SUMO**, de las 5 sesiones PoliDriving ni del conductor sintético `furious`.

## Requisitos por conducta

### Cruce en rojo / amarillo
- Enfoque longitudinal de vehículo antes de línea de detención y señalización visible, instante de cambio de fase y tiempo de entrada/salida.
- Numerador rojo: cruces inequívocos en fase roja de oportunidades bien definidas; los ambiguos van a `unknown`.
- Denominador: oportunidades de aproximación relevantes, no cantidad de pasos ni todos los autos de la ciudad.
- Estratos: intersección, carril, hora, densidad/cola, clima, prioridad, amarillo/rojo. Validación interanotador si hay video.

### Seguimiento / TTC
- Líder y seguidor identificados y temporalmente sincronizados; gap métrico, velocidades y velocidades relativas.
- TTC = gap/cierre **solo** si velocidad de cierre positiva y gap positivo; censurar el resto, no marcar como seguro de manera automática.
- Denominador: tiempo observado con líder válido; no número total de registros de velocidad.

### Exceso de velocidad
- Validar límite legal vigente y su segmento espacial (el atributo `design_speed` no basta por sí solo).
- Definir margen, duración, cobertura GPS, vías y velocidad de referencia, separar errores instrumentales.
- Denominador: distancia/tiempo con límite válido y velocidad observable.

### Aceleración/jerk
- Mantener definiciones y unidades para OBD-II/GPS/derivada; auditar cuantización y huecos temporales.
- Reportar por conductor/sesión y banda de velocidad; intervalos de confianza por unidades independientes, no vehículo-pasos tratados como independientes.

### Bloqueo/intersección
- Diferenciar detenerse en cruce, no tener salida libre, accidente y **bloqueo impuesto por simulador**.
- Separar ramas de experimento: nominal; solo Vine; solo H09; híbrido sin bloqueo artificial; bloqueo artificial aislado; combinado solo si se etiqueta explícitamente.
- `setSpeed(id,0)` externo constituye intervención forzada, no se reetiqueta como imprudencia medida.

## Plan de muestreo futuro

Diseñar estratos definidos a priori por tipo de vía, zona, franja horaria, día y condiciones de circulación; calcular tamaños muestrales a partir de variabilidad piloto y precisión deseada, NO inventar tasas de Quito. Minimizar recolección de identificadores personales y documentar licencias/permisos para GPS y vídeo.

## Criterio de progreso

La ausencia de una fuente empírica compatible se registra como `NO_IDENTIFICABLE`, no como cero ni como éxito. Para validar un mecanismo particular se requiere observabilidad, referencia real independiente, métrica bien definida, denominador comparable, error/instrumentación caracterizados y evaluación en escenarios reservados.
