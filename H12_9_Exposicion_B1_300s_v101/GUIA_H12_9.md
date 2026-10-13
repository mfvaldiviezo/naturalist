# H12.9 v1.0.1 — Exposición efectiva de Vine ante PPO (300 s)

## Corrección v1.0.1

Se reemplaza el acceso indirecto `__import__('importlib').util` por `import importlib.util` explícito. La versión v1.0.0 podía fallar en Python cuando el submódulo no estaba previamente cargado. Se añadió una regresión con un intérprete aislado (`python -S`), que verifica la carga en memoria de H12.5 y H12.7. **No cambia** parámetros Vine, cohortes, semilla, duración, lógica SUMO, estados ni checkpoints.

## Motivación

H12.8 encontró que B1 tuvo tráfico en 94/120 microticks, pero no había espera ni
vehículos detenidos exactamente en las doce fronteras de decisión (cada 5 s).
Los agregados B1 y las observaciones 34D fueron idénticos entre nominal y Vine,
aun cuando los 20 comandos alteraron las aceleraciones globales. Este resultado
NO implica que PPO sea robusto al comportamiento no nominal.

## Propósito

Extender **el mismo piloto de integración**, con seed 101, hasta el horizonte
300 s que utiliza la referencia congelada H10. Se ejecutan tres escenarios
comparables: nominal, probe y Vine protegido activo. A cada microtick de 0,5 s,
se miden los agregados B1 y qué IDs seleccionados Vine están realmente en sus
carriles, más sus velocidades. Cada 5 s se registra el estado completo 34D
antes y después de la decisión PPO.

No se alteran las fuentes `H12.5`, `H12.7`, H08/H09/H10, ni el checkpoint.
Se cargan copias en memoria con verificación de hashes SHA-256. El único
cambio operativo del instrumento es extender el límite de 20 a 60 decisiones
PPO, conservando 10 microticks de 0,5 s por decisión. La fuente del entorno RL
usa la misma transformación auditada de H12.2 y el mismo checkpoint H-SARG.

**Limitación:** No es una comparación estadística ni valida representación
poblacional de conducción de Quito. El entorno heredado repite 4 carriles
únicos hasta 12, deja carriles salientes vacíos y detecta 2 fases verdes
representadas por 4 acciones PPO (alias). Estos problemas no se corrigen aquí;
cambiarlos requiere verificar/reentrenar checkpoints.

## Instalación

Extraer `H12_9_Exposicion_B1_300s_v101` dentro de
`C:\Proyecto_Tesis_Final_V1\revision_naturalista` manteniendo su nombre.
Deben existir los directorios ya usados H12.5, H12.7, H12.2, scripts y H10.

## A. Pruebas automáticas (sin SUMO)

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h129 = '.\H12_9_Exposicion_B1_300s_v101'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
python -m unittest discover -s "$h129\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'H12.9: pruebas fallidas' }
```

## B. Plan y verificación SHA (no SUMO)

```powershell
python "$h129\h12_9_exposicion.py" `
    --revision-root . --repo-root $repo --mode plan
if ($LASTEXITCODE -ne 0) { throw 'H12.9: preflight fallido' }
```

Debe imprimir `PLAN_OK` y el baseline H08 de 300 IDs (45 seleccionados Vine).

## C. Ejecución nominal/probe/activo: seed 101, 300 s

**Solo si B pasó.** Tres sesiones de SUMO (cada una 600 microticks, 60
acciones PPO). Se limitarán comandos a 100 en total, además de las guardas H08
(20 por ventana 60 s; 2 por paso; 12 por vehículo). El uso de 100 no implica
que vaya a emitirlos todos. Cualquier fallo de seguridad detiene el ensayo.

```powershell
python "$h129\h12_9_exposicion.py" `
    --revision-root . `
    --repo-root $repo `
    --mode run `
    --model ppo_ideal `
    --tls-id B1 `
    --seed 101 `
    --rl-steps 60 `
    --max-commands 100 `
    --ack-active EXPERIMENTAL_ONLY `
    --ack-time-scale NOT_CALIBRATED
if ($LASTEXITCODE -ne 0) { throw 'H12.9: piloto no acreditado' }
```

El proceso detiene la suite si nominal/probe no es invariante, si no se
confirman los comandos activos, o si aparecen colisiones o teleports. Si falla,
quedan diagnósticos y resultados parciales **sin declarar éxito**.

## D. Informe

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_9_exposicion_300s_*' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_h12_9.md') -Encoding UTF8
```

También se guarda `dictamen_h12_9.json` y tres directorios con microticks y
observaciones. `--mode analyze --results-dir RUTA` recalcula la auditoría
**sin lanzar SUMO**, a partir de las sesiones existentes.

## Interpretación esperada (no anticipar resultados)

- **Vine no aparece en B1:** la intervención longitudinal sigue siendo
  válida, pero no se ha probado exposición local del controlador. Habrá que
  escoger un TLS/horizonte/demanda emparejados y con exposición real.
- **Vine aparece en B1, cambia velocidades pero no 34D:** la codificación
  heredada pierde información cinemática; no se puede afirmar resiliencia.
- **Vine cambia 34D, pero no acciones:** la política escogió la misma decisión
  bajo observaciones diferentes; documentar sin concluir robustez.
- **Vine cambia 34D y acciones:** se ha mostrado respuesta diferencial en
  una semilla; aún faltan validación interverde, métricas y replicación.

Antes de comparaciones SOTA, homologar control (B1 vs red completa),
transiciones amarillas, métricas y presupuestos de entrenamiento.
