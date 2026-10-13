# H10 v1.1.2 — corrección de asignación XML H09 y reanudación auditada

## Diagnóstico de fallo anterior

En H10 v1.1.1 se empleaban dos lecturas XML distintas:

```python
root_tree = ET.parse(routes).getroot()      # árbol A
_,_,ex = h09.read_roster(routes, horizon)  # nodos del árbol B
h09.clone_route(root_tree, ex, ...)        # modifica B, escribe A: MAL
```

El vType H09 se agregaba al árbol A, pero los atributos `type` de los vehículos se cambiaban en el árbol B. Al guardar A los 45 vehículos seguían con tipo nominal. La verificación en TraCI fallaba legítimamente. **No se ha probado el perfil H09 ni ninguno de los híbridos en H10 v1.1.1.**

Ahora se usa **un solo árbol XML**:

```python
root_tree, planned, ex = h09.read_roster(routes, horizon)
h09.clone_route(root_tree, ex, ...)
verify_route_assignment(...)               # valida 45/45 en disco ANTES de SUMO
```

La auditoría comprueba exactamente qué IDs recibieron el vType y si otros fueron modificados; no basta con comprobar que el elemento vType existe. También preserva el SHA-256 original de `.rou.xml`.

## Reutilización segura

La nueva salida es `resultados/h10_vine_h09_imprudencia_v112_piloto_101`. Se pueden reutilizar **solo** `nominal`, `vine_protegido` y `vine_contextual` del H10 v1.1.1, siempre que se verifiquen todos sus archivos, hashes y manifiestos incluyendo el hash **exacto** del puente anterior `2e5f6693003a435b7f93d93f8e101ab32852882227f8f892dd5b75b7c273efe3` y los mismos parámetros de fuente. Los nuevos escenarios H09 e híbridos se crean únicamente en la nueva salida. **Nunca se reutiliza ni se borra la carpeta H09 parcial de v1.1.1.**

La comparación factorial final escribe `source_scenarios`, que identifica para cada condición el directorio real y la versión del ejecutor que produjo sus datos.

## Comandos (PowerShell, tsc-env)

Descomprimir el ZIP directamente en `C:\Proyecto_Tesis_Final_V1\revision_naturalista`. No sobrescribir ni borrar v1.1.1. Ejecutar:

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
$h10 = '.\H10_Vine_H09_Imprudencia_v112'
python -m unittest discover -s "$h10\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Pruebas H10 v1.1.2 fallidas' }
Unblock-File "$h10\ejecutar_piloto_h10_v112.ps1"
& "$h10\ejecutar_piloto_h10_v112.ps1"        # Solo lectura
& "$h10\ejecutar_piloto_h10_v112.ps1" -Ejecutar
```

Espera `REUTILIZANDO AUDITADO` para las tres condiciones ya terminadas y `PENDIENTE` para `h09`, `hibrido_protegido`, `hibrido_contextual`. Antes de cada ejecución H09 se exigirá `H10 XML H09 VERIFICADO: ... "assigned_xml":45`.

**Parámetros experimentales:** semilla 101, 600 pasos de 0.5 s, 15% H09 entre 300 rutas programadas, 15% Vine sobre el baseline H08 observado, variante Vine Student, presupuesto máximo 100 comandos. La política contextual cambia solo la elegibilidad del inyector: no desactiva `speedMode=31` ni altera la cópula, H08b, H06, H08, sus datos congelados o la simulación histórica. No hay validación empírica para Quito ni evaluación RL en este piloto.

**Si se produce cualquier otro error**, preservar íntegros los archivos parciales y compartir los logs y `DIAGNOSTICO_H09_NO_VALIDADO.json` si se generó; no editar las rutas originales.
