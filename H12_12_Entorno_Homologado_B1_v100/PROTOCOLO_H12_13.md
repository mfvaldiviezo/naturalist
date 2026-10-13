# Hoja de ruta H12.13: entrenamiento homologado H-SARG / Coop-SARG

**No implementado aún**. Debe partir del contrato H12.12 acreditado en SUMO, no del entorno heredado.

1. **Congelar el entrenamiento:** red (`.net.xml`), demanda (`.rou.xml`), configuración de SUMO, versión de SUMO, seed, periodo de decisión, microtick, reward, recorte/orden del estado, scheduler de semáforos y etapa `online`; registrar SHA de código y artefactos.
2. **Acciones nuevas:** construir extractor H-SARG y Coop-SARG que acepte `Discrete(2)`, y estado `[0,1]^34` nueva semántica. Conservar arquitecturas separadas pero idéntico presupuesto de interacciones por comparación; no inicializar pesos de checkpoints legados sin un estudio de transferencia que lo identifique como tal.
3. **Comprobar aprendizaje:** observar fases 0/2 y transiciones amarillas, decisiones/aplicación física, distribuciones PPO, convergencia, exploración, control de reward no trivial, perfiles de colas/demora en carga nominal.
4. **Control negativo:** par nominal/probe con trazas y hashes idénticos. Casos nominal, Vine activo y H09 requieren flujos de demanda, inicio, tiempo y grupos de vehículos homologados; no confundir roster de 45 con la exposición real de 45.
5. **Comparadores:** FIXED, MaxPressure auténtico y SOTA entrenado bajo la MISMA superficie semafórica, acciones físicas, red/demanda, calidad de entrenamiento y presupuesto. No denominar CoLight a la heurística histórica.
6. **Repetición/estadística:** semillas independientes verdaderas, estratos de episodios, horizonte suficiente y análisis de saturación; reportar deltas pareados con IC/efecto/tamaño de muestra; evitar decir robusto por empate de argmax.
7. **Alcance doctoral:** el objetivo es modelar patrones no nominales y evaluar resiliencia de los controladores, **no optimizar el tráfico en la fase de modelado ni afirmar tasas reales de conducción imprudente en Quito**.

Puerta de paso a H12.13: `H12_12_PLAN_OK`, `H12_12_FREEZE_OK` y `H12_12_SUMO_SMOKE_OK` reales; manifest reproducible y prueba de amarillo bajo demanda real. Después auditar seguridad de programas de semáforos y conflicto geométrico antes de generalizar a otros TLS o redes.
