# H11.2 — Observador conductual PASIVO para Quito–SUMO

## Alcance y seguridad experimental

- **No** optimiza semáforos ni mejora tráfico. **No** modifica parámetros de H09, Vine, las cópulas, SUMO ni las rutas.
- El archivo `h11_2_observador_pasivo.py` **NO llama** `simulationStep()`, `traci.start()`, `setSpeed`, `setTau`, `setAcceleration`, `setSpeedMode` ni `setPhase`.
- La instrumentación se ejecuta **después del avance SUMO que ya realiza H10**, en un solo proceso TraCI. El enganche reversible de `h11_2_ejecutar_h10.py` está diseñado para el script H10 Python real, sin editarlo.
- **No renombres, borres ni sobrescribas** resultados de H08/H09/H10. El puente exige que el H10 que invoques escriba resultados en una **carpeta nueva**. No se conocen de antemano los argumentos del ejecutor de tu PC: determinar mediante preflight y tu PowerShell H10.
- Esta entrega ha sido probada con **TraCI simulado (fixture)** y la sintaxis Python. **No se ha ejecutado contra tus escenarios H10 reales** en este entorno.
- Los resultados son **proxies / telemetría de SUMO**; NO prueban calibración del tráfico imprudente de Quito.

## 1. Instalación y pruebas

Descomprime `H11_2_Observador_Pasivo_v100.zip` directamente en `C:\Proyecto_Tesis_Final_V1\revision_naturalista`. Queda la carpeta `H11_2_Observador_Pasivo_v100`.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h11 = '.\H11_2_Observador_Pasivo_v100'

python -m unittest discover -s "$h11\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron pruebas H11.2' }

python "$h11\h11_2_preflight_h10.py" --root .
if ($LASTEXITCODE -ne 0) { throw 'Fallo inspeccion H10' }
```

**El preflight solo lee los archivos `.py`/`.ps1` de H10**, imprime SHA-256 y líneas que usan `simulationStep`, `.on_step`, `traci.start` y `python`. Comparte esta salida si necesitas comandos ajustados exactamente a tu ejecutor. No intenta activar ninguna simulación.

## 2. Primera corrida recomendable: prueba corta nominal independiente

Usa un archivo `.sumocfg` del piloto H07 que YA sabes que funciona y un directorio de salida NUEVO. Esta prueba permite confirmar disponibilidad de todas las APIs con el SUMO/TraCI instalado en tu PC. NO es una simulación H10 ni demuestra invariancia de los experimentos pasados.

```powershell
python "$h11\h11_2_demo_nominal.py" --root . --steps 20 --seed 101 `
  --cfg '.\resultados\ntvc_vine_r_07_hangzhou_piloto\hangzhou_vine_sin_additional.sumocfg' `
  --out '.\resultados\h11_2_smoke_nominal_101_001'

if ($LASTEXITCODE -ne 0) { throw 'Fallo prueba nominal H11.2' }

$tele = '.\resultados\h11_2_smoke_nominal_101_001\telemetria'
python "$h11\h11_2_validar.py" --telemetria $tele --expected-steps 20
python "$h11\h11_2_resumir.py" --telemetria $tele --guardar
```

Para repetir la prueba usa `h11_2_smoke_nominal_101_002`, etc., porque H11.2 se niega a sobrescribir resultados existentes. Si la ruta `.sumocfg` difiere de la tuya, utiliza la ruta correcta **sin alterar el archivo original**.

## 3. Integración con H10: dos métodos, no usar ambos a la vez

### Método A (preferido al tener el ejecutor real): hook explícito de 3 líneas

En **una copia nueva** del ejecutor H10 Python, sin modificar ni sobrescribir `H10_Vine_H09_Imprudencia_v112`, inicializar al comienzo de la ejecución una instancia:

```python
from h11_2_observador_pasivo import PassiveObserver
obs_h11 = PassiveObserver(r"C:\Proyecto_Tesis_Final_V1\revision_naturalista\resultados\h11_2_h10_nuevo\telemetria", condition='hibrido_contextual', seed=101, vine_ids=ids_vine, h09_ids=ids_h09)
```

Después de la llamada `traci.simulationStep()` de H10, una vez por paso, añadir:

```python
obs_h11.on_step(traci)
```

Al cerrar la simulación, preferiblemente con `try/finally`, ejecutar `obs_h11.close()` **antes de cerrar la sesión TraCI**. No añadir un segundo `simulationStep()`. Los nombres `ids_vine` y `ids_h09` son las listas **reales** seleccionadas por H10 (no las totales del informe), de modo que se clasifican `both`, `vine_only`, `h09_only`, `neither`.

### Método B: enganchar H10 sin editar scripts, mediante runpy

El archivo `h11_2_ejecutar_h10.py` instala temporalmente el observador sobre `traci.simulationStep()` y luego llama al **script Python** H10 que tú le indiques; `h11_2_bootstrap.py` elimina el enganche al salir. Conserva exactamente el `simulationStep` de H10: **no añade pasos**.

**NOTA:** El ejecutor H10 original no fue adjuntado y no sabemos sus flags exactos. No uses los siguientes nombres de flags como suposición ni pases rutas históricas v111/v112: hay que inspeccionar tu runner primero. Forma del comando:

```powershell
python "$h11\h11_2_ejecutar_h10.py" --root . `
  --runner '.\H10_Vine_H09_Imprudencia_v112\scripts\ARCHIVO_REAL.py' `
  --condition hibrido_contextual --seed 101 `
  --vine-ids '.\RUTA_NUEVA\ids_vine.txt' `
  --h09-ids '.\RUTA_NUEVA\ids_h09.txt' -- `
  ARGUMENTOS_REALES_H10_QUE_GENERAN_SALIDA_NUEVA
```

Este bloque es una **plantilla**, no debe ejecutarse tal como está. Para poder completar la línea exacta, utiliza la salida del preflight y la línea real `python ...` contenida en `ejecutar_piloto_h10_v112.ps1`. Si no tienes roster de IDs exactos, omite `--vine-ids` y `--h09-ids`: el observador los marcará `unclassified`, evitando atribuciones falsas. Si el runner abre un subproceso Python separado para SUMO, este método no lo intercepta y debes usar el método A dentro del subproceso que realmente llama TraCI.

**Control importante:** el puente NO reconfigura H10. El script H10 continúa gobernando red, rutas, semilla, condiciones y ruta de salida; verifica que apunte a una carpeta nueva antes de ejecutarlo. Si el runner se niega a repetir condiciones ya ejecutadas es comportamiento correcto de H10.

## 4. Datos generados por corrida (cada instante 0.5 s)

| Archivo | Qué contiene | Advertencia |
|---|---|---|
| `trayectorias_h11.csv` | Posición, velocidad, aceleración observada, jerk aproximado, velocidad límite de carril, líder, gap, headway, TTC, próximo TLS, carril de salida candidato | `headway` y `TTC` solo cuando hay líder y datos suficientes. `speed_limit` corresponde al carril, no sustituye el límite legal verificado. |
| `eventos_semaforicos_h11.csv` | Primera observación por episodio/color, proxy de cruce, estado anterior y actual, distancia y frenado requerido | Cruces proxy, no infracciones legales confirmadas. Ámbar no es necesariamente ilegal. `unknown` es una categoría deliberada. |
| `eventos_interseccion_h11.csv` | Detenciones sostenidas en carriles internos e indicios en carril siguiente | **NO demuestra gridlock**, no verifica flujos transversalmente bloqueados. |
| `seguridad_h11.csv` | Recuento e IDs de vehículos con colisión, teleport o frenada de emergencia por paso, si TraCI los soporta | Valor ausente se conserva vacío, no se inventa cero. |
| `manifest_h11_2.json` | SHA-256, pasos, metadatos, indicadores de datos faltantes | No implica validación para Quito. |

## 5. Validez: criterios antes de aceptar como H11.2 integrado

1. El auditor H11.2 supera las pruebas unitarias.
2. La prueba nominal `--steps 20` devuelve 20 pasos y validación SHA sin modificar archivos previos.
3. El preflight identifica el script Python real que ejecuta el ciclo `traci.simulationStep()` de H10.
4. Una **nueva** condición H10 instrumentada registra 600 pasos/300 s (o el horizonte nominal declarado) con manifiesto y sin errores de telemetría esenciales.
5. El runner instrumentado y el no instrumentado deben ejecutarse con **idénticos** archivos de entrada, semilla y políticas; las salidas del tráfico originales deben permanecer idénticas byte a byte o reconciliarse con métricas equivalentes si existen campos no físicos de metadatos. Para comparar dos CSV idénticamente estructurados:

```powershell
python "$h11\h11_2_comparar_invariancia.py" `
  --original '.\resultados\CONDICION_SIN_OBSERVADOR_NUEVA\trafico_hito10.csv' `
  --nuevo '.\resultados\CONDICION_CON_OBSERVADOR_NUEVA\trafico_hito10.csv'
```

6. Los eventos de rojo, ámbar y gridlock siguen etiquetados como `proxy` o `indeterminado` cuando la telemetría no permite confirmar el fenómeno.
7. La correspondencia efectiva Vine/H09 se determina por **IDs fuente de verdad**; el registro `cohort=unclassified` no se interpreta como ausencia de imprudencia.

## 6. Qué enviar para cerrar esta etapa

**Primero:** salida de `unittest`, `h11_2_preflight_h10.py` y de `h11_2_demo_nominal.py` / `h11_2_validar.py` (20 pasos). Después, podremos definir el comando H10 integrado exacto según tus scripts reales sin inventar rutas ni flags.

**NO usar H11.2 para maximizar infracciones, colisiones o congestión**. Nuestro criterio es medir conductas reproducibles y verificar, después, fidelidad frente a Quito.
