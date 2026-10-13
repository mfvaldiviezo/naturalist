# H11.3a — Contraste por bandas de velocidad y auditoría integral de 100 órdenes

**Estado**: herramienta de análisis descriptivo, sin reentrenamiento, SIN nueva corrida SUMO.

## Alcance y origen

Se reutilizan los verificadores de `H11_3a_Contraste_Aplicado_v100` y la referencia
H01 `ntvc_vine_r_01_cohortes_movimiento_regenerado`. No se leen archivos RAW,
Richard, ni la sesión Alonso excluida. La integridad H01 y de los dos brazos
pareados H11.2 se valida antes de leer para análisis. Los fuentes originales
son estrictamente de solo lectura; la salida es nueva bajo `resultados/`.

## Ejecución desde PowerShell

Descomprimir `H11_3a_Bandas_Velocidad_v100.zip` junto a
`H11_3a_Contraste_Aplicado_v100` dentro de
`C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h11aBands = '.\H11_3a_Bandas_Velocidad_v100'
$nom = '.\resultados\h11_2_pareado_h10_nominal_20261011_184549_504694\observado\telemetria'
$hib = '.\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\telemetria'
$act = '.\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\hibrido_contextual\acciones_hito08.csv'

python -m unittest discover -s "$h11aBands\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Pruebas H11.3a bandas fallidas' }

python "$h11aBands\h11_3a_bandas_velocidad.py" --root . --nom $nom --hib $hib --vine-actions $act
if ($LASTEXITCODE -ne 0) { throw 'Preflight H11.3a bandas fallido' }

python "$h11aBands\h11_3a_bandas_velocidad.py" --root . --nom $nom --hib $hib --vine-actions $act --guardar
if ($LASTEXITCODE -ne 0) { throw 'Auditoría H11.3a bandas fallida' }
```

## Productos

- `estadisticos_bandas_h11_3a.csv`: por origen/cohorte, velocidad y aceleración o jerk; número de muestras y de unidades, media, dispersión, cuantiles, fracción con |a| cerca de cero y dt mediano.
- `distancias_bandas_h11_3a.csv`: Wasserstein/KS por banda siempre que ambas poblaciones tengan al menos 30 muestras, sin inferencia.
- `comparacion_pareada_bandas_h11_3a.csv`: diferencias del mismo vehículo entre escenarios por banda de velocidad, cuando tiene >=10 observaciones válidas en ambos brazos.
- `auditoria_comandos_lider_h11_3a.csv`: trayectoria del líder al emitir orden, TTC cinemático, signo ordenado, aceleración observada y cruce de observadores H10/H11.2.
- `manifiesto_h11_3a_bandas.json`: SHA de fuentes y resultados, versión del código original y su dependencia, parámetros y advertencias.
- `informe_h11_3a_bandas.md`: criterios de interpretación.

## Límites científicos

- Las bandas `(5,20]`, `(20,40]`, `(40,60]`, `(60,+infinito)` son cortes descriptivos preestablecidos **no optimizados sobre el piloto**. Existen diferencias de contexto, velocidad límite, geometría, densidad, sensor y dt incluso dentro de la banda.
- La aceleración cero exacta en PoliDriving puede reflejar resolución de sensor; el análisis incorpora sensibilidades `|a|<=0,05` y `<=0,10` m/s², que tampoco implican parada.
- Jerk depende del intervalo de muestreo. NO se interpola, suaviza, ni remuestrea PoliDriving sin justificar la adquisición.
- La referencia tiene únicamente cinco sesiones de desarrollo de cuatro conductores. No se hacen pruebas de significancia; muestras anidadas en vehículo/sesión son autocorrelacionadas.
- El nominal lleva una **etiqueta de cohorte contrafactual** derivada del híbrido, nunca intervenciones activas nominales.
- El emparejamiento por vehículo/banda no controla las circunstancias ni usa el mismo instante, por tanto no identifica efecto causal de Vine.
- El modelo de TTC constante usa la velocidad relativa del seguidor/líder en el instante de emisión y no predice freno del líder ni seguridad legal.
- La muestra de 100 comandos Vine tiene selección por elegibilidad, presupuesto y reglas del guard; no mide la población general ni Quito.
- Ningún resultado basta para validar representatividad de tráfico imprudente de Quito ni para optimizar controladores semafóricos.

## Resultados preliminares del caso ya conocido

El usuario obtuvo 100 comandos, 100 observaciones posteriores y dos desviaciones absolutas mayores de 0,1 m/s², en los vehículos 71 y 210. Dos comandos presentaron TTC de cierre menor de tres segundos en el instante de emisión: vehículo 8 (orden de frenado efectiva) y 210 (aceleración solicitada, no reproducida exactamente). Estos son hechos de la auditoría previa, **no salidas ejecutadas de esta versión nueva**.
