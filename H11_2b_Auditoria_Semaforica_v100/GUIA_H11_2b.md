# Hito 11.2b — Auditoría automatizada de aproximaciones semafóricas

**Versión:** 1.0.0 | **Estado:** análisis offline, descriptivo, solo lectura sobre H10/H11.2.

Este paquete **NO ejecuta SUMO**, **NO altera** H08b, H09, Vine Student, H10 ni H11.2, y **NO calibra** ninguna tasa al tráfico de Quito. Lee los CSV de las dos corridas H11.2 con invariancia pareada comprobada (semilla 101, 600 pasos de 0,5 s), reconstruye episodios de aproximación y genera informes en una carpeta **nueva** bajo `resultados/`.

## 1. Instalación

Descomprime el ZIP en:

`C:\Proyecto_Tesis_Final_V1\revision_naturalista`

Debe quedar:

`C:\Proyecto_Tesis_Final_V1\revision_naturalista\H11_2b_Auditoria_Semaforica_v100\h11_2b_auditar_semaforos.py`

No necesita bibliotecas Python externas; utiliza la biblioteca estándar. Puede ejecutarse dentro de `tsc-env`.

## 2. Pruebas locales

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h11b = '.\H11_2b_Auditoria_Semaforica_v100'
python -m unittest discover -s "$h11b\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'FALLARON pruebas H11.2b' }
```

En el desarrollo se superaron **16 pruebas sintéticas**, incluidas integridad SHA-256, cohortes, denominadores, pares, archivos alterados y salida nueva. Esto NO sustituye la ejecución con los datos reales del usuario.

## 3. Definir las fuentes ya generadas

Estas rutas son las que resultaron de las corridas nominal e híbrida de H11.2 en esta sesión. No sustituyas una por el CSV de otro experimento:

```powershell
$nom = '.\resultados\h11_2_pareado_h10_nominal_20261011_184549_504694\observado\telemetria'
$hib = '.\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\telemetria'
$h10run = '.\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\hibrido_contextual'

@($nom,$hib,"$h10run\eventos_h09.csv","$h10run\acciones_hito08.csv") | ForEach-Object {
    if (!(Test-Path $_)) { throw "Fuente ausente: $_" }
}
```

## 4. Preflight estricto, **sin escribir reportes**

```powershell
python "$h11b\h11_2b_auditar_semaforos.py" `
  --root . `
  --nom $nom `
  --hib $hib `
  --require-paired

if ($LASTEXITCODE -ne 0) { throw 'FALLO preflight H11.2b' }
```

Comprueba los cuatro archivos H11.2 por cada escenario contra `manifest_h11_2.json`; además exige el `comparacion_h11_2.json` de cada corrida pareada, cuyo estado debe ser `INVARIANZA_BYTE_A_BYTE_VERIFICADA`, y **recalcula los hashes de los archivos H10 control/observado** citados por esa auditoría.

## 5. Auditoría descriptiva completa

```powershell
python "$h11b\h11_2b_auditar_semaforos.py" `
  --root . `
  --nom $nom `
  --hib $hib `
  --h09-events "$h10run\eventos_h09.csv" `
  --vine-actions "$h10run\acciones_hito08.csv" `
  --a-ref 4.5 `
  --require-paired `
  --guardar

if ($LASTEXITCODE -ne 0) { throw 'FALLO auditoria H11.2b' }
```

**`--a-ref 4.5` es un supuesto mecánico de sensibilidad**, no un parámetro empírico validado para Quito. Por diseño calcula factibilidad de detención a 0,5 y 1,0 segundos de reacción hipotéticos.

La salida se guarda en `resultados\h11_2b_auditoria_AAAAMMDD_HHMMSS_microsegundos\`. No se sobrescribe ninguna carpeta existente. `--output` permite dar otra ruta nueva dentro de `resultados/`.

## 6. Archivos de salida

| Archivo | Interpretación |
|---|---|
| `episodios_h11_2b.csv` | **Un registro por episodio de aproximación**, incluso sin cruce detectado. Primer ámbar, distancia/velocidad, factibilidad mecánica, frenado observado, calidad de cruce y comandos Vine en la ventana |
| `movimientos_emparejados_h11_2b.csv` | Emparejamiento entre brazos por **ID del vehículo + TLS + link index + carril de entrada + orden de visita**, sin exigir igualdad de tiempos |
| `matriz_transiciones_h11_2b.csv` | Tabla verde/amarillo/rojo/desconocido/sin cruce de nominal a híbrido para los episodios emparejados |
| `metricas_cohortes_h11_2b.csv` | Indicadores de exposición por **cohorte activa** en cada brazo |
| `metricas_cohortes_objetivo_h11_2b.csv` | En nominal, grupos de vehículos etiquetados según su **cohorte en el híbrido**. Son etiquetas contrafactuales: en nominal NO se activaron esos mecanismos |
| `reconciliacion_h09_h11.csv` | Pareos entre H09 confirmado y H11 proxy por vehículo, semáforo y tiempo con tolerancia de 0,5 s. No eleva eventos proxy a confirmados |
| `resumen_h11_2b.json` | Totales, matriz, procedencia verificada, integridad de los archivos, limitaciones y estado de reconciliación |
| `informe_h11_2b.md` | Reporte narrativo de solo lectura para revisar y eventualmente integrar a la tesis |
| `manifest_h11_2b.json` | SHA-256 de los resultados generados y manifiestos H11.2 de origen |

## 7. Definiciones y límites científicos

- **Episodio de aproximación:** identificado por `episode_id` del observador H11.2. Se genera una oportunidad al observar por primera vez cada color del semáforo dentro de su horizonte (80 m por defecto en H11.2). Los colores no son excluyentes: un episodio puede ver verde, luego ámbar, luego rojo.
- **Censura:** `sin_cruce_observado` NO significa obediencia: puede ser parada, desaparición de la observación, salida de ruta o fin de simulación.
- **Posibilidad mecánica de parada:** para la primera observación ámbar, `d_necesaria = v*t_reaccion + v²/(2*a_ref)`. Se compara con la distancia observada. No contempla pendiente, adherencia, incertidumbre geométrica ni comportamiento humano real. Reacción de 0,5 o 1 segundo es solo una sensibilidad.
- **Riesgo de sesgo por selección:** evitar dividir cruces en rojo únicamente por cruces completados o únicamente por vehículos observados. La tabla incluye denominadores por episodio, condiciones de oportunidad y sin-cruce, pero no constituye una tasa real de infracción en Quito.
- **Cruce proxy:** deriva de una transición de carril cercana a una línea de parada y señal observada; no prueba infracción legal ni comportamiento intencional. `confirmed` H09 usa su propio protocolo y cobertura.
- **Cohortes:** `both`, `h09_only`, `vine_only`, `neither`. El nominal real queda en `unclassified`. La etiqueta contrafactual es solo para comparación por los mismos IDs.
- **Asociación Vine:** contar comandos efectivos durante el episodio no equivale a atribuirles causalmente un cruce. H10 podría registrar intervenciones anteriores con efectos indirectos; los métodos no deshacen esas interacciones.
- **Una sola semilla:** los episodios y las observaciones de un mismo vehículo o red están correlacionados. NO calcular aquí valores-p ni intervalos de confianza que supongan muestras independientes.
- **Quito:** no existen en estos archivos observaciones de campo capaces de validar tasas de imprudencia locales. El paso posterior H11.3 requiere fuentes externas y protocolo de calibración.

## 8. Qué devolver para interpretación

Comparte la salida textual que comienza en `INTEGRIDAD: OK`, el `informe_h11_2b.md` y, preferentemente, `resumen_h11_2b.json`. Para investigar detalles o discrepancias, añade `movimientos_emparejados_h11_2b.csv` y `reconciliacion_h09_h11.csv`.

**Criterio técnico de cierre:** auditoría de integridad aceptada, episodios con denominadores explícitos, emparejamiento verificable y diferencias H09–H11 mantenidas con su calidad original. Esto NO equivale a cerrar la validación empírica ni la causalidad del modelo generador.
