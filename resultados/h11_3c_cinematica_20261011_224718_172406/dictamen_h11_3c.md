# H11.3c — Caracterización de maniobras cinemáticas en POLIDriving (desarrollo)

**Dictamen:** eventos cinemáticos intensos candidatos; NO etiquetas de imprudencia ni infracciones.
No se utilizaron las etiquetas expertas de riesgo, datos sintéticos, Richard ni la sesión reservada de Alonso.

## Sensibilidad exploratoria — umbrales simétricos NO normativos
| Escenario | Evento | muestras | episodios | Σdt de muestras marcadas (s) |
|---|---|---:|---:|---:|
| exploratorio_sensible | aceleracion_intensa | 366 | 142 | 126.45 |
| exploratorio_sensible | frenada_intensa | 639 | 177 | 256.41 |
| exploratorio_sensible | jerk_intenso_pos | 61 | 60 | 16.93 |
| exploratorio_sensible | jerk_intenso_neg | 137 | 126 | 38.61 |
| exploratorio_sensible | cualquier_maniobra_intensa | 1152 | 423 | 424.25 |
| exploratorio_intermedio | aceleracion_intensa | 48 | 23 | 14.56 |
| exploratorio_intermedio | frenada_intensa | 164 | 51 | 64.43 |
| exploratorio_intermedio | jerk_intenso_pos | 7 | 7 | 1.89 |
| exploratorio_intermedio | jerk_intenso_neg | 10 | 10 | 2.65 |
| exploratorio_intermedio | cualquier_maniobra_intensa | 226 | 84 | 82.72 |
| exploratorio_conservador | aceleracion_intensa | 0 | 0 | 0.00 |
| exploratorio_conservador | frenada_intensa | 14 | 5 | 5.44 |
| exploratorio_conservador | jerk_intenso_pos | 0 | 0 | 0.00 |
| exploratorio_conservador | jerk_intenso_neg | 0 | 0 | 0.00 |
| exploratorio_conservador | cualquier_maniobra_intensa | 14 | 5 | 5.44 |

## Interpretación obligatoria
- `SIN BANDERA` significa sin cruce de los umbrales analizados, NO conducción nominal verificada.
- `CON BANDERA` significa cinemática intensa observada, NO prueba de imprudencia ni responsabilidad del conductor.
- Se excluye v<=5 km/h por comparabilidad con H01; para flag de jerk se exige además velocidad anterior >5 km/h dentro del mismo segmento.
- El jerk se deriva de aceleración con dt irregular: considerar ruido y cuantización de instrumentos.
- Umbrales 1.5/2/3 m/s² y 2/3/5 m/s³ son una grilla de SENSIBILIDAD, NO umbrales legales, naturales ni validados.
- Las tasas de muestras/episodios describen SOLAMENTE las cinco sesiones de desarrollo; episodios no independientes.
- La duración es suma de intervalos de muestra elegibles y NO necesariamente tiempo cronológico completo del trayecto.
- Eventos por racha solo fusionan dentro del mismo segment_id; no se unen segmentos ni sesiones.
- Aceleración intensa también puede ser necesaria o segura; posible falta de contexto humano/geométrico.
- Sin labels independientes de imprudencia no se pueden reportar precision, recall o accuracy.
- No convertir el 15/30/50% de H09 en prevalencia de conductores de Quito.

## Pregunta respondida
**¿Existen maniobras cinemáticamente intensas?** Ver conteos calculados. **¿Demuestran conducción imprudente?** No por sí solas.

## Decisión para siguiente fase
Si hay episodios: muestrear episodios para revisión ciega con vídeo/contexto independiente (si legalmente accesible);
si no existe el material, presentar resultados como conducción no nominal cinemática, no como imprudencia comprobada.
No reentrenar Vine ni alterar SUMO en este hito.
