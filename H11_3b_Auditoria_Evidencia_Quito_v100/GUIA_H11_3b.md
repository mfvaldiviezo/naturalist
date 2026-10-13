# H11.3b v1.0 — Auditoría de evidencia e identificabilidad de la conducción imprudente de Quito

## Propósito

Producir una matriz que diferencia lo realmente observado en Quito (POLIDriving desarrollo) de métricas/proxies SUMO (H11.2) y de cantidades que **no pueden identificarse** con estas fuentes. Responde a las observaciones P0-01 y P0-02 de la revisión del artículo T-ITS. **No es calibración, ni certificación, ni un modelo nuevo.**

## Dependencias históricas obligatorias e inalterables

- `H11_3a_Contraste_Aplicado_v100/h11_3a_contraste_aplicado.py` (verificador de integridad y cohortes de H01, procedencia H11.2).
- `H11_2c_Caracterizacion_Integral_v100/h11_2c_caracterizar.py` (verificador de manifests de telemetría y equivalencia SHA).
- `resultados/ntvc_vine_r_01_cohortes_movimiento_regenerado/` o `resultados/ntvc_vine_r_01_cohortes_movimiento/` con `manifest.json` y `cohortes_muestras_verificadas.csv`.
- Las dos carpetas originales H11.2 nominal/híbrido y el CSV de acciones del **mismo** brazo observado híbrido.

**Prohibiciones:** no leer archivos RAW de POLIDriving, no abrir Richard ni Alonso 20231229_151643 (reserva), no leer `furious`, no entrenar ni ejecutar SUMO, no modificar resultados/contenidos precedentes, no estimar prevalencia Quito a partir de penetración 15/30/50%.

## Ejecución en PowerShell

Descomprimir el ZIP al directorio raíz `C:\Proyecto_Tesis_Final_V1\revision_naturalista`, conservando la carpeta `H11_3b_Auditoria_Evidencia_Quito_v100`.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env

$h11b = ".\H11_3b_Auditoria_Evidencia_Quito_v100"
$nom = ".\resultados\h11_2_pareado_h10_nominal_20261011_184549_504694\observado\telemetria"
$hib = ".\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\telemetria"
$act = ".\resultados\h11_2_pareado_h10_hibrido_contextual_20261011_185111_910351\observado\hibrido_contextual\acciones_hito08.csv"

python -m unittest discover -s "$h11b\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Tests H11.3b fallidos' }

# PREFLIGHT SIN ESCRITURA
python "$h11b\h11_3b_auditar_evidencia.py" --root . --nom $nom --hib $hib --vine-actions $act
if ($LASTEXITCODE -ne 0) { throw 'Procedencia H11.3b inválida' }

# ESCRIBE EXCLUSIVAMENTE EN NUEVA CARPETA resultados/h11_3b_evidencia_...
python "$h11b\h11_3b_auditar_evidencia.py" --root . --nom $nom --hib $hib --vine-actions $act --guardar
if ($LASTEXITCODE -ne 0) { throw 'Auditoría H11.3b fallida' }
```

## Resultados

- `cobertura_polidriving_desarrollo_h11_3b.csv`: estadísticas de las **cinco sesiones** habilitadas (cuatro conductores) sin duplicar conteos como individuos independientes; velocidad, dt, aceleración, jerk, número de transiciones por banda.
- `matriz_evidencia_quito_h11_3b.csv`: nueve dimensiones de conducta y su grado de identificabilidad real.
- `puertas_director_pdf_h11_3b.csv`: P0-01 y P0-02, estatus honesto y requisitos de cierre.
- `dictamen_h11_3b.md`: interpretación lista para integrar metodológicamente a la tesis, no un resultado de campo nuevo.
- `manifiesto_h11_3b.json`: SHA-256 de fuentes, versiones, recuentos y salidas.

## Significado de estados

- `OBSERVABLE_PARCIAL`: fuente real útil, pero sin validez externa/calibración acreditada.
- `NO_IDENTIFICABLE_ACTUALMENTE`: no hay estimando legítimo con la combinación de datos verificados.
- `SIN_ANCLA_EMPIRICA`: SUMO mide el proxy, pero H01 no contiene una medida comparable en Quito.
- `FUENTE_NO_INTEGRADA`: existe fuente descrita públicamente, pero no forma parte de las sesiones verificadas ni del protocolo congelado.
- `FUENTE_EXCLUIDA`: sintéticos y reservados no se convierten en evidencia observacional.

## Advertencias

- POLIDriving fue recogido en dos rutas Quito con cinco conductores reales, pero no es un muestreo representativo de infractores; su conductor `furious` es sintético.
- El conjunto público describe una variable `design_speed`; su significado no se transforma sin verificación en límite **legal**.
- Su subconjunto de 1980 registros con clases de riesgo no corresponde a infracciones directamente etiquetadas.
- H11.3a demuestra una brecha de jerk persistente; la ingeniería de integración H10/H11 funciona, pero no certifica representatividad.
- Bloqueo artificial estático no debe mezclarse con imprudencia naturalista; requieren brazos experimentales separados.

## Fuente empírica

Marcillo et al. (2024), *POLIDriving: A Public-Access Driving Dataset for Road Traffic Safety Analysis*, Applied Sciences 14(14), 6300. DOI https://doi.org/10.3390/app14146300. Repositorio: https://github.com/laboratorioAI/polidriving.
