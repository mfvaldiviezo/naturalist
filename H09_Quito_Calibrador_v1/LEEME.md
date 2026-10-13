# H09 — Calibrador / validador empírico Quito (v1)

**Estado de esta entrega:** instrumento de **validación agregada y cribado de configuraciones candidatas**, no un generador de probabilidades individuales calibradas. **SOLO LECTURA de SUMO**. No sustituye H08b, no cambia ni reentrena Vine, y no toca las rutas, la red ni los controladores RL.

## Fundamentación empírica

1. **Quito, cruces semafóricos:** Díaz-Muñoz, F., García-Ramírez, Y., Roblez-Torres, V., y Merino-Vivanco, X. (2026). *Traffic Signal Noncompliance at Urban Intersections: Cycle-Level Evidence and Uncertainty-Aware Site Prioritization for Smart Urban Mobility in Ecuador*. *Smart Cities*, 9(9), 140. https://doi.org/10.3390/smartcities9090140
   - QUI-1: 4.518 vehículos; 168 cruces en amarillo y 170 en rojo.
   - QUI-2: 2.716; 0 amarillo y 89 rojo.
   - QUI-3: 2.409; 0 amarillo y 84 rojo.
   - Total meramente descriptivo: 9.643 vehículos, 511 eventos, 343 rojos, 168 amarillos.
   - La fuente expone especial sensibilidad al filtro de calidad para QUI-2 y QUI-3. **No** se deduce que el cruce en amarillo sea imposible en dichos sitios; tampoco que el total sea prevalencia representativa de Quito.
   - El numerador usa *eventos de cruce de la línea de detención*. El denominador son *vehículos observados en el protocolo de campo*. **No es** P(cruzar rojo | enfrentarse al rojo).
2. **Velocidad:** Johns Hopkins International Injury Research Unit / BIGRS. *Quito Road Safety Risk Factors* (observaciones noviembre de 2021–abril de 2023), **20 %** de vehículos observados con exceso de velocidad (valor publicado redondeado). https://publichealth.jhu.edu/sites/default/files/2024-02/20230602bigrsquito04pages.pdf. No se dispone del n correspondiente a esa cifra en el registro anterior. **No inferir intervalos de confianza** con n de otra ola.
3. **Sensibilidad temporal:** Nota Quito Informa sobre un informe 2024 publicada el 30 de octubre de 2024 menciona **27 %** de vehículos por encima del límite. Se incluye en un archivo aparte `indicador_alterno_velocidad_quito_2024.json`: es otra publicación/período, no debe promediarse con el 20 % ni reemplazar la fuente previa sin armonizar métodos. https://quitoinforma.quito.gob.ec/2024/10/30/estudio-sobre-seguridad-vial-otorga-herramientas-para-salvar-vidas-y-mejorar-politicas-publicas/

## Estructura

- `datos_referencia/`: COPIAS de objetivos y conteos publicados de la base Quito H09 previa. Las fuentes tienen SHA-256 en `MANIFEST_SHA256.json`.
- `scripts/calibrador_quito_h09.py`: auditoría, comparación por sitio, comparación descriptiva de candidatos multisemilla.
- `scripts/observador_traci_h09.py`: registrador de cruce proxy de líneas semafóricas y muestras de velocidad por zona, solo lectura.
- `config/protocolo_hangzhou_ejemplo.json`: se debe **revisar el mapeo TLS** y la definición de denominador. Contiene referencias solo ilustrativas de Hangzhou a intersecciones Quito: **no equivale a replicarlas**.
- `config/zonas_velocidad_ejemplo.json`: posición y carril ilustrativos para una futura muestra de velocidad, **no calibrados**.
- `tests/test_h09_quito.py`: 11 pruebas sin necesitar SUMO, con eventos completamente sintéticos identificados como pruebas.

## Uso inmediato sin ejecutar ni modificar SUMO

Desde carpeta descomprimida `H09_Quito_Calibrador_v1`:

```powershell
python .\scripts\calibrador_quito_h09.py auditar-fuentes
python -m unittest discover -s .\tests -v
```

### Opción A — Registrar eventos en una simulación ya controlada por otro script

```python
from observador_traci_h09 import EventObserver
obs = EventObserver(run_id="baseline_101", seed=101, sites=["B1", "B2", "C1"])
# Dentro de tu loop ya existente, DESPUÉS del único traci.simulationStep():
obs.observe(traci)
# Al terminar y con todos los pasos observados:
obs.write_csv(r"C:\Proyecto_Tesis_Final_V1\revision_naturalista\resultados\h09_eventos_101\eventos_h09.csv")
```

Asegúrate de que `observador_traci_h09.py` está en el `PYTHONPATH` o importarlo desde la ruta completa. Este observador NO llama `simulationStep()` ni modifica SUMO cuando se usa como clase; su función es leer. Comprueba que los semáforos **B1, B2, C1 realmente existan** en la red utilizada antes de registrar eventos.

### Opción B — Piloto separado, únicamente de observación

El primer piloto de seguridad utiliza el `hangzhou_vine_sin_additional.sumocfg` ya validado:

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
python .\H09_Quito_Calibrador_v1\scripts\observador_traci_h09.py `
  --sumocfg .\resultados\ntvc_vine_r_07_hangzhou_piloto\hangzhou_vine_sin_additional.sumocfg `
  --seed 101 --pasos 600 --step-length 0.5 `
  --sites B1,B2,C1 `
  --salida-dir .\resultados\h09_quito_observador_base_101
```

**No se necesita reejecutar H06/H08b** ni ajustar Vine para validar las fuentes. Para analizar eventos individuales del simulador sí es necesario instrumentar una corrida futura: los antiguos CSV de `trafico_hito08.csv` NO registraron fase semafórica por vehículo en el momento de pasar la línea. El observador no crea conductas imprudentes, solo registra lo que realmente aparece en SUMO.

### Comparar contra Quito

```powershell
python .\H09_Quito_Calibrador_v1\scripts\calibrador_quito_h09.py comparar `
  --eventos .\resultados\h09_quito_observador_base_101\eventos_h09.csv `
  --protocolo .\H09_Quito_Calibrador_v1\config\protocolo_hangzhou_ejemplo.json `
  --salida-dir .\resultados\h09_quito_comparacion_base_101
```

Produce `reporte_comparacion_h09.json` con por-sitio: n_simulado, n_referencia, rojo, amarillo, desconocidos, diferencia en puntos porcentuales, cobertura de clasificación y razones de comparabilidad insuficiente. Si un CSV está vacío, se abstiene en lugar de reportar una tasa falsa de 0 %.

### Comparar varias configuraciones experimentales

Crea `candidatos_h09.csv` con columnas `escenario,seed,eventos` y **rutas reales a CSV de eventos ya observados**:

```csv
escenario,seed,eventos
baseline,101,C:/ruta/real/baseline_101/eventos_h09.csv
perfil_A,101,C:/ruta/real/perfil_A_101/eventos_h09.csv
perfil_B,101,C:/ruta/real/perfil_B_101/eventos_h09.csv
```

```powershell
python .\H09_Quito_Calibrador_v1\scripts\calibrador_quito_h09.py comparar-candidatos `
  --manifiesto .\candidatos_h09.csv `
  --protocolo .\H09_Quito_Calibrador_v1\config\protocolo_hangzhou_ejemplo.json `
  --salida-dir .\resultados\h09_quito_candidatos
```

El resultado `comparacion_candidatos_h09.json` reúne errores descriptivos por escenario/semilla; con protocolo no comparable indica `ONLY_DESCRIPTIVE_CANDIDATE_COMPARISON` y **no clasifica los parámetros como empíricamente calibrados**.

## Advertencias metodológicas que impiden afirmar calibración definitiva hoy

1. **Denominador:** el observador TraCI detecta pasos de línea completados y el artículo cuenta vehículos observados por ciclos/bloques. No sabemos si las reglas de inclusión coinciden. **Sin armonización se prohíbe validar oficialmente tasas Quito/SUMO como si fueran la misma métrica.**
2. **Tiempo de fase:** con `step_length=0.5`, si la fase cambió entre t y t+dt, clasifica `unknown/uncertain`, jamás como un rojo/amarillo confirmado. Una transición de carril no certifica en todos los casos la geometría exacta de la línea: es un proxy explícito y no un detector definitivo.
3. **Sitios:** mapear B1 a QUI-1 no convierte la red Hangzhou en la intersección Capitán Geovani/Duchicela. Los resultados solo sirven como contraste transferido, no prueba de representatividad.
4. **Velocidad:** `getMaxSpeed(lane)` se utiliza como límite de referencia de la vía y los vehículos se muestrean una vez por estación; la fuente BIGRS usa su propio protocolo de selección. Sin equivalencia demostrada el contraste del 20% es descriptivo.
5. **Números:** 15%, 30%, 50% son proporciones de perfiles experimentales, no prevalencias observadas de conductores imprudentes en Quito.
6. **Datos faltantes:** las probabilidades de cruzar en rojo condicionado a una oportunidad, seguir demasiado cerca, bloqueo e ignorar prioridad siguen no identificadas en fuentes publicadas agregadas. Permanecen en `null`.
7. **Controles semafóricos:** versiones con RL deben compartir red, demanda, semilla, señales y protocolo. El observador no debe llamar un segundo `simulationStep()`.

## Resultado esperado

- Ahora: base de comparación empírica documentada, auditable por sitio, sin inventar tasas individuales.
- Siguiente parte científica: generar escenarios parametrizados de imprudencia en un `scenario_runner` de SUMO, registrar eventos bajo la misma política de observación, ejecutar semillas pareadas y seleccionar candidatos que minimicen discrepancias agregadas **solamente si las métricas son comparables**. No hay todavía parámetros numéricos calibrados para rojo, gridlock o seguimiento próximo.
