# H12.12 — Nuevo contrato experimental B1 homologado (v1.0.0)

**Objetivo:** eliminar las incompatibilidades observadas en H12.7–H12.11 ANTES de entrenar o comparar controladores. Este paquete **no cambia** `traffic_project`, `revision_naturalista` anterior, ni los cuatro checkpoints heredados. Utiliza un entorno Gymnasium nuevo e incompatible con esos checkpoints. **No optimiza el tráfico de Quito ni calibra los episodios POLIDriving**; prepara el banco de ensayo que permitirá evaluar después la resiliencia ante Vine/H09.

## Evidencia de partida (código de red observado en GitHub, pendiente de contraste en equipo local)

La red `tsc_framework/sumo_configs/networks/hangzhou_4x4.net.xml` de B1 declara un programa `type="actuated"` con cuatro fases: verde 0 (42 s), amarillo 1 (3 s), verde 2 (42 s), amarillo 3 (3 s). Hay cuatro entradas físicas distintas pero cada una controla varios movimientos. No se identifica un rojo total explícito entre estas dos fases. H12.12 conserva esos **estados de las luces del XML**, pero reemplaza la lógica *actuated* de B1 por control deliberado `online` de TraCI; otros semáforos siguen con sus programas normales. Es una decisión experimental nueva, no equivalente al viejo SUMO bajo control actuado.

## Contrato nuevo

| Elemento | Definición H12.12 | Diferencia respecto de legado |
|---|---|---|
| Acción | `Discrete(2)`: 0→fase verde0; 1→fase verde2 | Antes `Discrete(4)` con 0/2 y 1/3 duplicados |
| Transición de semáforo | Verde activo ≥10 s; transición 0→1 amarillo 3s→2 y 2→3 amarillo 3s→0 | Antes salto directo mediante `setPhase` |
| Control de señal | `setRedYellowGreenState` con **solo estados verificados del net.xml**, programa `online` TraCI | Antes programa original `actuated` más `setPhase` |
| Observación `34D` | `q12`, `w12`, `p4`, `φ4`, `τ2`, todo `[0,1]` | Antes 4 carriles repetidos 12 posiciones, presión sin salidas y edad sin recorte |
| q/w | Primeras 4 posiciones corresponden a 4 carriles únicos ordenados; restantes 8 son padding cero | No repetir artificialmente el cuarto carril |
| presión | Por entrada: `N_entrada - promedio(N_salidas_reales_de_sus_conexiones)`, codificado `clip(0.5 + presión/(2×50),0,1)` | `outgoing=[]` antes |
| φ4 | One-hot solo en los dos índices de acción 0/1; durante amarillo los 4 ceros | No confundir dos verdes con cuatro |
| τ2 | Edad actual de etapa `/120` acotada; edad de etapa `/min_green` acotada | No salen del `Box` |
| Recompensa | `- (0.4·delay_norm + 0.3·Gini + 0.3·CVaR95_norm)` de los 4 carriles REALES | No duplicar esperas de un carril nueve veces |
| Micro/decisión | 0,5 s / 5 s (10 microticks por paso RL) | SUMO legado entrenó a microtick 1 s |
| Demanda nominal | Ruta **explícita** `hangzhou_dense.rou.xml`, no "primer XML ordenado" | Script histórico eligió primer archivo |

**Advertencias científicas:**

1. Cuatro entradas físicas llenan solo cuatro de las doce ranuras `q12/w12`. Se mantienen 34 componentes para poder configurar extractores H-SARG/Coop-SARG con input 34D, pero NO se reutilizan sus pesos. La futura homologación puede revisar dimensionalidad y comparabilidad si se amplía a otras topologías.
2. La presión propuesta es una definición operacional nueva (media de los carriles salientes por aproximación), NO una presión MaxPressure canónica y NO una medida estadística de tráfico imprudente.
3. La fase amarilla de 3 s se toma del `net.xml`; **no se certifica seguridad geométrica total** ni tiempo all-red en una red que no lo contiene. La validación geométrica/SOTA aún requiere auditoría.
4. La estrategia de RL podrá solicitar cambios durante el amarillo, pero se ignoran hasta completar la secuencia. `info['stage']` informa la etapa realmente iluminada, no una acción solicitada que se aplica automáticamente.
5. La semántica de la recompensa es nueva: no comparar valores numéricos de recompensa contra H12.5–H12.10 sin reentrenamiento y reevaluación.
6. Los 45 vehículos Vine y 45 H09 proceden de selección de una referencia congelada, pero **H12.12 no los inyecta**; el inyector autenticado de H12.9 se integrará después de verificar este contrato.

## Instalación / preflight en Windows

Extraer `H12_12_Entorno_Homologado_B1_v100.zip` bajo:
`C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h1212 = '.\H12_12_Entorno_Homologado_B1_v100'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
python -m unittest discover -s "$h1212\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'H12.12 pruebas fallidas' }
python "$h1212\h12_12_homologar.py" --repo-root $repo --revision-root . --mode plan
if ($LASTEXITCODE -ne 0) { throw 'H12.12 preflight fallido' }
```

Esperado: `H12_12_PLAN_OK`. **No genera resultados, no arranca SUMO ni carga modelos.** La validación del XML de tu repositorio puede revelar diferencias con el archivo previamente examinado y fallará antes de modificar nada.

## Congelar manifiesto de entradas (sin SUMO)

```powershell
python "$h1212\h12_12_homologar.py" --repo-root $repo --revision-root . --mode freeze
if ($LASTEXITCODE -ne 0) { throw 'H12.12 freeze fallido' }
```

Esperado: `H12_12_FREEZE_OK` y nuevo `revision_naturalista\resultados\h12_12_homologado_...\manifiesto_h12_12.json`. Incluye SHA-256 de red, demanda, configuración, `tsc_env.py`, `train.py` y todos los fuentes H12.12, además de los detalles de fases, presión, 34D, recompensa y transición.

## Smoke de 60 s (opcional, SÍ arranca SUMO; no entrenará)

**Solo después de aprobar las pruebas y el plan.** Utiliza controlador fijo alternante de test, no PPO ni Vine. Se exige reconocimiento de nueva semántica por flags explícitos.

```powershell
python "$h1212\h12_12_homologar.py" `
  --repo-root $repo --revision-root . --mode smoke `
  --seed 101 --rl-steps 12 --min-green 10 `
  --ack-new-contract NEW_MODEL_REQUIRED `
  --ack-online-control TLS_OVERRIDE
if ($LASTEXITCODE -ne 0) { throw 'Smoke SUMO H12.12 NO validado' }
```

Esperado, **si SUMO real es compatible en tu equipo**: `H12_12_SUMO_SMOKE_OK decisiones=12 microticks=120 ...`. Una carpeta nueva de resultados contendrá:
- `manifiesto_h12_12.json` (entradas congeladas)
- `sumo_h12_12.sumocfg` (config aislada, no sobrescribe original)
- `runtime_h12_12.json` (versiones de SUMO/Gymnasium/NumPy/TraCI)
- `smoke_h12_12.json` (34D, esperas, recompensa y secuencia completa de cambios de señales)
- `ERROR_h12_12.json` (solo si falla alguna condición; útil para corrección)

Al terminar el smoke compara nuevamente los SHA de las ocho fuentes. Un cambio concurrente invalida el piloto. Si el XML difiere, si se altera un estado TLS o si SUMO no mantiene el reloj de 0,5 s, **falla cerrado**. El resto de intersecciones permanece como en la red SUMO; este smoke no es comparación multiintersección.

## Consultar última evidencia

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_12_homologado_*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-ChildItem $ultimo.FullName | Select-Object Name
if (Test-Path (Join-Path $ultimo.FullName 'ERROR_h12_12.json')) {
  Get-Content (Join-Path $ultimo.FullName 'ERROR_h12_12.json') -Raw
} else {
  Get-Content (Join-Path $ultimo.FullName 'smoke_h12_12.json') -Raw |
    ConvertFrom-Json | Select-Object result,steps,microticks,tls_events
}
```

## Qué NO hay todavía

- Entrenamiento o checkpoints H12.13; no cargar `ppo_ideal`, `ppo_chaos`, `ppo_coop_ideal` ni `ppo_coop_chaos` bajo `Discrete(2)`.
- Equivalencia con benchmarks SOTA ni posibilidad de inferencia poblacional Quito.
- Comparación del caos H09/Vine o transferencia entre ciudades.
- Certificación física de amarillo/all-red o compatibilidad de topología multiagente.

Pruebas efectuadas por el autor del paquete: **45 pruebas offline, incluidos 7 casos con TraCI/Gymnasium simulado**, sin SUMO real en el entorno de desarrollo. No declarar `H12_12_SUMO_SMOKE_OK` hasta observarlo en Windows.
