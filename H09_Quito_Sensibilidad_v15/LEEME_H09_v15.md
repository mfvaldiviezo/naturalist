# Hito H09 — Sensibilidad 15/30/50 y oportunidades semafóricas v1.5

## Objetivo y límites

Determinar si los vehículos expuestos a perfiles persistentes de conducción
experimental presentan oportunidades de interacción con rojo/amarillo y cruces
observados. No estima probabilidades de infracción individuales a partir de las
observaciones agregadas de Quito. Sigue siendo una simulación de Hangzhou 4×4.

**Intervención:** solo perfil `combinado` H09 v1.2, con parámetros *exploratorios*
(tau=0.9, minGap=1.2, speedFactor=1.15, jmDriveAfterYellowTime=1.5,
jmDriveAfterRedTime=0.5, jmIgnoreKeepClearTime=0). No modificar perfiles ni
valores de referencia durante este experimento.

**Red y reloj:** Hangzhou 4×4, semáforos B1,B2,C1, 600 × 0.5s = 300s,
semillas 101–105, demanda original de 300 vehículos. Cohortes SHA-256 anidadas
45, 90 y 150, con asignación por semilla.

## Dependencias existentes (NO sobrescribir)

- `H09_Quito_Instrumentacion_v11` (observador original y zonas)
- `H09_Quito_Perfiles_Contextuales_v12` (ejecutor y configuración de perfiles)
- `resultados/ntvc_vine_r_07_hangzhou_piloto/hangzhou_vine_sin_additional.sumocfg`
- `resultados/h09_zonas_velocidad_generadas_v11.json`
- `resultados/h09_v12_piloto_101/` y `resultados/h09_v14_multisemilla/`

## Distinción de indicadores

- `tls_phase_exposure`: primer fotograma de un **episodio de aproximación**
  dentro de 30 m y de ese color, incluso si está detenido. Una vez por episodio
  y color, no una vez por paso ni una tasa conductual.
- `tls_moving_opportunity`: primer fotograma del mismo episodio y color con
  velocidad >= 1 m/s. **PROXY operativa**, no asegura que el conductor pueda
  detenerse físicamente ni constituye oportunidad condicional comparable con
  el trabajo de campo de Quito.
- `stopline`: cruce proxy conservador registrado por observador v1.1, con
  clasificación verde/amarillo/rojo/unknown.
- `tls_crossing_link`: unión auditable del cruce al episodio observado.
  Si no hubo aproximación detectada antes del cruce, el enlace queda vacío,
  en vez de inventar un denominador.

Un mismo vehículo puede tener episodios distintos en intersecciones distintas,
y un episodio puede exponerse a varios colores por cambio de fase.
No dividir automáticamente `n_cruces_rojos / n_oportunidades_rojas` para
inferir tasas de infracción condicionales; primero valorar elegibilidad,
ambigüedad y relación uno-a-uno. No identificar un cruce amarillo como ilegal.

## Ejecución PowerShell

Extraer esta carpeta en `C:\Proyecto_Tesis_Final_V1\revision_naturalista`.
Activar `tsc-env` y ubicarse en dicha carpeta.

```powershell
$h15 = '.\H09_Quito_Sensibilidad_v15'
python -m unittest discover -s "$h15\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Pruebas H09 v1.5 fallidas' }

# Inspeccionar plan sin ejecutar SUMO:
python "$h15\scripts\ejecutar_h09_v15.py" --root .

# Inicio: si se interrumpe, reanudar sin borrar nada.
Unblock-File "$h15\ejecutar_h09_v15.ps1"
& "$h15\ejecutar_h09_v15.ps1"
```

Serán hasta **20 corridas nuevas**: para cada una de las 5 semillas,
(0 %, 15 %, 30 %, 50 %). El baseline y 15 % previos NO se repiten por
sus métricas, sino que se usa una nueva observación para obtener la cantidad
de episodios de exposición en el mismo protocolo de medición para todos
los porcentajes. **Se exige hash de tráfico idéntico** al baseline y 15 % de
H09 v1.4.3; si cambia, el programa falla cerrado.

Las salidas anteriores de 15 % se conservan intactas y no se sobrescriben.
El nuevo instrumental NO envía comandos de control SUMO/TraCI. Solo los
perfiles experimentales existentes influyen en SUMO para corridas active.

## Salidas nuevas

`resultados/h09_v15_sensibilidad_oportunidades/seed_<semilla>/baseline`
y `active_15_combinado`, `active_30_combinado`, `active_50_combinado`.
En cada carpeta: `manifest_H09.json`, `cohorte_h09.csv`, `trafico_h09.csv`,
`exposicion_h09.csv`, `eventos_h09.csv` enriquecido.

Consolidado:

- `h09_v15_101_105.json`
- `h09_v15_101_105_por_semilla.csv`
- `h09_v15_101_105_contrastes.csv`
- `h09_v15_101_105_resumen.csv`

## Criterios de aceptación

1. Pruebas unitarias correctas.
2. Configuración, red y rutas originales inalteradas, con SHA-256 auditado.
3. Todos los vehículos seleccionados **y observados** tienen vType correcto;
   asignado 45/90/150, observado puede ser menor.
4. Por semilla, cohorte 15% ⊆ 30% ⊆ 50%.
5. Baseline y 15 % v1.5 reproducen tráfico original hash a hash.
6. Una exposición/oportunidad registrada una única vez por episodio-color,
   sin convertir frames de rojo detenido en ensayos independientes.
7. Nunca reclasificar `unknown` ni cruce amarillo como infracción.
8. No inferir prevalencia de Quito a partir de observaciones de Hangzhou.

### Lo que queda fuera

No hay inyección de Vine Student, agentes DQN/PPO, colisiones deliberadas,
frenados severos cuantificados, equivalencia de protocolos Quito/Hangzhou ni
calibración empírica del comportamiento de los conductores.

**Si una corrida queda a medio escribir**, la carpeta parcial queda protegida:
no eliminarla sin investigar el error primero. No hay sobrescrituras.

## Aclaraciones de interpretación

En las salidas v1.5, las filas de oportunidad se etiquetan como medición
instrumental (`classification_quality=observed_snapshot`) y no como
infracción confirmada. Los porcentajes de **vehículos planificados** son
exactos, pero las oportunidades observables, cruces y vehículos efectivamente
admitidos son aleatorios y dependen del tráfico. Aunque una aproximación
registre movimiento en rojo, ello NO demuestra que hubiera distancia de
frenado disponible; el criterio es operativo y debe validarse más adelante
contra cinemática/espacio de frenado antes de estimar probabilidades por
oportunidad. La referencia empírica de Quito tampoco dispone de ese denominador.

El filtro temporal conserva cambios de fase dudosos; no extrapola eventos
`unknown` como cruces rojos/amarillos. Los cruces con falta de episodio
anterior se reportan como no enlazables, en vez de suponer una oportunidad.
