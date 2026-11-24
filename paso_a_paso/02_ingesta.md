# 02 — Ingesta (T2: auditd y Apache hasta Elasticsearch)

Deja los registros de auditd y Apache llegando **parseados** a Elasticsearch, con las reglas de auditd del
laboratorio cargadas. Parte del estado final de la guía [01 — Laboratorio](01_laboratorio.md).
Siguiente guía: 03 — Escenarios.

**Archivos que intervienen**

| Archivo | Para qué |
|---|---|
| `configs/auditd/lab.rules` | Reglas de auditd: exclusiones del stack, archivo protegido, accesos denegados y procesos de `labuser` |
| `configs/filebeat/filebeat.yml` | Módulos `auditd` y `apache` (access y error), con salida a Logstash |
| `configs/logstash/pipeline/lab.conf` | Marca de recepción, quita el `event.original` duplicado y enruta por fuente |
| `configs/elasticsearch/pipeline_lab_ingested.json` | Pipeline final que agrega `lab.es_ingested` |
| `scripts/t2_ingesta_setup.sh` | Configura auditd (RAW, rotación), carga las reglas, crea la plantilla `lab` y los pipelines, y arranca Filebeat |
| `scripts/t2_reiniciar_ingesta.sh` | Borra los índices de logs y hace que Filebeat vuelva a leer desde cero |
| `scripts/t2_verificar.sh` | Genera eventos conocidos y comprueba que llegan bien parseados |

**Las cuatro marcas de tiempo de cada evento**

| Campo | Qué marca | Lo pone |
|---|---|---|
| `@timestamp` | Generación del evento (hora escrita en el propio log) | Pipeline del módulo en Elasticsearch |
| `lab.filebeat_read` | Lectura de la línea por Filebeat | Logstash, copiando el `@timestamp` que trae Filebeat (`event.created` existe solo en Apache) |
| `lab.logstash_received` | Primera recepción en el stack | Logstash (`lab.conf`) |
| `lab.es_ingested` (y `event.ingested`) | Indexación en Elasticsearch | Pipeline final `lab-ingested` (y el del módulo) |

Todas se guardan en **UTC**.

---

### 0. Encender la VM y comprobar el stack (si estaba apagada)

🪟 *como administrador*:

```powershell
Start-VM sor2-lab
```

Esperar 1–2 minutos y entrar con `ssh labadmin@192.168.56.10`. Después, 🐧:

```bash
cd ~/sor2-e3-elk-ml && docker compose ps -a
```

**Resultado:** `es01`, `kibana` y `logstash` en `Up ... (healthy)`.

### 1. Copiar el repo actualizado a la VM 🪟

Lleva a la VM las configuraciones y los scripts nuevos. No pisa el `.env` ni los resultados que solo existen en la VM.

```powershell
cmd /c "tar -cf - --exclude=.git -C C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml . | ssh labadmin@192.168.56.10 tar -xf - -C sor2-e3-elk-ml"
```

**Resultado:** pide la contraseña y termina sin mensajes (ver [README de las guías](README.md#copiar-el-repo-actualizado-a-la-vm-)).

### 2. Aplicar los cambios del stack 🐧

Vuelve a correr el `setup` (roles y usuarios) y reinicia Logstash para que lea el `lab.conf` nuevo.

```bash
cd ~/sor2-e3-elk-ml && docker compose up setup && docker compose restart logstash
```

**Resultado:** el `setup` termina con `[setup] Listo.` y `exited with code 0`. Logstash se reinicia; en 1 minuto `docker compose ps` lo vuelve a mostrar `healthy`.

### 3. Instalar la ingesta 🐧

Revisarlo antes con `less scripts/t2_ingesta_setup.sh` (se sale con `q`). Configura auditd (formato RAW y rotación), crea el archivo protegido, carga las reglas, instala Filebeat, crea el pipeline final y la plantilla `lab`, carga los pipelines de los módulos y arranca Filebeat.

```bash
sudo bash scripts/t2_ingesta_setup.sh
```

**Resultado esperado por etapa:**
- `== 1`: `log_format = RAW`, `max_log_file = 50`, `num_logs = 10`, `max_log_file_action = ROTATE`, `name_format = NONE`.
- `== 2`: `-rw------- 1 root root ... /srv/lab/protegido/secreto.txt`.
- `== 3`: 4 reglas `never` (Filebeat, dockerd, containerd y shim), el `-w` del archivo protegido y 3 `always` con `uid=` y las claves `lab_acceso_denegado` y `lab_exec`.
- `== 4`: `Config OK`.
- `== 5`: `OK PUT /_ingest/pipeline/lab-ingested` y `OK PUT /_index_template/lab`.
- `== 6`: pipelines `filebeat-9.5.6-auditd-log-…` y `filebeat-9.5.6-apache-…`.
- `== 7`: `active` y la prueba de Filebeat contra Logstash terminando en `OK`.

### 4. Reiniciar la ingesta desde cero 🐧

Rota `audit.log`, **borra** los índices `lab-auditd-*`, `lab-apache-*` y `lab-otros-*` y vacía el registro de Filebeat, para que todo se vuelva a ingestar con la configuración final. No toca `lab-test`.

```bash
sudo bash scripts/t2_reiniciar_ingesta.sh
```

**Resultado:** `DELETE lab-... -> HTTP 200` por cada índice, `registry eliminado`, `active` y `Listo`.

> Este paso se repite cada vez que cambie el parseo, y una vez más justo antes del lote de la T3.

### 5. Verificar la ingesta 🐧

Esperar unos 20 segundos después del paso 4. El script genera un acceso denegado de `labuser` al archivo protegido y dos peticiones HTTP (una 200 y una 404) con una marca única, y comprueba que llegan parseadas y sin errores. Guarda la salida en `results/t2/`.

```bash
bash scripts/t2_verificar.sh
```

**Resultado:** `=== Resultado: 11 OK, 0 fallas ===` (tarda algo más de un minuto: espera 45 s a que los eventos sean visibles). Además muestra:
- La tabla de índices `lab-*`.
- Un ejemplo de la petición 404 con IP, método, URL, código y las marcas de tiempo.
- El registro SYSCALL del acceso denegado: clave `lab_protegido`, `success: no`, código de salida `-13` (EACCES), `uid` 1001 (`labuser`) y `auid` 1000 (`labadmin`, que lanzó el `sudo`).
- La reconstrucción del evento: los registros que comparten su número de serie (`syscall`, `cwd`, `path`, `proctitle`).

> Si fallan los controles de formato RAW, auditd no aplicó el cambio con la recarga: reiniciar la VM (`sudo reboot`) y repetir desde el paso 4.

### 6. Vistas de datos y consultas en Kibana 🪟

En `http://192.168.56.10:5601` (usuario `elastic`): **☰ → Stack Management → Data Views → Create data view**:
- Nombre `auditd`, patrón `lab-auditd-*`, campo de tiempo `@timestamp`.
- Nombre `apache`, patrón `lab-apache-*`, campo de tiempo `@timestamp`.

Después, en **☰ → Discover**, con el rango de tiempo en *Last 1 hour*:
- Vista `auditd`, consulta `lab_protegido`.
- Vista `apache`, consulta `http.response.status_code : 404`.

**Resultado:** en ambas consultas aparecen los eventos generados en el paso 5. **Captura de cada una** (la consigna pide capturas de consultas en la T2), en `informe/figuras/t2_*.png`. En auditd, anotar en qué campo aparece `lab_protegido`: es un dato para la tabla de campos.

### 7. Traer la evidencia al repo 🪟

```powershell
scp labadmin@192.168.56.10:~/sor2-e3-elk-ml/results/t2/*.txt C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\results\t2\
```

**Resultado:** los archivos `verificacion_<fecha>.txt` copiados al `100%`.

### 8. Comparar los logs originales con Elasticsearch 🐧

Compara línea por línea `audit.log`, `access.log` y `error.log` con lo indexado: líneas perdidas, documentos de más, errores de parseo y recuento por tipo de registro de auditd. Además guarda un documento de ejemplo de cada tipo de registro para la tabla de campos. Se ignoran las líneas de los últimos 90 s, que todavía pueden estar en tránsito.

```bash
cd ~/sor2-e3-elk-ml && sudo python3 src/extraccion/validar_ingesta.py
```

**Resultado:** un bloque por archivo y un resumen final. Lo esperado es `faltan 0 / de más 0 / errores 0` en los tres, y en auditd todos los tipos de registro con el mismo número en el log y en ES (sin `<-- difiere`). Guarda `results/t2/recuentos_<fecha>.txt` y `results/t2/ejemplos_campos_<fecha>.json`.

> Si `access.log` muestra documentos "de más", puede ser que Apache haya rotado su log después del reinicio de la ingesta: esas líneas están en `access.log.1`. No es una pérdida.

### 9. Traer los resultados al repo 🪟

```powershell
scp labadmin@192.168.56.10:~/sor2-e3-elk-ml/results/t2/* C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\results\t2\
```

**Resultado:** las verificaciones, los recuentos y los ejemplos de campos en `results/t2/`. Con eso se completa la sección 7 de `informe/t2_ingesta.md`.

---

## Problemas encontrados y su solución

Detalle en `results/t2/diagnostico_parseo_incorrecto_20261119.txt` y en la bitácora.

| Síntoma | Causa | Solución |
|---|---|---|
| Documentos de Apache con `error.message: field [event.original] already exists` y sin campos HTTP | Logstash (ECS v8) ya copia la línea en `event.original` y el pipeline del módulo intenta hacerlo de nuevo | `lab.conf` quita `event.original` antes de enviar |
| Campos de auditd mezclados (`event.outcome: success'␝UID="root"`) | `log_format = ENRICHED` agrega valores tras un separador 0x1D que el módulo no parsea | `log_format = RAW` |
| `node=(null)` en los registros de auditd | `name_format = HOSTNAME` aplicado con recarga | `name_format = NONE`; el host sale de `host.name` (Filebeat) |
| `_cat/indices` devuelve 403 con `lab_analyst` | Al rol le faltaba el privilegio `monitor` | Agregado en `setup.sh` (paso 2) |
| La verificación no encuentra eventos que sí están indexados | El evento tarda ~19 s en llegar (casi todo en Filebeat) y el índice se refresca cada 5 s | La verificación espera 45 s |
| No aparecen registros SYSCALL al agrupar por `auditd.log.record_type` | En los SYSCALL el módulo deja el tipo en `event.action` (`syscall`) | Consultar por `event.action` |
| Error al buscar dentro de `event.original` | La plantilla de Filebeat lo guarda sin indexar | Buscar por campos parseados (`auditd.log.key`, `url.original`) |
| `event.created` vacío en auditd | El pipeline del módulo auditd no conserva la hora de lectura de Filebeat | Logstash la copia a `lab.filebeat_read` para las dos fuentes (aplicar con los pasos 2 a 5) |

## Documentación de la T2

La tabla de campos con su origen, las marcas de tiempo, la agregación de los eventos de auditd, los ejemplos de parseo correcto e incorrecto y la comparación con los logs originales están en [`informe/t2_ingesta.md`](../informe/t2_ingesta.md).
