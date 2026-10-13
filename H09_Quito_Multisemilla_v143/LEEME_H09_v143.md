# H09 — Multisemilla v1.4.3: corrección de etiquetas del reanudador

## Problema solucionado

La v1.4.2 audita correctamente la semilla 102 completa, pero el lanzador
`ejecutar_reanudar_h09_v142.ps1` llama al auditor por nombre de carpeta,
p. ej. `--label active_15_placebo`, mientras que `read_run` sólo acepta la etiqueta
canónica `placebo`. El error era `KeyError: 'active_15_placebo'` después de
auditar baseline y probe. **No es un fallo científico ni una corrida inválida.**

La v1.4.3 normaliza las etiquetas de carpeta a los nombres del comparador:

| Carpeta | Etiqueta interna |
|---|---|
| baseline | baseline |
| probe | probe |
| active_15_placebo | placebo |
| active_15_semaforos | S |
| active_15_velocidad | V |
| active_15_semaforos_velocidad | SV |
| active_15_combinado | combinado |

La normalización se hace en el auditor y sólo permite nombres incluidos en
`RUNS`. Se conservan todos los controles de hash SHA-256, exposición, entrada
idéntica, semilla, modo y parámetros de perfil. La comparación multisemilla
sigue siendo descriptiva, **no calibración empírica de Quito**.

## Instalación, sin borrar ni sobrescribir corridas anteriores

Descargar y extraer `H09_Quito_Multisemilla_v143.zip` directamente en
`C:\Proyecto_Tesis_Final_V1\revision_naturalista`. Quedará una nueva carpeta
`H09_Quito_Multisemilla_v143`, junto a v1.4.1 y v1.4.2.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
$h143 = '.\H09_Quito_Multisemilla_v143'
python -m unittest discover -s "$h143\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron pruebas v1.4.3' }
```

## Verificación previa sin SUMO de los siete escenarios de la semilla 102

```powershell
$auditor = "$h143\scripts\auditar_semilla_h09_v143.py"
$comparador = "$h143\scripts\comparar_factorial_h09_v143.py"
$dir102 = '.\resultados\h09_v14_multisemilla\seed_102'
foreach ($label in @('baseline','probe','active_15_placebo','active_15_semaforos','active_15_velocidad','active_15_semaforos_velocidad','active_15_combinado')) {
    python $auditor --comparador $comparador --root $dir102 --seed 102 --label $label
    if ($LASTEXITCODE -ne 0) { throw "Auditoria individual fallida: $label" }
}
python $auditor --comparador $comparador --root $dir102 --seed 102
if ($LASTEXITCODE -ne 0) { throw 'Auditoria factorial 102 fallida' }
```

## Reanudar

```powershell
Unblock-File "$h143\ejecutar_reanudar_h09_v143.ps1"
& "$h143\ejecutar_reanudar_h09_v143.ps1"
```

Reutiliza los siete escenarios de 102. Si no existen resultados 103–105,
ejecuta 21 escenarios; guarda reportes nuevos en
`resultados\h09_v14_multisemilla\h09_multisemilla_101_105*.{json,csv}`.
No repite la semilla 101, no modifica Vine, H08b ni archivos originales.
**Si existe una salida parcial o un hash inválido, se detiene y no la borra.**

## Alcance y cautelas

- La cohorte son **45 de 300 asignados**, no necesariamente 45 conductores observados durante 300 s.
- En la semilla 102, placebo/S/V observaron 44/45; SV y combinado 45/45.
- Los cruces detectados son proxies de transición de línea y pueden quedar unknown.
- Cruce en amarillo no necesariamente implica ilegalidad.
- No hay equivalencia de protocolos Quito/Hangzhou ni calibración individual.
- La validación unitaria es local; las 21 corridas de SUMO las ejecuta el usuario.
