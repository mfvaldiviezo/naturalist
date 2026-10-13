# H09 — Validación instrumental v1.1 (Quito como referencia empírica)

**Estado:** entrega de software para auditoría offline y pruebas controladas; **no son nuevos resultados SUMO** hasta ejecutar los comandos indicados en el equipo con SUMO. Mantiene intactos todos los datos, scripts y resultados anteriores de Vine/H08b/H09 v1.0.

## Qué corrige y qué NO corrige

1. **Auditoría sin simulación:** `scripts/auditar_eventos_h09.py` lee `resultados/h09_quito_observador_base_101/eventos_h09.csv` de la ejecución anterior y separa cruces confirmados, fases desconocidas y transición de fase. Los valores indicados por el usuario son: 207 cruces proxy, 197 verdes, 10 desconocidos, 158 vehículos diferentes; 8 transiciones rojo→verde, 2 verde→amarillo. **No requiere volver a iniciar SUMO**.
2. **Observador actualizado:** `scripts/observador_traci_h09_v11.py` conserva las columnas del CSV original y añade una comprobación de `getNextSwitch(tls)` cuando esa API esté disponible; si hay un cambio programado dentro del intervalo observado, se abstiene de asignar rojo/amarillo/verde aunque coincidan los colores extremos. El cruce sigue siendo un proxy de transición, **no** una reconstrucción geométrica exacta ni equivalente al estudio de Quito. Respetar el mismo criterio de muestreo en todas las variantes.
3. **Prueba positiva artificial:** `scripts/prueba_positiva_aislada_h09.py` genera una **nueva red microscópica de juguete** con `netconvert` e intenta observar un cruce forzado en rojo y otro en amarillo. Solo en esta red artificial (1 vehículo y ninguna demanda ajena) modifica TLS y `speedMode=7`. **Nunca ejecutar este test sobre Hangzhou o sobre resultados previos**. Si los eventos no se detectan, termina con error; no certifica nada silenciosamente.
4. **Zonas de velocidad:** `scripts/generar_zonas_velocidad_h09.py` lee exclusivamente la `hangzhou_4x4.net.xml` y crea JSON con carriles reales asociados a B1, B2 y C1. Ubica una ventana de medición a 45–15 m del final de cada carril de aproximación, siempre que su longitud lo permita. Es un muestreo instrumental propio **no comparable automáticamente** con la toma de datos Johns Hopkins/BIGRS Quito.
5. **19 tests offline:** los 11 tests heredados de H09 v1.0 más 8 nuevos para rojo/amarillo, transiciones de fase, auditoría y generación de zonas. Se ejecutan sin SUMO real y **NO sustituyen la prueba positiva aislada**.

## Instalación

Descomprimir `H09_Quito_Instrumentacion_v11.zip` directamente en
`C:\Proyecto_Tesis_Final_V1\revision_naturalista`. No sobrescribir `H09_Quito_Calibrador_v1`.

## Paso A — Auditar los 207 eventos existentes SIN ejecutar SUMO

En PowerShell (ambiente `tsc-env`):

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
$h09 = '.\H09_Quito_Instrumentacion_v11'
python "$h09\scripts\auditar_eventos_h09.py" `
  --eventos '.\resultados\h09_quito_observador_base_101\eventos_h09.csv' `
  --salida '.\resultados\h09_auditoria_offline_v11_101.json'
python -m unittest discover -s "$h09\tests" -v
```

Resultados esperados si el CSV es el mismo que el usuario resumió en el chat: 207 cruces, 158 vehículos únicos, 10 `unknown`, 8 `red->green`, 2 `green->yellow`, `speed_samples=0` y **19 tests OK**. Si los conteos difieren, investigar primero hashes/dataset, no forzar valores.

## Paso B — Probar detección POSITIVA en red nueva y aislada

**Este test SI inicia SUMO** y envía comandos que fuerzan semáforos y velocidad. Hace falta `sumo` y `netconvert` en PATH, además de `traci` disponible en el Python activo. Se generará una red distinta de Hangzhou dentro de una carpeta nueva:

```powershell
python "$h09\scripts\prueba_positiva_aislada_h09.py" `
  --permitir-infracciones-aisladas `
  --salida-dir '.\resultados\h09_prueba_positiva_aislada_v11_101'
```

**Aceptar únicamente si** informa `positive_detected: true` para `red` y `yellow`, y `confirmed_positive_count>=1` por escenario. Los CSV y las salidas SUMO quedan bajo esa nueva carpeta. Si falla, conservar el informe y remitir errores; no modificar las fuentes o el benchmark para hacer que pase.

SUMO documenta que `speedMode=7` más `setSpeed` permite un cruce deliberado en rojo: https://eclipse.dev/sumo/docs/TraCI/Change_Vehicle_State.html . Esto se usa **exclusivamente como instrumento de prueba**, no como frecuencia naturalista ni parámetro del modelo H09.

## Paso C — Preparar muestreo de velocidad desde la red real, opcional

```powershell
$net = 'C:\Proyecto_Tesis_Final_V1\traffic_project\tsc_framework\sumo_configs\networks\hangzhou_4x4.net.xml'
python "$h09\scripts\generar_zonas_velocidad_h09.py" `
  --net $net --sites B1,B2,C1 `
  --salida '.\resultados\h09_zonas_velocidad_generadas_v11.json'
```

En **una ejecución posterior nueva** del baseline, usar:

```powershell
python "$h09\scripts\observador_traci_h09_v11.py" `
  --sumocfg '.\resultados\ntvc_vine_r_07_hangzhou_piloto\hangzhou_vine_sin_additional.sumocfg' `
  --seed 101 --pasos 600 --step-length 0.5 --sites B1,B2,C1 `
  --zonas-velocidad '.\resultados\h09_zonas_velocidad_generadas_v11.json' `
  --salida-dir '.\resultados\h09_observador_v11_speed_101'
```

**No ejecutar el paso C si no hace falta una nueva simulación:** la corrida original ya está archivada. `speed_samples=0` en ella es correcto porque no se suministraron zonas de medición.

## Referencia y límites científicos

- Evidencia local publicada: Díaz-Muñoz et al. (2026), *Smart Cities*, `https://doi.org/10.3390/smartcities9090140`: 9.643 vehículos observados en tres intersecciones, 343 cruces en rojo, 168 en amarillo. El denominador de campo **no es** el número de oportunidades de pasar en rojo y **no coincide necesariamente** con los 207 pasos de línea proxy de SUMO Hangzhou.
- Velocidad: Johns Hopkins/BIGRS Quito: `https://publichealth.jhu.edu/sites/default/files/2024-02/20230602bigrsquito04pages.pdf`, prevalencia de alrededor de 20 % en el informe, con protocolo no armonizado con las zonas del simulador.
- `B1`, `B2` y `C1` son semáforos de **Hangzhou**, no intersecciones reales de Quito. Las configuraciones locales se compararán **descriptivamente** salvo acreditarse equivalencia geométrica y metodológica.
- Esta entrega **no contiene un modelo cuantitativo ya calibrado** para probabilidad condicional de infringir rojo, bloquear cruces o mantener distancia corta. Dichos parámetros permanecen desconocidos. La prueba con estado rojo forzado solo demuestra que el observador puede medir un evento deliberado bajo control.
- Los 15/30/50 % de H08b son porcentajes experimentales de perfiles asignados y no prevalencias empíricas de conductores imprudentes quiteños.

## Integridad

Todas las funciones de auditoría son de solo lectura; el registrador v1.1 no envía ningún comando de control. El script positivo sí envía comandos, pero su red, rutas y salidas se generan íntegramente en carpeta nueva, aislada de los archivos anteriores.
