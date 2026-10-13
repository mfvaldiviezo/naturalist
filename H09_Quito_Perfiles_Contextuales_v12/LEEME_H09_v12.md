# Hito 09 v1.2 — Perfiles contextuales persistentes y auditoría SUMO

## Estado y alcance

**Entregable ejecutable para un piloto en Hangzhou 4×4; no se ha ejecutado aquí en SUMO real.** En el entorno del usuario ya se validaron 19 pruebas offline del observador v1.1, dos pruebas positivas de paso por rojo/amarillo en una red de juguete, 207 pasos de línea proxy y 259 registros de velocidad en Hangzhou. Este nuevo módulo tiene **11 pruebas unitarias adicionales**, verificadas offline, y una prueba de preparación de 90/300 con archivos sintéticos. NO se modifica H08b, POLIDriving, Vine ni el framework original.

**Se conservan dos capas conceptualmente distintas:**

- **Conducción contextual implementada:** SUMO recibe parámetros de un `vType` persistente por vehículo: `tau`, `minGap`, `speedFactor`, `jmDriveAfterYellowTime`, `jmDriveAfterRedTime` y `jmIgnoreKeepClearTime`. No se envían comandos `setSpeed`, `setSpeedMode`, ni cambios de fase con TraCI. Es el propio SUMO quien decide cómo se mueve el conductor y cuándo puede ocurrir una conducta según la fase, el seguimiento y el espacio. **Estos parámetros son HIPÓTESIS de estrés, NO números aprendidos de Quito.** No hay probabilidades individuales calibradas.
- **Movimiento Vine:** sus artefactos previos se mantienen. **La inyección temporal Vine todavía NO se integra en v1.2**. Tras comprobar este piloto y el control `baseline==probe`, el futuro hito deberá conectar el generador Vine y evitar que sus comandos prevalezcan sobre decisiones semafóricas sin auditoría.

El objetivo próximo es medir el **efecto de los perfiles** y sus resultados reales, no repetir la preparación de PoliDriving.

## Base empírica — Quito

La referencia publicada original y sus advertencias están en `datos_referencia/objetivos_quito_h09.json`, una copia del archivo auditado de la versión 1.1. El estudio Díaz-Muñoz et al., *Smart Cities* (2026), https://doi.org/10.3390/smartcities9090140, documenta 9.643 vehículos, 343 eventos de rojo y 168 de amarillo en tres intersecciones. Los denominadores de Quito NO son oportunidades individuales por estado semafórico y sus intersecciones no son físicamente equivalentes a Hangzhou. El informe Johns Hopkins/BIGRS proporciona una referencia agregada aproximada de 20 % de exceso de velocidad con otro protocolo de muestreo. No se estima una probabilidad condicional individual a partir de estas tasas.

El archivo `config/escenarios_exploratorios.json` contiene **familias de estrés ablatorias**, no distribuciones empíricas. Cada parámetro tendrá que someterse a experimentos de sensibilidad, múltiples semillas y validación de agregados con denominadores armonizados si se pretende hablar de calibración externa. **No presentar una similitud en porcentajes como éxito de calibración.**

Fuentes técnicas de la semántica del simulador:

- https://eclipse.dev/sumo/docs/Definition_of_Vehicles,_Vehicle_Types,_and_Routes.html#junction-model-parameters
- https://eclipse.dev/sumo/docs/TraCI/Change_Vehicle_State.html

## ¿Qué cambia v1.2?

**En `active`:** analiza el `--sumocfg` existente, resuelve el XML de red/ruta, contabiliza vehículos explícitos `depart < pasos * step_length`, selecciona exactamente y sin duplicados el 15 %, 30 % o 50 %, copia la ruta completa en una carpeta NUEVA, crea un vType con los parámetros experimentales y asigna ese tipo solo a los IDs elegidos. Como el tipo se asigna antes de la salida, es **persistente desde el inicio del recorrido**, a diferencia de intervenciones puntuales. No se alteran las rutas ni cantidades de vehículos. Las cohortes son **anidadas para la misma semilla dentro de H09 v1.2**. Su hash puede NO coincidir con el algoritmo de H08b, de modo que los conjuntos de IDs no se deben declarar idénticos sin compararlos. La asignación porcentual es sobre salidas previstas; el número realmente circulante se audita aparte.

**En `baseline` y `probe`:** utiliza sin cambios los tres archivos originales de SUMO y solo observa. Se comparará SHA256 del CSV de tráfico para asegurarse de que ambos sean idénticos. El observador v1.1 se llama una vez DESPUÉS de cada paso SUMO, con la misma ventana de velocidad en todos los escenarios.

**Registro:** cada corrida produce `eventos_h09.csv` (observador v1.1), `trafico_h09.csv` (por paso), `cohorte_h09.csv` (asignación planeada), `exposicion_h09.csv` (tipo observado, seguimiento, intentos próximos a TLS y cruces observados), `manifest_H09.json` (hashes, parámetros, estado, semilla, cifras). Se registra si un vehículo seleccionado llegó a aparecer y tuvo el tipo previsto; **eso NO equivale a afirmar que cometió una infracción**. Un vehículo puede circular con parámetros imprudentes sin llegar a cruzar en rojo.

**Limitaciones:** `internal_stopped_snapshots` es solo una señal proxy de detención dentro de la intersección, no una demostración de gridlock. La detección de pasos por línea sigue siendo un proxy con abstención ante cambios de fase. Deberá validarse específicamente el mecanismo de bloqueo y el denominador de oportunidades semafóricas antes de una inferencia empírica fuerte.

## Instalación en Windows PowerShell

Descargar `H09_Quito_Perfiles_Contextuales_v12.zip` y extraerlo **directamente** en:

`C:\Proyecto_Tesis_Final_V1\revision_naturalista`

El ZIP contiene la carpeta `H09_Quito_Perfiles_Contextuales_v12` con este `LEEME`, `scripts`, `tests`, `config`, `datos_referencia` y `ejecutar_piloto_15pct.ps1`.

Se requiere previamente `H09_Quito_Instrumentacion_v11`, `resultados/h09_zonas_velocidad_generadas_v11.json` y `resultados/ntvc_vine_r_07_hangzhou_piloto/hangzhou_vine_sin_additional.sumocfg`. Todos existen según las salidas que proporcionaste, salvo que se hayan movido.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
$pkg = '.\H09_Quito_Perfiles_Contextuales_v12'
python -m unittest discover -s "$pkg\tests" -v
```

### Piloto recomendado: baseline / probe / active 15 %

```powershell
& "$pkg\ejecutar_piloto_15pct.ps1"
```

La ejecución crea 3 carpetas nuevas dentro de `resultados/h09_v12_piloto_101/` y al final `comparacion_descriptiva.csv`. Tiene guardas para no sobrescribir datos; si ya existen, **no borrarlos**, elige otro nombre en PowerShell. Antes del piloto activo, el script presenta una confirmación textual explícita a través de `--ack-active`. No se modifica el benchmark original.

### Preparación previa opcional (sin SUMO)

```powershell
python "$pkg\scripts\piloto_perfiles_h09_v12.py" `
 --sumocfg '.\resultados\ntvc_vine_r_07_hangzhou_piloto\hangzhou_vine_sin_additional.sumocfg' `
 --modo active --porcentaje 30 --familia combinado --seed 101 `
 --ack-active ESCENARIO_EXPLORATORIO_NO_CALIBRADO `
 --preparar-solo --output '.\resultados\h09_v12_preparacion_30_101'
```

Esto verifica que la ruta copiada contiene exactamente el perfil en vehículos asignados, pero **no certifica que la simulación vaya a ejecutar infracciones**.

### Experimentos posteriores (no automáticos)

Repetir con 15, 30 y 50 %, cada familia `seguimiento`, `semaforos`, `bloqueo`, `combinado`, varias semillas comparables y controles `baseline/probe`. Mantener fija la demanda, tiempos y controles para cada bloque. Evitar ajustar todos los parámetros a la vez: las ablataciones permiten identificar mecanismos.

## Condiciones de rechazo

Se detiene sin intentar arreglar silenciosamente si falta un archivo original, el config tiene adicionales incompatibles, contiene `flow` no expandido, múltiples rutas, `vType` base modificado, IDs repetidos, un vehículo seleccionado tiene un tipo explícito diferente de `DEFAULT_VEHTYPE`, las unidades no son válidas, se intenta reutilizar una carpeta o `baseline != probe` en la comparación. En caso de error, conservar logs; no borrar el escenario ni los originales.

## Criterios de aceptación de la siguiente corrida

1. `baseline` y `probe`: mismo `traffic_sha256` e iguales inputs de red/config/rutas.
2. `active15`: cohorte asignada exactamente al 15 % del *roster planificado* (`n_assigned`) e identificadores anidados con otros porcentajes del mismo H09; comprobar `n_selected_seen` y `n_selected_verified_vtype`.
3. `eventos_h09.csv` con rojo/amarillo/verde/unknown **clasificados sin imputar desconocidos**. No se exige ningún mínimo artificial de infracciones.
4. Registrar colisiones/teletransportes si ocurren: un perfil estresante puede ocasionar problemas; no declararlo seguro por ausencia en una sola semilla.
5. Comparación con Quito se limita a **validación exploratoria agregada** hasta establecer equivalencia de definiciones, intersecciones, períodos y oportunidades.
