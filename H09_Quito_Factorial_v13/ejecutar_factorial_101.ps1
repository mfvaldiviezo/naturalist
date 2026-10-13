# H09 v1.3: 3 corridas adicionales sobre la semilla 101 existente.
# Este script no toca ni elimina los resultados v1.2: las salidas se crean nuevas.
# Compatible con Windows PowerShell 5.1 y PowerShell 7; sin elevacion necesaria.
$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$package = Join-Path $root 'H09_Quito_Factorial_v13'
$v12 = Join-Path $root 'H09_Quito_Perfiles_Contextuales_v12'
$runner = Join-Path $v12 'scripts\piloto_perfiles_h09_v12.py'
$cmp = Join-Path $package 'scripts\comparar_factorial_h09_v13.py'
$sumocfg = Join-Path $root 'resultados\ntvc_vine_r_07_hangzhou_piloto\hangzhou_vine_sin_additional.sumocfg'
$zones = Join-Path $root 'resultados\h09_zonas_velocidad_generadas_v11.json'
$instrument = Join-Path $root 'H09_Quito_Instrumentacion_v11\scripts'
$outroot = Join-Path $root 'resultados\h09_v12_piloto_101'

foreach ($required in @($runner,$cmp,$sumocfg,$zones)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Archivo requerido inexistente: $required" }
}
if (-not (Test-Path -LiteralPath $instrument -PathType Container)) {throw "Observador no disponible: $instrument"}
foreach ($existing in @('baseline','probe','active_15_semaforos','active_15_combinado')) {
    $manifest = Join-Path (Join-Path $outroot $existing) 'manifest_H09.json'
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {throw "Falta resultado previo: $manifest"}
}

# Preflight para evitar ejecuciones parciales por carpetas preexistentes.
foreach ($n in @('placebo','velocidad','semaforos_velocidad')) {
    $dest = Join-Path $outroot "active_15_$n"
    if (Test-Path -LiteralPath $dest) {throw "La salida ya existe (no sobrescribir): $dest"}
}
$reportprefix = Join-Path $outroot 'factorial_semaforos_velocidad_101'
if ((Test-Path "$reportprefix.csv") -or (Test-Path "$reportprefix.json")) {throw 'El informe factorial ya existe'}

$common = @('--sumocfg',$sumocfg,'--seed','101','--pasos','600','--step-length','0.5',
  '--sites','B1,B2,C1','--zonas-velocidad',$zones,'--instrument-dir',$instrument,
  '--modo','active','--porcentaje','15','--familia','combinado',
  '--ack-active','ESCENARIO_EXPLORATORIO_NO_CALIBRADO')

foreach ($name in @('placebo','velocidad','semaforos_velocidad')) {
    $config = Join-Path $package "config\perfil_$name.json"
    if (-not (Test-Path -LiteralPath $config)) {throw "Configuracion faltante: $config"}
    $dest = Join-Path $outroot "active_15_$name"
    Write-Host "`n=== FACTORIAL H09: $name ==="
    python $runner @common --config-perfiles $config --output $dest
    if ($LASTEXITCODE -ne 0) {throw "Fallo SUMO en escenario $name; conservar carpeta para diagnostico"}
}

Write-Host "`n=== COMPARACION FACTORIAL CON HASHES Y COHORTE ==="
python $cmp --root $outroot --output-prefix $reportprefix
if ($LASTEXITCODE -ne 0) {throw 'Fallo auditoria factorial; conservar todas las corridas'}
Write-Host "`nFACTORIAL LISTO: $reportprefix.csv"
