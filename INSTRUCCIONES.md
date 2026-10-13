# Respaldo selectivo — `revision_naturalista`

Este paquete contiene un script de Python **sin dependencias adicionales** y un lanzador PowerShell para Windows. No crea el respaldo dentro del directorio original, no sobreescribe archivos, no cambia Git y no ejecuta SUMO ni entrenamiento. Los archivos originales permanecen intactos.

## 1. Copiar los dos scripts

Coloca `empaquetar_revision_definitiva.py` y `empaquetar_revision_definitiva.ps1` en:

`C:\Proyecto_Tesis_Final_V1\revision_naturalista`

Abre PowerShell en esa carpeta (el entorno `colight-pyg` o `tsc-env` sirve; el empaquetador utiliza solamente la biblioteca estándar):

```powershell
cd C:\Proyecto_Tesis_Final_V1\revision_naturalista
conda activate colight-pyg

# PLAN: no crea ZIP ni modifica proyecto.
.\empaquetar_revision_definitiva.ps1 -Modo plan -Detalle
```

Para guardar la lista en un documento y revisarla con calma:

```powershell
.\empaquetar_revision_definitiva.ps1 -Modo plan -Detalle *>&1 |
    Out-File -FilePath "..\inventario_revision_definitiva.txt" -Encoding UTF8
```

## 2. Crear respaldo recomendado

**Opción A, respaldo compacto:** conserva últimas versiones de carpetas `H*_vNNN`, evidencias con estados verificados H12.17–H12.19, otras evidencias auditadas localizadas, manifiestos de datos, documentos y dependencias principales de `scripts/`. No incluye `data/verified` completos ni repositorios Git `externos_h12_16`.

```powershell
.\empaquetar_revision_definitiva.ps1 -Modo crear
```

**Opción B, respaldo de código más reproducible:** incluye además los clones originales `externos_h12_16/LibSignal` y `externos_h12_16/colight`, **con `.git`** para que puedan ejecutarse los controles `git show` de H12.18/H12.19. Ocupa más espacio.

```powershell
.\empaquetar_revision_definitiva.ps1 -Modo plan -Detalle -ConFuentesExternas
.\empaquetar_revision_definitiva.ps1 -Modo crear -ConFuentesExternas
```

**Opción C, respaldo privado de datos verificados:** si también deseas incluir datos de `data/verified` y todos los scripts originales, agrega `-ConDatosVerificados -TodosScripts`. **Advertencia:** algunos datasets verificados pueden contener muestras reservadas o datos personales aunque su nombre no lo indique. No compartas este ZIP sin revisar esos archivos, permisos y condiciones de uso.

## 3. Ubicación de salida

Por defecto el ZIP se crea en:

`C:\Proyecto_Tesis_Final_V1\RESPALDOS_REVISION\revision_naturalista_definitiva_YYYYMMDD_HHMMSS.zip`

También se crea al lado un `*.sha256.txt` y dentro del ZIP un `MANIFIESTO_ARCHIVO_FINAL.json` con SHA-256 individual de cada archivo, bytes, procedencia, carpetas seleccionadas y exclusiones. El ZIP no se anuncia como completo hasta validar CRC y todos los SHA-256 de su contenido.

Si prefieres otra ruta:

```powershell
.\empaquetar_revision_definitiva.ps1 -Modo crear -Salida "D:\RespaldoTesis\revision_naturalista_definitiva.zip"
```

Puedes verificar un ZIP existente sin tocar los archivos originales:

```powershell
.\empaquetar_revision_definitiva.ps1 -Modo verificar -Salida "D:\RespaldoTesis\revision_naturalista_definitiva.zip"
```

## Criterio de selección y limitaciones

- Conserva la **versión numérica más alta** de cada familia de carpeta con formato `H..._vNNN` (ej.: H12.18 v103, H12.19 v101). Esto es una regla de selección, **no una prueba de que un experimento esté científicamente validado**.
- Selecciona la última carpeta de cada familia de resultados cuyo reporte contenga el marcador conocido, como `H12_19_COLIGHT_UPSTREAM_NETWORK_TD_SMOKE_OK`; para H12.19 exige también el SHA conocido del checkpoint `2BE69572...`.
- Conserva manifiestos y fuentes necesarias identificadas por nombres y referencias de código; no incluye todos los prototipos antiguos, directorios temporales, entornos Conda, ZIP anteriores ni salidas fallidas.
- **No incluye** automáticamente el repositorio hermano `traffic_project` (está fuera de `revision_naturalista`). Para trasladar toda la tesis, haz además un respaldo separado de ese repositorio y sus checkpoints.
- No incluye los datos RAW ni el holdout explícito (Richard) por defecto. El reconocimiento por nombre es una salvaguarda, **no un análisis del contenido**. Tampoco determina si cualquier CSV contiene datos personales.
- Los documentos e informes pueden contener rutas absolutas del equipo de origen; el paquete no es una instalación portátil lista para ejecutar de forma automática.
- Para pruebas intermedias científicamente importantes que no hayan sido seleccionadas por los patrones incorporados, agrega explícitamente el resultado, por ejemplo: `-IncluirResultado @('nombre_carpeta_resultado')`. Se etiquetará como agregado manual, **sin asumir que esté acreditado**.
- Si falta alguno de los tres resultados críticos H12.17, H12.18 o H12.19, `crear` se detiene. No uses `-PermitirSinCriticos` para declarar un respaldo definitivo.

**Recomendación:** genera primero `plan -Detalle`, revisa la lista, y después crea el ZIP. Conserva el ZIP y su `*.sha256.txt` en una ubicación externa al proyecto.
