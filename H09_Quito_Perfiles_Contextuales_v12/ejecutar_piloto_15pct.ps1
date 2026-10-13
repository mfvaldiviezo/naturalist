# H09 v1.2 - Piloto controlado: baseline / probe / active 15 %.
# Ejecutar desde C:\Proyecto_Tesis_Final_V1\revision_naturalista con tsc-env activo.
$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$pkg = Join-Path $root 'H09_Quito_Perfiles_Contextuales_v12'
$script = Join-Path $pkg 'scripts\piloto_perfiles_h09_v12.py'
$cmp = Join-Path $pkg 'scripts\analizar_comparacion_h09_v12.py'
$cfg = Join-Path $root 'resultados\ntvc_vine_r_07_hangzhou_piloto\hangzhou_vine_sin_additional.sumocfg'
$zones = Join-Path $root 'resultados\h09_zonas_velocidad_generadas_v11.json'
$instrument = Join-Path $root 'H09_Quito_Instrumentacion_v11\scripts'
$outroot = Join-Path $root 'resultados\h09_v12_piloto_101'
$baseline = Join-Path $outroot 'baseline'
$probe = Join-Path $outroot 'probe'
$active = Join-Path $outroot 'active_15_combinado'
$report = Join-Path $outroot 'comparacion_descriptiva.csv'
foreach ($f in @($script,$cmp,$cfg,$zones,(Join-Path $instrument 'observador_traci_h09_v11.py'))) {
    if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { throw "Archivo necesario no encontrado: $f" }
}
foreach ($p in @($baseline,$probe,$active,$report)) {
    if (Test-Path -LiteralPath $p) { throw "No sobreescribir resultados previos: $p" }
}
New-Item -ItemType Directory -Path $outroot -Force | Out-Null
$common = @('--sumocfg',$cfg,'--seed','101','--pasos','600','--step-length','0.5',
            '--sites','B1,B2,C1','--zonas-velocidad',$zones,'--instrument-dir',$instrument)
Write-Host '=== H09 BASELINE v1.2 (sin intervención) ==='
python $script @common --modo baseline --porcentaje 0 --output $baseline
if ($LASTEXITCODE -ne 0) { throw 'Fallo BASELINE. No continuar.' }
Write-Host '=== H09 PROBE v1.2 (sin intervención) ==='
python $script @common --modo probe --porcentaje 0 --output $probe
if ($LASTEXITCODE -ne 0) { throw 'Fallo PROBE. No continuar.' }
Write-Host '=== H09 ACTIVE 15 % perfil persistente EXPLORATORIO ==='
python $script @common --modo active --porcentaje 15 --familia combinado `
    --ack-active 'ESCENARIO_EXPLORATORIO_NO_CALIBRADO' --output $active
if ($LASTEXITCODE -ne 0) { throw 'Fallo ACTIVE. No continuar.' }
Write-Host '=== H09 AUDITORÍA COMPARATIVA ==='
python $cmp --directorios $baseline $probe $active --salida-csv $report
if ($LASTEXITCODE -ne 0) { throw 'Fallo comparación descriptiva o probe no idéntico.' }
Write-Host "H09 PILOTO TERMINADO. Resultados: $outroot"
Write-Host 'NO ES CALIBRACIÓN DE PROBABILIDADES INDIVIDUALES DE QUITO.'
