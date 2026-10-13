# H11.3c — Identificación de episodios cinemáticos intensos en POLIDriving

Esta auditoría responde una pregunta **limitada y reproducible**: ¿las sesiones reales de desarrollo de POLIDriving contienen eventos sostenidos con aceleración, frenado o jerk de magnitud elevada? **No demuestra intención imprudente, infracción de velocidad, responsabilidad individual, peligrosidad objetiva ni prevalencia poblacional.**

## Protecciones

- Solo lee `resultados/ntvc_vine_r_01_cohortes_movimiento_regenerado/cohortes_muestras_verificadas.csv` y su `manifest.json` + otros tres archivos SOLO para SHA; alternativa H01 original si regenerado ausente.
- Verifica SHA-256 de cuatro fuentes H01, SHA de origen congelado `EBBB8BEB...669162C25`, 5 sesiones autorizadas y 62.398 filas. No accede al material RAW, Richard, Alonso reservado o `furious`.
- No entrena Vine, no usa SUMO, no modifica modelos anteriores. Resultados solo en **carpeta nueva** `resultados/h11_3c_cinematica_*`.
- Clasificación exclusiva a nivel de *episodio de maniobra*, no perfil moral/psicológico del conductor.

## Comandos PowerShell (copiar completos)

Extraiga `H11_3c_Episodios_Cinematica_PoliDriving_v100.zip` en `C:\Proyecto_Tesis_Final_V1\revision_naturalista`, sin renombrar su subcarpeta.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h11c = ".\H11_3c_Episodios_Cinematica_PoliDriving_v100"

python -m unittest discover -s "$h11c\tests" -v
if ($LASTEXITCODE -ne 0) { throw "Tests H11.3c fallidos" }

# Revalidacion H01 y analisis en memoria (NO escribe)
python "$h11c\h11_3c_episodios.py" --root .
if ($LASTEXITCODE -ne 0) { throw "Preflight H11.3c fallido" }

# Crea carpeta nueva de resultados (NO modifica fuentes)
python "$h11c\h11_3c_episodios.py" --root . --guardar
if ($LASTEXITCODE -ne 0) { throw "Ejecucion H11.3c fallida" }
```

## Archivos nuevos

- `resumen_por_sesion_h11_3c.csv`: exposición en segundos a marcha >5 km/h, fracciones de muestras y exposición por maniobra y sesión.
- `resumen_por_umbral_h11_3c.csv`: números de muestras/episodios y tiempo marcado por tipo de maniobra.
- `episodios_candidatos_h11_3c.csv`: episodios continuos por conductor, sesión y segmento, con fila inicial/final, duración, velocidad y pico de aceleración/jerk. **Sin GPS ni identidades sensibles adicionales**.
- `dictamen_h11_3c.md`: lectura científica explícitamente no causal.
- `manifiesto_h11_3c.json`: SHA de fuentes y productos.

## Umbrales: tres escenarios de sensibilidad; NO estándares legales

- Sensible: |aceleración| >= 1.5 m/s²; |jerk| >= 2.0 m/s³.
- Intermedio: |aceleración| >= 2.0 m/s²; |jerk| >= 3.0 m/s³.
- Conservador: |aceleración| >= 3.0 m/s²; |jerk| >= 5.0 m/s³.

Estos umbrales se usan **solo** para determinar si la conclusión descriptiva cambia al modificar el criterio. No afirmar que 2 m/s² es el umbral de imprudencia de Quito. El reconocimiento de jerk requiere actual y previa velocidad >5 km/h dentro del mismo segmento. Las paradas reales no se confunden con aceleración cero.

## Criterios de interpretación

Si aparecen episodios en uno o varios criterios, es legítimo decir "POLIDriving contiene maniobras cinemáticas intensas". Todavía NO se puede afirmar "son 20% imprudentes" o "esto es tráfico imprudente real": se necesita contexto/etiqueta independiente (video, descripción de maniobra, límites legales, tránsito, semáforos, proximidad).

**Precaución estadística:** muestras temporales autocorrelacionadas, solo cuatro conductores, diferentes dt medianos; comparar *descriptivamente por sesión*, no publicar p-valores o IC por fila como si fueran individuos.

**Para el artículo:** usar `non-nominal longitudinal driving dynamics informed by naturalistic observations from Quito` en vez de `empirically validated reckless driving in Quito` hasta disponer de anotaciones independientes.
