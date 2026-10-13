# H09 v1.4.3: reanudar semilla 102 conservada y ejecutar solo faltantes; nunca sobrescribir.
# Requiere proyecto H09 v1.2, v1.3 y observador v1.1. Ninguna sobreescritura.
$ErrorActionPreference='Stop'
# Windows PowerShell 5.1: validacion Python en fichero, no python -c con comillas
$root=(Get-Location).Path
$pkg=Join-Path $root 'H09_Quito_Multisemilla_v143'
$v12=Join-Path $root 'H09_Quito_Perfiles_Contextuales_v12'
$v13=Join-Path $root 'H09_Quito_Factorial_v13'
$runner=Join-Path $v12 'scripts\piloto_perfiles_h09_v12.py'
$comparator=Join-Path $pkg 'scripts\comparar_factorial_h09_v143.py'
$aggregator=Join-Path $pkg 'scripts\comparar_multisemilla_h09_v143.py'
$validator=Join-Path $pkg 'scripts\auditar_semilla_h09_v143.py'
$cfg=Join-Path $root 'resultados\ntvc_vine_r_07_hangzhou_piloto\hangzhou_vine_sin_additional.sumocfg'
$zones=Join-Path $root 'resultados\h09_zonas_velocidad_generadas_v11.json'
$observer=Join-Path $root 'H09_Quito_Instrumentacion_v11\scripts'
$old101=Join-Path $root 'resultados\h09_v12_piloto_101'
$outroot=Join-Path $root 'resultados\h09_v14_multisemilla'
$seeds=@(102,103,104,105)
$common=@('--sumocfg',$cfg,'--pasos','600','--step-length','0.5','--sites','B1,B2,C1',
          '--zonas-velocidad',$zones,'--instrument-dir',$observer)
$conditions=@(
  @{Label='baseline'; Mode='baseline'; Profile=''; Family='combinado'; Pct=0},
  @{Label='probe'; Mode='probe'; Profile=''; Family='combinado'; Pct=0},
  @{Label='active_15_placebo'; Mode='active'; Profile=(Join-Path $v13 'config\perfil_placebo.json'); Family='combinado'; Pct=15},
  @{Label='active_15_semaforos'; Mode='active'; Profile=''; Family='semaforos'; Pct=15},
  @{Label='active_15_velocidad'; Mode='active'; Profile=(Join-Path $v13 'config\perfil_velocidad.json'); Family='combinado'; Pct=15},
  @{Label='active_15_semaforos_velocidad'; Mode='active'; Profile=(Join-Path $v13 'config\perfil_semaforos_velocidad.json'); Family='combinado'; Pct=15},
  @{Label='active_15_combinado'; Mode='active'; Profile=''; Family='combinado'; Pct=15}
)
foreach($fp in @($runner,$comparator,$aggregator,$validator,$cfg,$zones,
                  (Join-Path $v13 'config\perfil_placebo.json'),
                  (Join-Path $v13 'config\perfil_velocidad.json'),
                  (Join-Path $v13 'config\perfil_semaforos_velocidad.json'))){
  if(-not (Test-Path -LiteralPath $fp -PathType Leaf)){throw "Falta archivo: $fp"}
}
if(-not (Test-Path -LiteralPath $observer -PathType Container)){throw "Falta observador: $observer"}
foreach($name in @('baseline','probe','active_15_placebo','active_15_semaforos',
                   'active_15_velocidad','active_15_semaforos_velocidad','active_15_combinado')){
  if(-not (Test-Path (Join-Path (Join-Path $old101 $name) 'manifest_H09.json'))){throw "Falta corrida original semilla 101: $name"}
}
# REANUDABLE: comprobar cada salida previa antes de decidir si conservarla.
# Nunca reescribir resultados. Si existe una carpeta incompleta o alterada, fallar cerrado.
foreach($seed in $seeds){
  $d=Join-Path $outroot "seed_$seed"
  foreach($c in $conditions){
    $dest=Join-Path $d $c.Label
    if(Test-Path -LiteralPath $dest){
      python $validator --comparador $comparator --root $d --seed $seed --label $c.Label
      if($LASTEXITCODE -ne 0){throw "Corrida previa no valida, revisar sin borrar: $dest"}
    }
  }
}
$prefix=Join-Path $outroot 'h09_multisemilla_101_105'
foreach($ext in @('.json','_por_semilla.csv','_contrastes.csv','_interacciones.csv','_resumen.csv')){
  if(Test-Path "$prefix$ext"){throw "Informe existente: $prefix$ext"}
}
# La validación de v1.3 de la semilla 101 precede a las nuevas ejecuciones.
Write-Host 'AUDITORIA PREVIA seed 101 (sin ejecutar SUMO)...'
python $validator --comparador $comparator --root $old101 --seed 101
if($LASTEXITCODE -ne 0){throw 'Semilla 101 no aprobó revisión'}
foreach($seed in $seeds){
  $d=Join-Path $outroot "seed_$seed"
  if(-not (Test-Path -LiteralPath $d)){
    New-Item -ItemType Directory -Path $d | Out-Null
  }
  foreach($c in $conditions){
    $dest=Join-Path $d $c.Label
    if(Test-Path -LiteralPath $dest){
      Write-Host "REUTILIZANDO seed=$seed escenario=$($c.Label) (previamente auditado)"
      continue
    }
    $argsRun=$common+@('--seed',[string]$seed,'--modo',$c.Mode,
      '--porcentaje',[string]$c.Pct,'--familia',$c.Family,'--output',$dest)
    if($c.Mode -eq 'active'){
      $argsRun+=@('--ack-active','ESCENARIO_EXPLORATORIO_NO_CALIBRADO')
    }
    if($c.Profile){$argsRun+=@('--config-perfiles',$c.Profile)}
    Write-Host "`n=== H09 seed=$seed escenario=$($c.Label) ==="
    python $runner @argsRun
    if($LASTEXITCODE -ne 0){throw "Falló SUMO $seed $($c.Label). Conservar el resultado para diagnóstico."}
  }
  # Revalidar cada semilla antes de iniciar la siguiente.
  python $validator --comparador $comparator --root $d --seed $seed
  if($LASTEXITCODE -ne 0){throw "La auditoría seed $seed falló. No continuar."}
}
python $aggregator --seed101-root $old101 --multiseed-root $outroot `
  --additional-seeds '102,103,104,105' --comparador-v13 $comparator --output-prefix $prefix
if($LASTEXITCODE -ne 0){throw 'Agregado multisemilla falló'}
Write-Host "`nMULTISEMILLA COMPLETO: $prefix.json"
