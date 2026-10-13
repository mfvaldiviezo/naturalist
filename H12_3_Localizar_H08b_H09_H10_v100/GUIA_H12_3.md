# H12.3 — Localizador de interfaces H08b/H09/H10

Este paquete corrige el alcance limitado del descubrimiento H12.2. A diferencia del inventario anterior, recorre subcarpetas de código y también examina las entradas de archivos ZIP `H08`, `H09` y `H10`, **sin descomprimir ni ejecutar código**.

La implementación original `FixedRosterInjector` y su método `on_step(traci, step)` provienen del H08b funcional previamente documentado. El objetivo de H12.3 es localizar el código exacto, sus dependencias e integridad; no crea otra versión del modelo probabilístico.

## Ejecutar

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h123 = '.\H12_3_Localizar_H08b_H09_H10_v100'
python -m unittest discover -s "$h123\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Tests H12.3 fallaron' }

# Inventario en pantalla, sin escritura
python "$h123\h12_3_localizador.py" --revision-root .
if ($LASTEXITCODE -ne 0) { throw 'Inventario H12.3 falló' }

# Crear informe nuevo, sin tocar código original
python "$h123\h12_3_localizador.py" --revision-root . --guardar
if ($LASTEXITCODE -ne 0) { throw 'No se pudo guardar H12.3' }
```

Si no aparece ningún script H08/H09/H10 dentro de `revision_naturalista`, es probable que los paquetes estén en una **carpeta hermana**. El siguiente comando amplía la búsqueda a `C:\Proyecto_Tesis_Final_V1` (solo lectura del proyecto; cualquier informe sigue dentro de `revision_naturalista\resultados`):

```powershell
python "$h123\h12_3_localizador.py" `
    --revision-root . `
    --search-root "C:\Proyecto_Tesis_Final_V1" `
    --guardar
```

Se generan `simbolos_h08b_h09_h10.json` y `hallazgos_h12_3.md` bajo una carpeta nueva `resultados\h12_3_localizador_*`.

El resultado `LOCALIZADO` solo identifica la clase y el archivo; **no habilita automáticamente el modo `active`**. La etapa siguiente verificará la firma del constructor, las dependencias, el roster congelado y los hashes. Si no aparece un paquete H08b, la búsqueda registra honestamente `PENDIENTE`, sin sustituir Vine Student por ruido nuevo.

## Precisiones metodológicas

- El piloto H12.2 exitoso utilizó `tsc_framework/sumo_configs/hangzhou.sumocfg`, cuya demanda es `hangzhou_minimal.rou.xml`. No equivale al escenario emparejado H11 con demanda densa.
- El estado 34D / 4 acciones quedó demostrado en H12.1. El piloto H12.2 demostró 40 microticks de 0,5s con 4 decisiones PPO, sin inyección.
- Una vez localizada H08b, el hook deberá avanzar solo mediante el ciclo Gymnasium; H08b ejecuta `on_step()` sin llamar `simulationStep()`.
- No se modifica ni sobreescribe H08/H09/H10/H11, datos POLIDriving ni checkpoints.
