# H09 v1.5 -- lanzador mínimo compatible con Windows PowerShell 5.1.
# Ejecuta 20 observaciones nuevas para medir oportunidades en misma base instrumental.
$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$script = Join-Path $root 'H09_Quito_Sensibilidad_v15\scripts\ejecutar_h09_v15.py'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Falta archivo: $script" }
python $script --root $root --ejecutar-corridas --ack ENTIENDO_EXPERIMENTO_EXPLORATORIO_NO_CALIBRADO
if ($LASTEXITCODE -ne 0) { throw "H09 v1.5 se detuvo: revise el error; no borre resultados existentes" }
Write-Host 'H09 v1.5: corridas e informe de oportunidades completados'
