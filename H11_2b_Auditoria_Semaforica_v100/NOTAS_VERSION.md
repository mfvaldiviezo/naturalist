# H11.2b — Auditoría semafórica v1.0.0

- Solo lectura de las corridas H11.2/H10 ya ejecutadas; no depende de SUMO/TraCI.
- Revalida SHA-256 de telemetría original; en modo estricto revalida la comparación H10 pareada y sus archivos originales.
- Analiza episodios con y sin cruce, distancias/velocidades al primer ámbar, dos tiempos hipotéticos de reacción y frenado observado.
- Empareja el mismo movimiento por vehículo, TLS, índice de enlace y carril de entrada; preserva visitas repetidas y episodios no encontrados.
- Reconcilia cruces H09 `confirmed` con cruces H11.2 `PROXY_signal_stable` sin homologarlos.
- Cuenta comandos Vine `command_issued=True` dentro de cada ventana y registra propuestas no ejecutadas separadamente.
- Conserva valores desconocidos y no concluye legalidad, intencionalidad, causalidad ni tasas representativas de Quito.
- 16 pruebas automatizadas sintéticas superadas en el entorno de construcción. **Pendiente ejecución sobre los archivos de Windows del usuario**.
