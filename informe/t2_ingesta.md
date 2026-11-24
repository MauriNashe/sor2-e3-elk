# T2 — Ingesta y normalización: documentación para el informe

Material de base para las secciones 6.2 (implementación) y 6.4 (verificación) del informe.
Evidencia en `results/t2/`; capturas en `informe/figuras/t2_*.png`.

---

## 1. Dónde se hace cada transformación

| Etapa | Componente | Qué hace | Por qué ahí |
|---|---|---|---|
| Generación | auditd (`log_format = RAW`), Apache (formato `combined`) | Escriben una línea por registro | Son las fuentes; no se modifican sus formatos más allá de RAW |
| Lectura | Filebeat 9.5.6, módulos `auditd` y `apache` | Lee solo los archivos activos, sigue la rotación por inodo, etiqueta cada evento con módulo, fileset y nombre de pipeline (`@metadata.pipeline`). **No parsea** | Agente liviano en la máquina monitoreada: cuanto menos procesa, menos interfiere con lo que se mide |
| Recepción | Logstash 9.5.6 (`lab.conf`) | Copia la hora de lectura de Filebeat a `lab.filebeat_read`, agrega `lab.logstash_received`, quita el `event.original` duplicado y enruta a `lab-<módulo>-AAAA.MM.DD` | Punto único de entrada: se agregan marcas y enrutamiento sin tocar los agentes |
| Parseo | Ingest pipelines oficiales de los módulos, en Elasticsearch | Convierte cada línea en campos ECS y fija `@timestamp` desde el propio log | Pipelines probados, mantenidos por Elastic y con nombres de campo estándar. Escribir grok propios agregaba riesgo sin beneficio |
| Indexación | Pipeline final `lab-ingested` + plantilla `lab` | Agrega `lab.es_ingested`; mapea los tipos de cada campo (IP, enteros, fechas) | Se aplica a todo documento, sea cual sea el módulo |

## 2. Marcas de tiempo

| Campo | Momento | Quién la pone | Resolución |
|---|---|---|---|
| `@timestamp` | **Generación**: hora escrita en la línea del log | Pipeline del módulo | auditd: milisegundos; Apache: segundos |
| `lab.filebeat_read` | Lectura de la línea por Filebeat | Logstash (copia el `@timestamp` original de Filebeat) | milisegundos |
| `lab.logstash_received` | **Primera recepción** en el stack | Logstash | milisegundos |
| `lab.es_ingested` / `event.ingested` | **Indexación** | Pipeline final / pipeline del módulo | nanosegundos |

Todas en UTC. La VM tiene NTP con un desfase medido de unos 0,1 ms, y las cuatro marcas salen del mismo reloj.

Latencia observada en la verificación (20/11, 00:17): unos 13 s desde que se escribe la línea hasta que se indexa. La lectura de Filebeat (hasta ~3 s) y su espera para armar el lote antes de enviarlo (~10 s) explican casi todo; la indexación tarda ~15 ms. A eso se suma el refresco del índice (5 s) hasta que el documento es visible en búsquedas.

## 3. Tabla de campos — auditd

Campos verificados sobre documentos reales (`results/t2/verificacion_20261120_001735.txt`; completar con `ejemplos_campos_*.json`).

| Dato que pide la consigna | Campo en Elasticsearch | Origen en la línea de `audit.log` | Ejemplo (acceso denegado, serie 733) |
|---|---|---|---|
| Origen del evento | `event.module`, `event.dataset`, `log.file.path` | Lo agrega Filebeat | `auditd`, `auditd.log`, `/var/log/audit/audit.log` |
| Tipo de registro | `event.action` (registros del núcleo); `auditd.log.record_type` (registros de programas: USER_CMD, CRED_ACQ…) | `type=` | `syscall` |
| Host | `host.name` | No viene en el log (`name_format = NONE`): lo pone Filebeat | `sor2-lab` |
| Resultado | `auditd.log.success`; `process.exit_code` (retorno de la llamada); `event.outcome` (solo en registros de programas, `res=`) | `success=`, `exit=`, `res=` | `no`, `-13` (EACCES) |
| Usuario | `user.id` (uid), `user.effective.id` (euid), `user.audit.id` (auid); `user.name` solo si el log trae `acct=` | `uid=`, `euid=`, `auid=`, `acct=` | `1001` (labuser), auid `1000` (labadmin) |
| Proceso | `process.executable`, `process.name`, `process.pid`, `process.parent.pid` | `exe=`, `comm=`, `pid=`, `ppid=` | `/usr/bin/cat`, `cat`, `24786` |
| Regla | `auditd.log.key` | `key=` | `lab_protegido` |
| Serie / identificador | `auditd.log.sequence` | `msg=audit(<epoch>:<serie>)` | `733` |
| Llamada al sistema | `auditd.log.syscall` (número) | `syscall=` | `257` (openat) |
| Generación | `@timestamp` | `msg=audit(<epoch>…)` | `2026-11-20T03:17:35.615Z` |
| Archivo involucrado (registro PATH) | `auditd.log.name`, `auditd.log.inode`, `auditd.log.mode`, `user.owner.id` | `name=`, `inode=`, `mode=`, `ouid=` | `/usr/bin/id`, `0100755`, `0` |
| Directorio de trabajo (CWD) | `process.working_directory` | `cwd=` | `/home/labadmin/sor2-e3-elk-ml` |
| Línea de comando (PROCTITLE / EXECVE) | `auditd.log.proctitle` (decodificado del hexadecimal); `process.args` | `proctitle=`, `a0=`, `a1=`… | `sshd: labadmin [priv]`; `["/usr/bin/id"]` |

**Notas para el informe:**
- `process.exit_code` es el nombre que usa ECS, pero en un registro SYSCALL contiene el **valor de retorno de la llamada** (−13 = permiso denegado), no el código de salida del proceso.
- No se inventan valores: `user.name` no se completa a partir del uid. La correspondencia uid ↔ usuario del laboratorio (1000 = labadmin, 1001 = labuser) es conocida y se documenta aparte.
- `event.original` se conserva pero **no está indexado** en la plantilla de Filebeat: sirve para leerlo y compararlo, no para buscar.

## 4. Tabla de campos — Apache (access.log)

| Dato que pide la consigna | Campo en Elasticsearch | Origen en la línea | Ejemplo |
|---|---|---|---|
| IP del cliente | `source.ip`, `source.address` | Primer campo | `127.0.0.1` (en la T3: `172.30.0.x`) |
| Método | `http.request.method` | Línea de petición | `GET` |
| Ruta | `url.original` (y `url.path`, `url.query`) | Línea de petición | `/no-existe-t2check1795144655` |
| Respuesta | `http.response.status_code`; `event.outcome` (`failure` si ≥ 400) | Código | `404`, `failure` |
| Timestamp | `@timestamp` | `[20/Nov/2026:00:17:35 -0300]` (resolución de 1 s) | `2026-11-20T03:17:35.000Z` |
| Tamaño | `http.response.body.bytes` | Bytes | `432` |
| Agente | `user_agent.original`, `user_agent.name` | User-Agent | `curl/8.5.0` |
| Usuario autenticado | `user.name` | Tercer campo | `-` (sin autenticación) |
| Origen del evento | `event.module`, `event.dataset`, `log.file.path` | Filebeat | `apache`, `apache.access` |

## 5. Eventos de auditd con varios registros (agregación)

Un mismo evento del núcleo se escribe como **varias líneas** que comparten la marca `msg=audit(<epoch>:<serie>)`: SYSCALL (la llamada, el resultado, el usuario, el proceso y la clave), CWD (directorio de trabajo), PATH (cada archivo involucrado) y PROCTITLE (línea de comando). Filebeat indexa **un documento por línea**.

- **Identificador del evento:** el par (`@timestamp`, `auditd.log.sequence`). La serie sola no alcanza, porque se reinicia al reiniciar auditd.
- **Reconstrucción:** se agrupan los documentos por ese par. La verificación de la T2 (paso [8]) lo demuestra: la serie 733 reúne `proctitle`, `cwd`, `path` y `syscall`.
- **Decisión para las características (T4):** los recuentos por regla y por resultado se calculan sobre los registros **SYSCALL** (un SYSCALL = un evento), así no se cuenta varias veces el mismo evento. PATH y PROCTITLE se usan solo si una característica necesita el archivo o el comando.
- Los registros de programas (USER_CMD, CRED_ACQ, etc.) son eventos de una sola línea.

## 6. Ejemplos de parseo incorrecto y correcto

| | Incorrecto (primera ejecución) | Correcto (configuración final) |
|---|---|---|
| Apache | `error.message: field [event.original] already exists`; sin IP, método, URL ni código | IP, método, URL, código, bytes y user agent parseados; 0 errores |
| auditd | `event.outcome: success'␝UID="root"`; mensaje anidado partido; `user.id: 4294967295` (auid sin asignar) | `auditd.log.success: no`, `process.exit_code: -13`, `user.id: 1001`, `user.audit.id: 1000`, `auditd.log.key: lab_protegido` |
| Causa | ECS v8 en Logstash + formato ENRICHED de auditd | `lab.conf` quita el duplicado; `log_format = RAW` |

Detalle: `results/t2/diagnostico_parseo_incorrecto_20261119.txt` y `results/t2/verificacion_20261120_001735.txt`.

## 7. Comparación con los logs originales

`src/extraccion/validar_ingesta.py` compara **línea por línea** el texto de cada archivo con el `event.original` de los documentos que vinieron de ese archivo, e informa líneas faltantes, documentos de más, errores de parseo y, en auditd, el desglose por tipo de registro.

Resultado final del 20/11/2026, 01:14 (`results/t2/recuentos_20261120_011452.txt`). Se ignoraron las líneas de los últimos 90 s, que podían seguir en tránsito.

| Archivo | Líneas comparadas | Documentos en ES | Faltan en ES | De un archivo ya rotado | De más (duplicados) | Errores de parseo |
|---|---|---|---|---|---|---|
| `audit.log` | 317 | 317 | **0** | 0 | **0** | **0** |
| `access.log` | 2 | 6 | **0** | 4 (en `access.log.1`) | **0** | **0** |
| `error.log` | 2 | 7 | **0** | 5 (en `error.log.1`) | **0** | **0** |

- **auditd:** coincide línea por línea, y los 18 tipos de registro presentes (SYSCALL 20, PATH 10, CWD 6, PROCTITLE 20, EXECVE 4, USER_CMD 19, USER_START 33, USER_END 34, USER_ACCT 35, USER_AUTH 5, CRED_ACQ 18, CRED_DISP 34, CRED_REFR 29, LOGIN 14, SERVICE_START 16, SERVICE_STOP 15, BPF 4, DAEMON_ROTATE 1) tienen el mismo recuento en el log y en Elasticsearch. Una primera corrida del script (01:11) mostraba diferencias por tipo porque no descontaba en ese desglose las líneas recientes; se corrigió.
- **Apache:** a medianoche `logrotate` rotó `access.log` y `error.log`. Las líneas anteriores quedaron en `*.log.1` y **ya estaban indexadas**: Filebeat siguió el archivo por su inodo durante la rotación y no perdió ni duplicó nada. Es evidencia directa de que la rotación no afecta la ingesta.
- **Conclusión:** 0 eventos perdidos, 0 duplicados y 0 errores de parseo en las tres fuentes.

Fuente: `results/t2/recuentos_<fecha>.txt`.

## 8. Lo que estas fuentes no pueden ver

- Un escaneo de puertos que no completa peticiones HTTP no aparece en `access.log`.
- Accesos a archivos no cubiertos por las reglas de auditd no quedan registrados (las reglas están acotadas a propósito; riesgo R4).
- Lo que haga un usuario con privilegios de root puede incluir desactivar la auditoría.
- Las IPs del laboratorio son de una red Docker sin NAT hacia el anfitrión; en un servidor real detrás de un proxy, `source.ip` sería la del proxy.
