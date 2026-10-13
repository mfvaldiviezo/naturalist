# H09 v1.3 — Factorial semáforos × velocidad (sin repetir experimentos anteriores)

## Justificación a partir de la ablación de la semilla 101

En los resultados reales aportados por el investigador, el perfil semafórico por sí solo NO generó cruces confirmados en rojo o amarillo (0/0), mientras que el combinado generó 1/1. Seguimiento redujo llegadas de 96 a 91; bloqueo mantuvo 96; combinado elevó a 105 (en 300 s). Los perfiles activos se asignaron y verificaron 45/45. Baseline y probe tenían SHA256 de tráfico idénticos.

Esto NO demuestra que la parte semafórica sea ineficaz: podrían existir oportunidades escasas o reclasificadas como unknown; tampoco identifica qué otra componente produjo el 1/1 en combinado. La siguiente pregunta concreta es si hay interacción con `speedFactor`.

## Diseño

Se reutilizan SIN repetir las corridas anteriores (seed 101, 600 pasos, dt 0.5, sitios B1/B2/C1):

- **baseline** y **probe**: tráfico original y control instrumental.
- **S** (`active_15_semaforos`): `jmDriveAfterYellowTime=1.5`, `jmDriveAfterRedTime=0.5`.
- **COMBINADO** (`active_15_combinado`): todos los mecanismos originales v1.2.

Se crean SÓLO tres corridas nuevas:

- **P** (`active_15_placebo`): `tau=1.0`, valor nominal documentado de SUMO. Controla que el nuevo tipo de vehículo no altere el baseline por sí solo. Si su hash difiere del baseline, **no** declarar neutralidad.
- **V** (`active_15_velocidad`): `speedFactor=1.15` sin intervención semafórica.
- **SV** (`active_15_semaforos_velocidad`): `speedFactor=1.15`, `jmDriveAfterYellowTime=1.5`, `jmDriveAfterRedTime=0.5` sin alterar seguimiento ni bloqueo.

Cohorte 45/300 para las cinco intervenciones, selección misma semilla 101 y mismo algoritmo H09. Estos valores son **HIPÓTESIS EXPLORATORIAS**, no probabilidades ni parámetros inferidos de Quito.

### ¿Por qué P en lugar de baseline como celda 00 del factorial?

En v1.2 una intervención usa un nuevo `vType`; aunque sus parámetros se asemejen a los predeterminados, puede diferir en detalles estocásticos. La comprobación P vs baseline previene atribuciones erróneas. El informe calcula la interacción exploratoria **I = SV − S − V + P** para algunas métricas; una sola semilla no aporta inferencia estadística. Una modificación de observaciones ambigua no se convierte en cruce rojo ni amarillo.

## Instalación

Descargar `H09_Quito_Factorial_v13.zip`, extraer directamente dentro de:

`C:\Proyecto_Tesis_Final_V1\revision_naturalista`

Se requiere que sigan presentes las carpetas H09 v1.2 y observador v1.1 y el directorio previo `resultados\h09_v12_piloto_101`. Esta entrega NO reemplaza v1.2, NO reescribe baseline ni H08b, NO ejecuta Vine, NO cambia ningún TLS de forma directa.

PowerShell (mismo env `tsc-env`, ubicado en `revision_naturalista`):

```powershell
$h13 = '.\H09_Quito_Factorial_v13'
python -m unittest discover -s "$h13\tests" -v
# Si Windows marca el .ps1 como procedente de Internet:
Unblock-File "$h13\ejecutar_factorial_101.ps1"
& "$h13\ejecutar_factorial_101.ps1"
```

**No es necesario** ejecutar `preparar_factorial_h09_v13.py`: los tres archivos JSON ya están incluidos. Ese generador se proporciona para auditoría o regeneración en un directorio vacío. El PowerShell hace comprobaciones previas de archivos y de carpetas existentes antes de ejecutar; si se interrumpe, conserva la evidencia ya generada y no sobrescribe.

## Archivos nuevos y productos

- `scripts/preparar_factorial_h09_v13.py`: genera los JSON de perfiles en un directorio vacío; no ejecuta SUMO.
- `scripts/comparar_factorial_h09_v13.py`: auditoría por hash de SUMOCFG, red y ruta iguales; permite deliberadamente cambios en el JSON de perfil, comparando además semilla, duración, asignación de cohorte y hashes de archivos por corrida.
- `ejecutar_factorial_101.ps1`: crea P, V, SV; al finalizar escribe `resultados\h09_v12_piloto_101\factorial_semaforos_velocidad_101.csv` y `.json`.
- `tests/`: 11 pruebas offline con datos sintéticos, incluidas detección de corrupción y rechazo de cohortes distintas.

Si `P` no produce un `traffic_sha256` igual al baseline, el estado será `PLACEBO_DIFFERS_FROM_BASELINE_IN_TRAFFIC_SHA256`, señal importante para investigar. La ausencia de igualdad no hace fallar la escritura del informe porque esta diferencia es precisamente algo que necesitamos observar.

## Límites explícitos

1. Clasificación de cruces por observador v1.1: **proxy de transición por línea**, y posibilidad de intervalos ambiguos.
2. `red_rate_proxy_lower_pct` y `red_rate_proxy_upper_pct` son límites deterministas simples por eventos unknown, no intervalos estadísticos ni probabilidades de violación condicionadas a encontrar rojo.
3. `speed_exceed_pct` mide estaciones y muestras, no conductores independientes.
4. No afirmamos causalidad fuerte ni significación estadística con seed 101.
5. No calibrado a Quito: los 343 cruces en rojo y 168 en amarillo publicados tienen otros procedimientos y denominadores.
6. No se conectan aún perturbaciones Vine Student; se preservan sus artefactos.

## Interpretación esperada

- Si V y SV difieren y SV genera rojo/amarillo: puede existir una **interacción dependiente del contexto**, pendiente de reproducir en más semillas.
- Si sólo COMBINADO genera rojo/amarillo, otras componentes (seguimiento/bloqueo) o interacciones de orden superior pueden intervenir; no afirmar que son infracciones causadas inequívocamente por un parámetro.
- Si P no reproduce baseline: revisar el efecto de asignar un `vType` nuevo antes de interpretar factorial como estimación de efecto puro.

La siguiente fase, sólo después de revisar esta corrida, es diseñar un panel multi-semilla y cuantificar **oportunidades semafóricas independientes**, no sólo instantáneas de red/yellow cercanas al TLS.

Documentación oficial SUMO: https://eclipse.dev/sumo/docs/Definition_of_Vehicles,_Vehicle_Types,_and_Routes.html (vType, speedFactor, tau y parámetros de intersección).
