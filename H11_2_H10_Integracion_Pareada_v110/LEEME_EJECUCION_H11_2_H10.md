# H11.2 — Integración pareada del observador pasivo con H10 v1.1.2

**Estado:** paquete de ejecución preparado y comprobado con pruebas unitarias/fixtures. **No** se ha ejecutado en el ordenador del usuario ni se ha demostrado todavía invariancia H10+H11.2 en SUMO real.

## Hallazgo confirmado del preflight

El archivo `H10_Vine_H09_Imprudencia_v112/scripts/piloto_hibrido_h10.py` del archivo H10 original disponible tiene **SHA-256** `42a6fb5674307560688164c5ebbe7f06160a5df55b58c8fb021e1daac6211e7b`, igual que el informado en PowerShell. Se verificó que:

- `traci.simulationStep()` ocurre en la línea 222 de `step_once()`.
- El observador H09 ya existe dentro de H10, justo después del avance.
- `injector.on_step(traci, step)` ocurre en la línea 235, **sin avanzar SUMO**.
- `run_one(label, ctx, args)` puede invocarse reutilizando el núcleo original. Se crean escenarios nominal, vine_protegido, vine_contextual, h09, hibrido_protegido, hibrido_contextual.
- H10 fija rutas históricas y hace verificaciones de SHA; por lo tanto, ejecutar su CLI original no es la forma correcta de hacer la comparación H11.2, porque puede intentar *reutilizar* resultados ya cerrados.

## Solución implementada

`h11_2_integrar_y_comparar_h10.py` **importa la copia ORIGINAL de H10 sin editarla**, pasa por el `prepare()` original con verificaciones de hash y ejecuta `run_one()` con `p['out']` redirigido a una ubicación *nueva* dentro de `resultados/`. **No llama a `inspect_previous` ni reutiliza salidas pasadas**.

Para un escenario, lanza dos **procesos Python independientes**:

1. **control**: H10 original, sin observador H11.2.
2. **observado**: el MISMO H10 original con enganche pasivo sobre la llamada a `traci.simulationStep()`.

El observador se ejecuta una sola vez **después** de avanzar SUMO y **antes** del observador H09 y de Vine del paso; consulta TraCI y nunca emite setters. Se pasan las listas de IDs verdaderamente seleccionados desde `ctx[11]` y **solo** las cohortes activadas para el modo correspondiente. No se redefinen las cohortes H10.

Cada brazo escribe su manifiesto H10 original y, en el observado, se añade la telemetría H11.2. Al terminar, se contrastan **byte por byte** `trafico_h09.csv`, `eventos_h09.csv`, `cohortes_h10.csv`, `cohorte_h09.csv`, `exposicion_h09.csv` y los otros CSV originales presentes, tras verificar sus hashes contra los manifiestos H10. La comparación falla cerrada si faltan archivos esenciales, los metadatos no coinciden o cambia cualquier salida comparada. **Los manifiestos de las dos corridas NO se comparan byte a byte**, pues contienen rutas de salida diferentes.

Un éxito prueba la **invariancia de los archivos comparados** bajo la semilla, las entradas y el horizonte elegidos, no certifica la representatividad de Quito ni la ausencia de cambios en variables no observadas.

## Instalación

Descomprime el paquete en:

`C:\Proyecto_Tesis_Final_V1\revision_naturalista`

Debe quedar la carpeta `H11_2_H10_Integracion_Pareada_v110` directamente en la raíz. No sobrescribir ni mover H10 o H11.2 v100.

### Paso 1: pruebas unitarias (NO se abre SUMO)

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h11p = '.\H11_2_H10_Integracion_Pareada_v110'
python -m unittest discover -s "$h11p\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron pruebas H11.2 integracion pareada' }
```

### Paso 2: preflight de solo lectura (NO se abre SUMO)

```powershell
python "$h11p\h11_2_integrar_y_comparar_h10.py" --root . --escenario nominal
if ($LASTEXITCODE -ne 0) { throw 'Fallo preflight H10-integracion' }
```

### Paso 3: primer ensayo H10 pareado NOMINAL

**Este comando sí ejecuta dos simulaciones nuevas** de 600 pasos/300 segundos con la semilla 101:

```powershell
python "$h11p\h11_2_integrar_y_comparar_h10.py" --root . --escenario nominal `
  --ejecutar --ack-active EXPERIMENTAL_ONLY --ack-time-scale NOT_CALIBRATED
if ($LASTEXITCODE -ne 0) { throw 'No quedo demostrada invariancia nominal H11.2' }
```

Si H10 necesita flags de origen, admite `--vine-scripts`, `--reference-baseline-dir`, `--data-dir` y `--sumo-binary`, como H10 original. Por defecto usa las rutas y los requisitos originales y falla ante ambigüedad.

### Paso 4: probar el escenario híbrido SOLO si superó el nominal

**Este comando también ejecuta dos simulaciones nuevas** y podría tardar más que el nominal al añadir Vine y los perfiles H09.

```powershell
python "$h11p\h11_2_integrar_y_comparar_h10.py" --root . --escenario hibrido_contextual `
  --ejecutar --ack-active EXPERIMENTAL_ONLY --ack-time-scale NOT_CALIBRATED
if ($LASTEXITCODE -ne 0) { throw 'No quedo demostrada invariancia hibrida H11.2' }
```

## Salidas generadas

Una carpeta **nueva en cada ejecución**, por ejemplo:

```
resultados/h11_2_pareado_h10_nominal_YYYYMMDD_HHMMSS_microsegundos/
├── control/
│   ├── h11_2_brazo.json
│   └── nominal/ (CSV y manifest_h10.json originales)
├── observado/
│   ├── h11_2_brazo.json
│   ├── nominal/ (CSV y manifest_h10.json originales)
│   └── telemetria/
│       ├── trayectorias_h11.csv
│       ├── eventos_semaforicos_h11.csv
│       ├── eventos_interseccion_h11.csv
│       ├── seguridad_h11.csv
│       └── manifest_h11_2.json
└── comparacion_h11_2.json
```

Si una corrida falla o la invariancia no se demuestra, **se conserva íntegra su carpeta parcial**; no se borra ni se reintenta escribiendo en la misma. La herramienta sale con error y muestra el motivo.

## Limitaciones técnicas y científicas

- El H10 original contiene `speedMode=31` para Vine; no se altera aquí. Las reglas H09 siguen siendo exploratorias.
- `observado` produce datos adicionales, **no controladores RL** ni datos de campo.
- Conteos de `cruce rojo` H09 pueden no coincidir exactamente con proxies H11.2: sus definiciones/ventanas no son idénticas.
- El instrumento de detenciones en carriles internos **no certifica gridlock**.
- Una ausencia de fallas estructurales no valida las probabilidades de conducción imprudente para Quito.
- La cohorte nominal H10 no está sometida a Vine/H09, por lo que la etiqueta del observador será `unclassified`, no una imputación de imprudencia.
- Los archivos `manifest_h10.json` incluyen comandos SUMO con prefijos de salida propios y por eso **no deben** compararse como si fueran tráfico.

**Qué compartir:** salida de las 11 pruebas, preflight, estado final de la comparación nominal e híbrida, y `comparacion_h11_2.json` si aparece. No se debe dar por cerrada H11.2 hasta que pasen las dos comparaciones de invariancia.
