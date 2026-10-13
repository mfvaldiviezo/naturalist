# H11.3a — Contraste cinemático aplicado PoliDriving–Vine–SUMO

**Versión 1.0.0 · solo lectura · no entrenar modelos · no abrir reservas · no ejecutar SUMO.**

## Por qué esta herramienta no repite experimentos antiguos

Los scripts `process_polidriving_verified.py`, `preparar_transiciones_temporales.py`, `validar_polidriving_sesiones.py`, `validar_polidriving_conductores.py`, `validar_coherencia_temporal.py` ya establecieron orígenes, transiciones, controles de test, comparaciones de generadores iid/Gaussian/bootstrap y diagnósticos temporales. A continuación H01–H05 ejecutaron filtrado de marcha, núcleo Vine Gaussian/Student, integración cinemática y experimentos SUMO **shadow**; H06–H10 aplicaron acciones, H11.2 registró trayectorias y H11.2c realizó tasas agregadas por cohorte.

La nueva comprobación compara **la fuente de desarrollo H01 ya enriquecida con velocidad** con la aceleración y jerk **realmente observados** en SUMO, diferenciando solo los instantes con un comando emitido. No reestima distribuciones de Vine, no usa datos RAW, no accede a Richard y no modifica archivos originales.

## Origen PoliDriving obligatorio

`resultados/ntvc_vine_r_01_cohortes_movimiento_regenerado` (o `..._cohortes_movimiento`), con `manifest.json` y `cohortes_muestras_verificadas.csv`.

- El manifiesto H01 debe indicar SHA de la fuente congelada `EBBB8BEB...669162C25`, cinco sesiones permitidas de cuatro conductores, y hash válido de `cohortes_muestras_verificadas.csv`.
- **NO USAR** directamente el CSV congelado inicial de siete sesiones con SHA `2E20FE...B9299D` para este contraste: contiene material reservado e incluye un esquema distinto. La herramienta no lo abre.
- **NO ABRIR** Richard `20231227_104130` ni la sesión Alonso `20231229_151643`.
- Se estudia solamente marcha >5 km/h. Los jerk comparables requieren velocidad >5 tanto antes como después en el mismo segmento. No se unen discontinuidades.

## Instalación y comandos PowerShell

Extraer ZIP dentro de `C:\Proyecto_Tesis_Final_V1\revision_naturalista`. La carpeta nueva es `H11_3a_Contraste_Aplicado_v100`.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env

$h11a = '.\H11_3a_Contraste_Aplicado_v100'
$nom = '.\resultados\h11_2_pareado_h10_nominal_20261011_184549_504694\observado\telemetria'
$hib = '.\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\telemetria'
$act = '.\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\hibrido_contextual\acciones_hito08.csv'

python -m unittest discover -s "$h11a\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Fallo unittest H11.3a' }

# SOLO PREFLIGHT: verifica hashes H01, H11.2 y comparaciones pareadas
python "$h11a\h11_3a_contraste_aplicado.py" --root . --nom $nom --hib $hib --vine-actions $act
if ($LASTEXITCODE -ne 0) { throw 'Fallo preflight H11.3a; NO ejecutar analisis' }

# Solo si la verificacion anterior fue correcta: nueva salida sin sobrescritura
python "$h11a\h11_3a_contraste_aplicado.py" --root . --nom $nom --hib $hib --vine-actions $act --guardar
if ($LASTEXITCODE -ne 0) { throw 'Fallo contraste H11.3a' }
```

Si H01 no está en las dos carpetas por defecto, se puede especificar explícitamente `--h01 '.\resultados\RUTA_H01_EXISTENTE'`. Debe contener los dos archivos verificados y encontrarse dentro de `resultados`.

**Requisito local:** conservar intacto `H11_2c_Caracterizacion_Integral_v100/h11_2c_caracterizar.py`, porque se reutilizan `verify_source` y `verify_paired` para comprobar de nuevo los hashes y la invariancia real. Se requieren pandas, numpy y scipy ya usados en el proyecto.

## Salidas

Se crea una carpeta nueva `resultados/h11_3a_contraste_<fecha>` con:

- `metricas_cinematica_h11_3a.csv`: cantidades, denominadores, cuantiles de aceleración y jerk, dt mediano, autocorrelación lag-1 dentro de segmentos y duración de rachas cero;
- `distancias_h11_3a.csv`: Wasserstein W1 y KS descriptivos entre PoliDriving desarrollo y seis grupos SUMO (nominal, híbrido completo y 4 cohortes), más una séptima submuestra de instantes de actuación Vine;
- `informe_h11_3a.md`: límites, interpretación y siguientes pruebas;
- `manifiesto_h11_3a.json`: hashes y procedencia de fuentes y de las salidas.

## Criterio científico

Esto es un **contraste de transferibilidad aplicado, preliminar**, NO una validación empírica final, ni una estimación de la prevalencia de infracciones de Quito:

1. `getAcceleration()` SUMO y aceleración registrada PoliDriving pueden responder a filtros, tasas de muestreo, canales y dinámicas distintas. Contrastar magnitudes solo si se entiende esa homologación.
2. Aceleración y jerk en PoliDriving se extraen sin interpolar y con `dt` irregular; SUMO utiliza `dt=0.5 s`. Las diferencias de jerk y autocorrelación pueden deberse al reloj.
3. El H01 está enriquecido con velocidad. Comparar a >5 km/h conserva la población de marcha, pero no elimina diferencias de distribución de velocidad, red, demanda ni geometría.
4. Las cohortes solo indican asignación; `hibrido_vine_actuado` selecciona muestras en los instantes objetivo de comandos efectivos. Esta submuestra está condicionada por elegibilidad/cuota, por lo que no es una réplica independiente de las muestras naturales.
5. No son unidades independientes las filas vehículo-paso ni transiciones dentro de la misma sesión/conductor. W1 y KS no tienen interpretación inferencial sin diseño de validación por conglomerados.
6. Una Vine Student no debe juzgarse solamente por W1 marginal; la coherencia física y la dependencia temporal son necesarias. No reabrir familias de cópulas ni utilizar el holdout tras mirar estas cifras.

## Estado

El código y las 10 pruebas sintéticas se verificaron localmente. La ejecución sobre tus artefactos PoliDriving–H11.2 solo puede completarse en tu entorno porque los CSV reales no se adjuntaron a esta conversación. Conserva la salida PowerShell y comparte `metricas_cinematica_h11_3a.csv`, `distancias_h11_3a.csv` y `manifiesto_h11_3a.json`.
