# H11.2c — Caracterización integral de conducción en SUMO

**Versión:** v1.0.0 · **Modo:** SOLO LECTURA · **Base:** H11.2 nominal e híbrido contextual, semilla 101, 600 pasos × 0,5 s.

## Objetivo científico

Registrar cuantitativamente las diferencias **observadas** entre el escenario nominal y el híbrido contextual de H10/H11.2, sin modificar SUMO, H08b, Vine Student, H09, los controladores, los archivos históricos ni las cuotas del inyector. **No se intenta mejorar el tráfico o maximizar el caos:** este hito desarrolla evidencia descriptiva para validar posteriormente la representatividad del comportamiento en Quito.

**Prerequisito:** las simulaciones H11.2 pareadas ya superaron el control de invariancia byte a byte, y H11.2b cerró la auditoría de aproximaciones semafóricas. No se volverá a ejecutar SUMO.

## Instalación

Extraer `H11_2c_Caracterizacion_Integral_v100.zip` directamente en:

`C:\Proyecto_Tesis_Final_V1\revision_naturalista`

La carpeta creada debe ser `H11_2c_Caracterizacion_Integral_v100`.

## Ejecución desde PowerShell (conda `tsc-env`)

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env

$h11c = ".\H11_2c_Caracterizacion_Integral_v100"

# 1. Pruebas locales
python -m unittest discover -s "$h11c\tests" -v
if ($LASTEXITCODE -ne 0) { throw "Fallaron las pruebas H11.2c" }

# 2. Archivos H11.2 reales; NO utilizar las carpetas de H11.2b como origen
$nom = ".\resultados\h11_2_pareado_h10_nominal_20261011_184549_504694\observado\telemetria"
$hib = ".\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\telemetria"
$act = ".\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\hibrido_contextual\acciones_hito08.csv"

# 3. Revalidar SHA-256 y comparación pareada; NO crea ficheros
python "$h11c\h11_2c_caracterizar.py" `
    --root . --nom $nom --hib $hib `
    --vine-actions $act --require-paired
if ($LASTEXITCODE -ne 0) { throw "Preflight H11.2c fallido" }

# 4. Escribir informes en carpeta NUEVA debajo de resultados/
python "$h11c\h11_2c_caracterizar.py" `
    --root . --nom $nom --hib $hib `
    --vine-actions $act --require-paired --guardar
if ($LASTEXITCODE -ne 0) { throw "Auditoria H11.2c fallida" }
```

**Solo se crean informes cuando se especifica `--guardar`.** Si el destino existe, el auditor se detiene sin sobrescribir. `--require-paired` comprueba físicamente de nuevo los SHA de los archivos originales H10 de los brazos control/observado (uno por escenario). El paquete no llama a SUMO ni escribe dentro de las dos carpetas `telemetria`.

## Variables y denominadores

- **Velocidad:** registros con velocidad y límite positivo del carril SUMO disponibles. Se ofrecen tres sensibilidades: cualquier superación (>1e-6 m/s), límite +3,6 km/h (por defecto) y límite ×1,10. Es **proxy de velocidad respecto a configuración vial**, NO infracción legal. Se presenta además separado por carriles externos e internos.
- **Seguimiento:** `headway <1 s` exclusivamente donde se identifica líder, separación no negativa y headway definido. El denominador no es el total de vehículos/pasos.
- **TTC:** `TTC <2 s` exclusivamente en registros con TTC finito observado (normalmente con velocidad relativa de cierre positiva). Las situaciones de TTC no calculable no se contabilizan como seguras.
- **Frenada fuerte:** aceleración ≤−4,5 m/s²; **extrema:** aceleración ≤−7 m/s². Umbrales exploratorios de sensibilidad, NO rangos validados con datos de Quito.
- **Jerk alto:** |jerk observado| ≥8 m/s³ (sensibilidad exploratoria). El jerk es sensible a intervalo de muestreo y al método de derivación.
- **Episodios de riesgo:** secuencias de muestras positivas consecutivas del mismo vehículo a 0,5 s; duración observada = número de muestras positivas ×0,5 s. No se rellena ningún hueco. Se marca censura izquierda o derecha y se cuenta por separado vehículo afectado y episodio.
- **Cohortes:** en híbrido `both`, `h09_only`, `vine_only`, `neither` según roster efectivamente asignado; en el nominal son `unclassified` realmente. Para comparar por IDs, se añade `cohorte_objetivo` al nominal como etiqueta **contrafactual**, nunca como tratamiento real.
- **Intersecciones:** importa eventos H11.2 de detención en carril interno; no declara obstrucción real de flujos ni gridlock confirmado.
- **Seguridad:** conserva por separado los contadores TraCI (`emergency_stop_count`) y las frenadas intensas observadas en la aceleración. Una advertencia `emergency braking` de SUMO puede coexistir con `emergency_stop_count = 0`.

## Productos de salida

En `resultados\h11_2c_caracterizacion_<fecha>`:

| Archivo | Uso |
|---|---|
| `informe_h11_2c.md` | Resumen de métricas y límites científicos |
| `metricas_cohortes_h11_2c.csv` | Conteos, denominadores, proporciones, número y duración de episodios por cohorte |
| `metricas_carril_h11_2c.csv` | Estratificación entre carriles internos y externos |
| `episodios_riesgo_h11_2c.csv` | Cada episodio continuo, duración, extremos y comandos Vine cercanos (sin causalidad) |
| `vehiculos_h11_2c.csv` | Tasas y episodios por vehículo en cada condición |
| `comparacion_vehiculos_h11_2c.csv` | Emparejamiento nominal vs híbrido por ID; faltantes no se inventan |
| `comparacion_grupos_pareados_h11_2c.csv` | Promedio descriptivo de diferencias individuales de los vehículos presentes en ambos brazos |
| `detenciones_internas_h11_2c.csv` | Eventos candidatos; gridlock no confirmado |
| `seguridad_h11_2c.csv` | Conteos TraCI y contraste con frenadas extremas observadas |
| `manifiesto_h11_2c.json` | Orígenes, parámetros, hashes, procedencia y advertencias |

## Para compartir el resultado de forma compacta

Comparte la salida completa de PowerShell del paso 4 y adjunta `informe_h11_2c.md`, `metricas_cohortes_h11_2c.csv` y `comparacion_grupos_pareados_h11_2c.csv`. No hace falta adjuntar las 151.205 muestras individuales salvo que detectemos una inconsistencia.

Si deseas investigar el caso de frenada del vehículo 31 dentro del nuevo informe, usa:

```powershell
$out = ".\resultados\h11_2c_caracterizacion_<FECHA_REAL>"
Import-Csv "$out\episodios_riesgo_h11_2c.csv" |
    Where-Object { $_.vehicle_id -eq "31" -and $_.indicador -like "frenada*" } |
    Select-Object escenario, vehicle_id, indicador, inicio_s,
       fin_ultima_muestra_s, duracion_observada_s, valor_extremo |
    Format-Table -AutoSize
```

Reemplazar `<FECHA_REAL>` por el nombre de la nueva carpeta reportado por la ejecución.

## Criterios para aceptar este hito

1. Pasan las pruebas automáticas y el chequeo `INTEGRIDAD: OK`.
2. Se revalida la procedencia pareada e invariancia en ambos escenarios.
3. Los recuentos de 75.705 filas nominales y 75.500 híbridas coinciden con las fuentes (si esos datos no se modificaron).
4. Los porcentajes usan denominadores específicos de cada variable y se distinguen muestras, episodios y vehículos.
5. Se conserva la distinción de asignación de cohorte, comandos ejecutados y conductas observadas.
6. No se declara representatividad de Quito, gridlock confirmado, causalidad de H09/Vine ni significancia estadística a partir de una única semilla.

## Qué NO hace el paquete

No estima tasas reales de Quito; no calibra sobre PoliDriving ni modifica sus archivos; no cambia vType/TraCI, semáforos, velocidad, aceleración, rutas o el modelo Vine. No sustituye H11.2b (auditoría semafórica) ni valida conductas en campo. En H11.3 corresponderá construir referencias empíricas comparables.
