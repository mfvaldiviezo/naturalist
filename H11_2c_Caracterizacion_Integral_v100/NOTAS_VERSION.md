# H11.2c v1.0.0 — Notas de versión

- Auditoría offline H11.2/H10 nominal e híbrido contextual; sin ejecución de SUMO.
- Revalida SHA-256 de los cuatro CSV de cada escenario y, con `--require-paired`, los archivos H10 originales comparados en las corridas pareadas.
- Analiza tasas sobre denominadores de observación específicos, episodios continuos, vehículos distintos y cohortes objetivo contrafactuales.
- Estratificación interna/externa para evitar interpretar directamente el límite SUMO como una norma legal.
- Reportes de eventos de carril interno son candidatos, no gridlock acreditado.
- Seguridad: desaceleraciones observadas y contador de emergency stops separados.
- Umbrales exploratorios configurables, no parámetros calibrados para Quito.
- Las pruebas automáticas usan datos sintéticos; pendientes de resultados en la instalación real.
