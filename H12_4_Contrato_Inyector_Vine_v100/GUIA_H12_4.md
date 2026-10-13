# H12.4 — Contrato de `FixedRosterInjector`, sin ejecución

**Objetivo:** aprovechar el inyector H08b ya localizado, inspeccionando exactamente su firma, dependencias y llamadas a TraCI antes de conectarlo a H12.2. No reconstruye Vine ni modifica los datos.

## Ruta que ya confirmó H12.3

`C:\Proyecto_Tesis_Final_V1\revision_naturalista\scripts\ntvc_vine_r_08b_cuota_auditada.py`

## Ejecutar en PowerShell (tsc-env)

Descomprime `H12_4_Contrato_Inyector_Vine_v100.zip` dentro de `revision_naturalista`.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h124 = '.\H12_4_Contrato_Inyector_Vine_v100'
python -m unittest discover -s "$h124\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Pruebas H12.4 fallaron' }
python "$h124\h12_4_inspeccionar.py" --revision-root .
if ($LASTEXITCODE -ne 0) { throw 'Preflight H12.4 falló' }
python "$h124\h12_4_inspeccionar.py" --revision-root . --guardar
if ($LASTEXITCODE -ne 0) { throw 'H12.4 falló' }
```

El preflight no escribe archivos. `--guardar` crea **únicamente** una carpeta nueva en `revision_naturalista\resultados\h12_4_interfaz_*` con `interfaz_h08b.json` y `dictamen_interfaz_h12_4.md`.

## Envíame el contrato de interfaz

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_4_interfaz_*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_interfaz_h12_4.md')
```

Si el informe no contiene los valores predeterminados necesarios, adjunta **solo** `interfaz_h08b.json` (describe firmas AST y llamadas; no contiene dataset). Con esto diseñaremos una factoría fiel al H08b, y una prueba `probe` con cero comandos antes de cualquier ensayo `active`.

## Límites

- Solo analiza archivos `.py` de código de la revisión y nombres de scripts vecinos; no ejecuta/importa módulos H08b, no analiza datos POLIDriving.
- No prueba equivalencia cinemática ni puede certificar que un hook externo no produzca efectos colaterales por métodos dinámicos.
- No inicia SUMO ni carga checkpoints. La integración `probe/active` sigue pendiente.
