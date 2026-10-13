# H12.18 v1.0.3 — Registro de módulo para introspección PyTorch Geometric

## Problema localizado

H12.18 v1.0.2 pasó `plan`, pero `deps` detuvo el forward con:

```
KeyError 'h12_18_upstream_architecture_isolated'
```

**Causa identificada:** el cargador v1.0.2 ejecutaba el AST de las cuatro clases originales en un diccionario con `__name__='h12_18_upstream_architecture_isolated'`, pero sin registrar un objeto módulo en `sys.modules`. PyTorch Geometric, al inspeccionar la subclase de `MessagePassing`, consulta `sys.modules[cls.__module__]` y produce un `KeyError` cuando no existe ese nombre. La validación estática del preflight (`plan`) y la procedencia Git permanecían correctas.

## Corrección v1.0.3

Se crea un objeto `types.ModuleType` con ese nombre, se registra en `sys.modules` **antes** de definir las clases, y se ejecuta el AST original en el diccionario del módulo registrado. El cargador:

1. Rechaza sobrescribir un módulo homónimo ya presente.
2. Comprueba que están presentes las cuatro clases originales y que `__module__` corresponde al módulo aislado.
3. Elimina el módulo que acaba de crear si falla la compilación, la inspección o la ejecución.
4. Conserva los controles **del commit y blob originales, worktree limpio y SHA-256** de H12.18 v1.0.2; no modifica LibSignal.
5. No importa `agent/__init__.py`, `world`, `cityflow`, ni ejecuta entrenamientos; `shadow` sigue sin actuar con las propuestas neuronales.

**Pruebas:** 69 tests offline `unittest` aprobados, incluidos casos sintéticos que reproducen la consulta de PyG a `sys.modules`. No se ha ejecutado el forward real de LibSignal/PyG en Windows hasta que el usuario repita `deps`.

## Ejecución (PowerShell, entorno aislado colight-pyg)

Extrae el ZIP completo dentro de `C:\Proyecto_Tesis_Final_V1\revision_naturalista`, dejando intactos v100 y v101.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate colight-pyg

$h1218 = '.\H12_18_Bridge_CoLight_LibSignal_v103'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
$lib = (Resolve-Path '.\externos_h12_16\LibSignal').Path
$h1217run = Get-Item '.\resultados\h12_17_multi_tls_20261012_182005_185768_19e1d1'
$h1216run = Get-ChildItem '.\resultados' -Directory -Filter 'h12_16_colight_*' |
  Where-Object { Test-Path (Join-Path $_.FullName 'dictamen_h12_16.json') } |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $h1216run) { throw 'No se encontro H12.16' }

python -m unittest discover -s "$h1218\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Pruebas H12.18 v103 fallaron' }

$h18args = @(
  '--repo-root', "$repo",
  '--revision-root', (Get-Location).Path,
  '--h1216-dir', "$($h1216run.FullName)",
  '--h1217-dir', "$($h1217run.FullName)",
  '--libsignal-dir', "$lib"
)

python "$h1218\h12_18_bridge.py" @h18args --mode plan
if ($LASTEXITCODE -ne 0) { throw 'Preflight H12.18 v103 bloqueado' }

python "$h1218\h12_18_bridge.py" @h18args --mode deps
if ($LASTEXITCODE -ne 0) { throw 'Forward original LibSignal NO acreditado; no ejecutar shadow' }
```

Resultados buscados: **69 pruebas OK**, `H12_18_PLAN_OK`, `H12_18_DEPENDENCIES_AND_FORWARD_OK`. Solo el último acredita el forward real del `ColightNet` con pesos aleatorios. Si falla, conservar error completo.

**Solo después de aprobar deps** se permite piloto SUMO `shadow` (12 decisiones, semilla 101, 12 semáforos):

```powershell
python "$h1218\h12_18_bridge.py" @h18args `
  --mode shadow `
  --seed 101 `
  --rl-steps 12 `
  --min-green 10 `
  --ack-online-control MULTI_TLS_TEST_POLICY `
  --ack-shadow-model UNTRAINED_SHADOW_NEVER_ACTUATE
if ($LASTEXITCODE -ne 0) { throw 'Shadow H12.18 no acreditado' }
```

En `shadow`, la red neuronal con pesos aleatorios **solo observa**, mientras SUMO continúa ejecutando exclusivamente la política H12.17. No se certifican checkpoints, entrenamiento, calidad, SOTA reproducido, ni resiliencia Vine/H09.

## Diagnóstico opcional de fallo

Si `deps` vuelve a fallar, repite **solo** ese modo para ver la traza completa, sin ejecutar `shadow`:

```powershell
$env:H1218_TRACEBACK = '1'
python "$h1218\h12_18_bridge.py" @h18args --mode deps
Remove-Item Env:H1218_TRACEBACK -ErrorAction SilentlyContinue
```

El modo `deps` no inicia SUMO, no instala dependencias y no modifica archivos originales. Conserva la traza para depurar una eventual incompatibilidad adicional con PyG.

## Registro metodológico

- H12.18 v1.0.1 presentaba una comparación de blob Git vs worktree sensible a CRLF. v1.0.2 la corrigió; v1.0.3 mantiene esa corrección y registra el módulo para introspección de PyG.
- Los commits/blobs se verifican con Git local; no se hacen llamadas a red durante `plan` o `deps`.
- El forward se ejecutará con pesos aleatorios en CPU, aunque la GPU GTX 1050 esté disponible; no se certifica rendimiento ni compatibilidad CUDA del entrenamiento.
- La extracción AST de clases originales no reproduce `CoLightAgent` ni el entrenador íntegro de LibSignal, ni acredita la semántica de sus observaciones y recompensas.
- Sin `H12_18_DEPENDENCIES_AND_FORWARD_OK` no ejecutar el modo `shadow`.
