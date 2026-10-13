# H12 — Auditoría de Gymnasium, SOTA y compatibilidad de experimentos

**Versión 1.0.0. No es un runner experimental. SOLO LECTURA (excepto generación de informes nuevos cuando se añade `--guardar`).**

## Qué detectó la auditoría preliminar de GitHub

Repositorio original: <https://github.com/mfvaldiviezo/framework_RLT>, rama `main`, árbol observado: `fe124c599104f8a4ef8b1fa7b41a92a7da77c646`.

- `tsc_framework/src/core/tsc_env.py`: `TSCEnv(gym.Env)`, `reset` y `step` con API Gymnasium. Observación 34D y cuatro acciones (según docstring y código); el control RL avanza con `for _ in range(self.delta_t): traci.simulationStep()`.
- `tsc_framework/scripts/run_evaluation.py`: `FixedAgent`, `MaxPressureAgent`, y `CoLightAgent`; el último **no es CoLight original**, sino heurística de colas por fase, softmax y argmax. Citarlo como CoLight SOTA sería metodológicamente incorrecto.
- `run_resco.py`: alias `colight` -> `CoSLight` de RESCO, **no equivalente** a la arquitectura CoLight original. Código de RESCO y CoordLight presente en checkout, pero eso no acredita que sus modelos hayan participado en una comparación homogénea.
- `tsc_framework/src/core/latam_chaos_manager.py` y `tsc_framework/transfer_eval_n30_robust.py`: mecanismos de bloqueo explícito mediante `traci.vehicle.setSpeed(v_id, 0.0)`.
- `tsc_framework/outputs/models/`: cuatro ZIP de modelos `ppo_ideal`, `ppo_chaos`, `ppo_coop_ideal`, `ppo_coop_chaos` presentes en GitHub; su mera existencia no acredita validez de espacio, budget de entrenamiento, sincronización ni integridad local.
- `run_all_eval.ps1`: usa el evaluador local `scripts/run_evaluation.py` con baselines `fixed maxpressure colight`; no se debe confundir esa ruta con `evaluate_marl.py`/`run_resco.py` y RESCO.

## Ejecución segura en Windows PowerShell

Extraer `H12_Auditoria_Gymnasium_SOTA_v100.zip` directamente en `C:\Proyecto_Tesis_Final_V1\revision_naturalista`. Suponemos que el checkout de GitHub está en `C:\Proyecto_Tesis_Final_V1\traffic_project`; **si está en otra carpeta, especificar la ruta correcta**. No intentar actualizar GitHub ni ejecutar `git pull` como parte de esta auditoría.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env

$h12 = '.\H12_Auditoria_Gymnasium_SOTA_v100'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'

if (!(Test-Path (Join-Path $repo 'tsc_framework\src\core\tsc_env.py'))) {
    throw "No encuentro el checkout GitHub en $repo. Corrige `$repo."
}

python -m unittest discover -s "$h12\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron pruebas H12' }

# PRE-FLIGHT SIN ESCRITURA
python "$h12\h12_auditar.py" --revision-root . --repo-root $repo
if ($LASTEXITCODE -ne 0) { throw 'Falló preflight H12' }

# EXPORTA SOLO ARCHIVOS NUEVOS EN revision_naturalista/resultados/
python "$h12\h12_auditar.py" --revision-root . --repo-root $repo --guardar
if ($LASTEXITCODE -ne 0) { throw 'Falló auditoría H12' }
```

### Posible disposición local alternativa

Si los archivos de GitHub están en `C:\Proyecto_Tesis_Final_V1` directamente y no en `traffic_project`, usar `$repo = 'C:\Proyecto_Tesis_Final_V1'` **solo si** allí están juntos `run_all_eval.ps1`, `baselines` y `tsc_framework`.

## Resultados

Se crea `resultados/h12_auditoria_YYYYMMDD_HHMMSS_micros/` con:

| Archivo | Qué verifica |
| --- | --- |
| `fuentes_codigo_h12.csv` | SHA Git local frente a los blobs de GitHub auditados; solo normaliza CRLF en memoria para comparar |
| `detecciones_estaticas_h12.csv` | Gymnasium, CoLight heurístico, alias RESCO, hard stop y runner histórico |
| `checkpoints_sota_h12.csv` | ZIP de SB3 y metadatos JSON, sin PyTorch, pickle, ni carga de modelo |
| `evidencia_h11_h12.csv` | Presencia de tres artefactos H11 nominal/híbrido/acciones y cabeceras CSV (SIN leer filas) |
| `carpetas_resultados_h12.csv` | Carpetas históricas relevantes por nombre, NO interpretadas como ejecuciones válidas |
| `puertas_evaluacion_h12.csv` | Condiciones de cierre antes de nueva batería comparativa |
| `dictamen_h12.md` | Interpretación e implicación científica para el artículo |
| `manifiesto_h12.json` | Orígenes, códigos, hashes de productos y alcance |

## Reglas de integridad y alcance

- **No abrir** PoliDriving RAW, Richard, `furious`, ni la sesión reservada de Alonso; no tocar el conjunto H01 ni sus manifiestos.
- **No** recalibrar ni reentrenar Vine, H09, PPO, MAD-Gating u otros controladores.
- **No** ejecutar SUMO/TraCI, `run_all_eval.ps1`, `run_evaluation.py`, `run_resco.py` ni `evaluate_marl.py`.
- **No** cargar checkpoints con `torch`, `PPO.load` ni `pickle`; los ZIP se inspeccionan como contenedores (JSON interno seguro de leer).
- **No** modificar archivos originales del repositorio, `resultados/` previos, ni descargar dependencias.
- La presencia de checkpoint/archivo fuente o una etiqueta de algoritmo NO acredita comparabilidad o benchmark SOTA.

## Experimento recomendado SOLO DESPUÉS de verificar las puertas

Crear una interfaz única de observación y acciones para controladores de tráfico y conectar el inyector H10 en el mismo ciclo microtemporal. Comparar nominal, Vine, H09 e híbrido sin bloqueo artificial; conservar bloqueo impuesto como factor separado, si se incluye. Las variables de respuesta son métricas de resiliencia, **no** criterios para volver la perturbación más agresiva.

**Antes de experimentar:** comprobar quién controla TLS, qué paso físico se usa (`--step-length=0.5` frente a `delta_t` Gymnasium), restauración/reset de injertos, registro de semillas y equivalencia de métricas. Realizar tests unitarios de `reset`, `step` y no doble stepping primero. Después utilizar modelos SOTA genuinos con checkpoints/condiciones verificadas.
