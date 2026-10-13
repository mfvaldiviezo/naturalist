# H12.11 — Auditoría offline de procedencia PPO y contratos

## Para qué sirve

H12.10 mostró: 39 observaciones 34D modificadas y 39 cambios pequeños de distribución PPO, pero ninguna de las 60 decisiones cambia. H12.11 examina el entorno actual, el script de entrenamiento y los metadatos **JSON** de los cuatro checkpoints `.zip` de Stable-Baselines3 para establecer qué está documentado y qué sigue sin acreditarse.

**NO** ejecuta SUMO, entrena, modifica el entorno, carga políticas, importa módulos del repositorio ni deserializa pesos. Solo lee archivos e informa hallazgos. No certifica procedencia de entrenamiento.

## Instalación

Extraer carpeta `H12_11_Auditoria_Proveniencia_PPO_v100` en `C:\Proyecto_Tesis_Final_V1\revision_naturalista`.

### 1. Tests

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate tsc-env
$h1211 = '.\H12_11_Auditoria_Proveniencia_PPO_v100'
$repo = 'C:\Proyecto_Tesis_Final_V1\traffic_project'
python -m unittest discover -s "$h1211\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Tests H12.11 fallidos' }
```

### 2. Identificar resultados previos (no seleccionar por fecha sin verificar)

```powershell
$h129 = Get-ChildItem '.\resultados' -Directory -Filter 'h12_9_exposicion_300s_*' |
  Where-Object { Test-Path (Join-Path $_.FullName 'active\piloto_h12_5.json') } |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
$h1210run = Get-ChildItem '.\resultados' -Directory -Filter 'h12_10_politica_*' |
  Where-Object { Test-Path (Join-Path $_.FullName 'dictamen_h12_10.json') } |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $h129 -or -not $h1210run) { throw 'Faltan resultados previos H12.9/H12.10' }
```

### 3. Preflight

```powershell
python "$h1211\h12_11_proveniencia.py" `
  --repo-root $repo `
  --h129-dir $h129.FullName `
  --h1210-dir $h1210run.FullName `
  --mode plan
if ($LASTEXITCODE -ne 0) { throw 'H12.11 preflight fallido' }
```

Salida esperada: `H12_11_PLAN_OK`.

### 4. Diagnóstico real

```powershell
python "$h1211\h12_11_proveniencia.py" `
  --repo-root $repo `
  --h129-dir $h129.FullName `
  --h1210-dir $h1210run.FullName `
  --results-root '.\resultados' `
  --mode analyze
if ($LASTEXITCODE -ne 0) { throw 'H12.11 diagnostico fallido' }
```

Salida esperada: `H12_11_DIAGNOSTICO_OK (NO CERTIFICA ENTRENAMIENTO)`.

### 5. Leer dictamen

```powershell
$ultimo = Get-ChildItem '.\resultados' -Directory -Filter 'h12_11_proveniencia_*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content (Join-Path $ultimo.FullName 'dictamen_h12_11.md') -Encoding UTF8
```

## Decisión después del diagnóstico

Si se confirma la desigualdad de timesteps (por ejemplo, 20.480 vs 1.007.616), no atribuir diferencias a la arquitectura sin igualar presupuestos. La semántica de entrenamiento para rutas, período, amarillos, vector 34D y elección física de fases deberá acreditarse mediante fuente, configuraciones históricas y manifiestos; el archivo `.zip` solo almacena parte de esa información. Los modelos `chaos` heredados no pueden describirse como entrenados con Vine/H09 sin evidencia. Dejar intactos checkpoints y resultados H12.9/H12.10.
