# 02 — Ingesta (T2: auditd y Apache hasta Elasticsearch)

Deja los registros de auditd y Apache llegando **parseados** a Elasticsearch, con las reglas de auditd del
laboratorio cargadas. Parte del estado final de la guía [01 — Laboratorio](01_laboratorio.md).
Siguiente guía: 03 — Escenarios.

**Archivos que intervienen**

| Archivo | Para qué |
|---|---|
| `configs/auditd/lab.rules` | Reglas de auditd: exclusiones del stack, archivo protegido, accesos denegados y procesos de `labuser` |
| `configs/filebeat/filebeat.yml` | Módulos `auditd` y `apache` (access y error), con salida a Logstash |
| `configs/elasticsearch/pipeline_lab_ingested.json` | Pipeline final que agrega `lab.es_ingested` |
| `scripts/t2_ingesta_setup.sh` | Instala y carga todo lo anterior y arranca Filebeat |
| `scripts/t2_verificar.sh` | Genera eventos conocidos y comprueba que llegan bien |

**Las cuatro marcas de tiempo de cada evento**

| Campo | Qué marca | Lo pone |
|---|---|---|
| `@timestamp` | Generación del evento (hora escrita en el propio log) | Pipeline del módulo en Elasticsearch |
| `event.created` | Lectura del archivo por Filebeat | Filebeat / pipeline del módulo |
| `lab.logstash_received` | Primera recepción en el stack | Logstash (`configs/logstash/pipeline/lab.conf`) |
| `lab.es_ingested` | Indexación en Elasticsearch | Pipeline final `lab-ingested` |

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
scp -r C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml labadmin@192.168.56.10:~/
```

**Resultado:** lista de archivos copiados al `100%`, entre ellos `lab.rules`, `filebeat.yml`, `t2_ingesta_setup.sh` y `t2_verificar.sh`.

### 2. Revisar el script 🐧

```bash
cd ~/sor2-e3-elk-ml && less scripts/t2_ingesta_setup.sh
```

**Resultado:** el contenido del script. Se sale con `q`.

### 3. Instalar la ingesta 🐧

Configura auditd (rotación y nombre de host), crea el archivo protegido, carga las reglas, instala Filebeat, crea el pipeline final y la plantilla `lab`, carga los pipelines de los módulos y arranca Filebeat.

```bash
sudo bash scripts/t2_ingesta_setup.sh
```

**Resultado esperado por etapa:**
- `== 1`: líneas `max_log_file = 50`, `num_logs = 10`, `max_log_file_action = ROTATE`, `name_format = HOSTNAME` (y `log_format = ENRICHED`).
- `== 2`: `-rw------- 1 root root ... /srv/lab/protegido/secreto.txt`.
- `== 3`: la lista de reglas cargadas: 4 `never` (Filebeat, dockerd, containerd y shim), el `-w` del archivo protegido y 3 `always` con `uid=` y las claves `lab_acceso_denegado` y `lab_exec`. auditctl muestra el uid como número.
- `== 4`: `Config OK`.
- `== 5`: `OK PUT /_ingest/pipeline/lab-ingested` y `OK PUT /_index_template/lab`.
- `== 6`: nombres de pipelines que empiezan con `filebeat-9.5.6-auditd-log` y `filebeat-9.5.6-apache-…`.
- `== 7`: `active` y la prueba de Filebeat contra Logstash terminando en `OK`.
- Al final: `Listo. Siguiente paso: bash scripts/t2_verificar.sh`.

> Al arrancar, Filebeat lee `audit.log` y `access.log` **desde el principio**: los índices incluyen también la actividad anterior (instalación, pruebas de la T1). Es normal.

### 4. Verificar la ingesta 🐧

Genera un acceso denegado de `labuser` al archivo protegido y dos peticiones HTTP (una 200 y una 404) con una marca única, y comprueba que llegan a Elasticsearch sin errores de parseo. Guarda la salida en `results/t2/`.

```bash
bash scripts/t2_verificar.sh
```

**Resultado:** termina con `=== Resultado: 7 OK, 0 fallas ===`. Además muestra:
- La tabla de índices `lab-*`: `lab-auditd-AAAA.MM.DD` y `lab-apache-AAAA.MM.DD` en verde.
- Un ejemplo de la petición 404 con IP, método, URL, código y las marcas de tiempo.
- Un documento completo de auditd del acceso al archivo protegido.

Si aparece alguna `[FALLA]`, guardar la salida y revisarla antes de seguir.

### 5. Vistas de datos y consultas en Kibana 🪟

En `http://192.168.56.10:5601` (usuario `elastic`): **☰ → Stack Management → Data Views → Create data view**:
- Nombre `auditd`, patrón `lab-auditd-*`, campo de tiempo `@timestamp`.
- Nombre `apache`, patrón `lab-apache-*`, campo de tiempo `@timestamp`.

Después, en **☰ → Discover**, con el rango de tiempo en *Last 1 hour*:
- Vista `auditd`, consulta `auditd.log.key : "lab_protegido"`.
- Vista `apache`, consulta `http.response.status_code : 404`.

**Resultado:** en ambas consultas aparecen los eventos generados en el paso 4. **Captura de cada una**: la consigna pide capturas de consultas en la T2. Guardarlas en `informe/figuras/t2_*.png`.

> Si `auditd.log.key` no existe, buscar `lab_protegido` en la barra de búsqueda y anotar en qué campo aparece: es un dato para la tabla de campos.

### 6. Traer la evidencia al repo 🪟

```powershell
scp labadmin@192.168.56.10:~/sor2-e3-elk-ml/results/t2/*.txt C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\results\t2\
```

**Resultado:** el archivo `verificacion_<fecha>.txt` copiado al `100%`.

---

## Pendiente de la T2 (después del lote, viernes)

- Tabla de campos con su origen (auditd: host, resultado, usuario, proceso, regla, serie; Apache: IP, método, ruta, respuesta, timestamp).
- Reconstrucción de los eventos de auditd que comparten número de serie, o documentación de la agregación.
- Comparación de recuentos entre los logs originales y Elasticsearch, y ejemplos de parseo correcto e incorrecto.
