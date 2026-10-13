#requires -Version 5.1
param(
    [switch]$Ejecutar,
    [string]$VineScripts = '',
    [string]$ReferenceBaselineDir = '',
    [string]$DataDir = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'scripts\piloto_hibrido_h10.py'
if (!(Test-Path $runner)) { throw "Falta ejecutor: $runner" }
$argv = @($runner, '--root', $root)
if ($VineScripts) { $argv += @('--vine-scripts', $VineScripts) }
if ($ReferenceBaselineDir) { $argv += @('--reference-baseline-dir', $ReferenceBaselineDir) }
if ($DataDir) { $argv += @('--data-dir', $DataDir) }
if ($Ejecutar) {
  $argv += @('--ejecutar', '--ack-active', 'EXPERIMENTAL_ONLY', '--ack-time-scale', 'NOT_CALIBRATED')
}
python @argv
if ($LASTEXITCODE -ne 0) { throw "H10 v1.1.2 falló (exit code $LASTEXITCODE). NO sobrescribe las salidas existentes." }
