# Bitácora de trabajo

Materia prima para el informe (secciones 6.2 Implementación, 6.4 Pruebas, 7.2 Limitaciones) y para preparar el oral.
Se completa **al terminar cada tarea**, con la memoria fresca: 10–15 minutos alcanzan. No hace falta prosa prolija;
lo importante son los hechos, los problemas y el porqué de cada decisión.

Para cada entrada:
- **Qué hice:** pasos concretos, comandos o archivos clave.
- **Qué falló y cómo lo resolví:** síntoma, causa y solución. Es lo más valioso para el informe y el oral.
- **Decisiones y por qué:** alternativas descartadas.
- **Evidencia generada:** rutas en `results/`, capturas.
- **Para el informe:** qué sección alimenta, figura o tabla pendiente.
- **Preguntas que me podrían hacer en el oral:**

---

## T1 — Infraestructura de laboratorio

**Fecha:** 17–18/11/2026

**Qué hice:**
- Fase A (repo y configuración, hecha el 17/11): esqueleto del repo con la estructura de la consigna, `docker-compose.yml` (setup, es01, kibana, logstash), roles y usuarios de mínimo privilegio en `configs/elasticsearch/setup.sh`, pipeline de Logstash, scripts `vm_setup.sh`, `t1_pruebas.sh` y `t1_inventario.sh`.
- Fases B–F (VM, despliegue, pruebas, inventario): VM en Hyper-V instalada y preparada con `vm_setup.sh`; ELK 9.5.6 levantado con `docker compose up -d`.
- **Pruebas T1 (18/11, 22:21): 9 OK, 0 fallas** (`results/t1/pruebas_20261118_222108.txt`). 401 sin credenciales; 200 con `elastic` (cluster `sor2-lab`, versión 9.5.6); documento indexado y encontrado en `lab-test`; Kibana responde 302 en `192.168.56.10:5601`; ES inaccesible por la IP de la VM (000); `logstash_internal` recibe 403 al leer y al borrar; `lab_analyst` lee (200) pero no escribe (403); heap de ES exacto de 2 GB (2147483648 bytes).
- Puertos en escucha (`ss`): 9200 y 5044 solo en `127.0.0.1`; 5601 solo en `192.168.56.10`; 22 y 80 en todas las interfaces, filtrados por ufw a `192.168.56.0/24`.
- Desde Windows, `Test-NetConnection 192.168.56.10`: puerto 9200 → `TcpTestSucceeded : False`, puerto 5601 → `True`. Captura de Kibana Dev Tools con `GET lab-test/_search` (200 OK, 1 resultado).
- El `@timestamp` del documento de prueba quedó como `2026-11-19T01:21:08Z` aunque se creó a las 22:21 (UTC−3): Elasticsearch guarda todo en UTC. Es relevante para los timestamps de la T2 y las latencias de la T7.
- **Inventario (18/11, 22:40, `results/t1/inventario_20261118_224045.txt`):**
  - Ubuntu 24.04.5 LTS, kernel 6.8.0-149-generic. 4 vCPU (Ryzen 5 5600, hipervisor Microsoft), 7,8 GiB de RAM más 4 GiB de swap. Disco de 37 GB: 14 GB usados y 21 GB libres.
  - NTP sincronizado (chrony), desfase de unos 0,1 ms.
  - auditd 3.1.2, Apache 2.4.58, Filebeat 9.5.6, Docker Engine 29.10.0, Compose v5.8.0, ES 9.5.6 con heap de 2 GB y JVM 27.0.1.
  - Consumo en reposo: Elasticsearch 2,73/3 GiB (91 %), Kibana 966 MiB/1 GiB (94 %), Logstash 630 MiB/1 GiB (62 %). En la VM: 5,0 GiB usados y 2,8 GiB disponibles.
- **Ajuste:** Kibana estaba al 94 % de su límite recién arrancado, así que se subió `KIBANA_MEM_LIMIT` a 1536m para que el OOM no lo mate al usar el dashboard.
- **Ajuste:** las secciones de auditd y ufw del inventario salían vacías porque necesitan root. El script ahora pide sudo al principio y además guarda `auditctl -s`.

**Qué falló y cómo lo resolví:**
- _completar_

**Decisiones y por qué:**
- **Elastic 9.5.6:** último parche publicado de la rama 9.5 al 17/11/2026. La 9.5.7 aparecía en el listado de versiones, pero todavía no tenía paquete de Filebeat publicado. La 9.6.0 acababa de salir.
- **Puertos atados a IPs concretas en el compose:** Docker publica puertos con sus propias reglas de iptables, que no pasan por ufw. Elasticsearch y Logstash quedan solo en 127.0.0.1; Kibana solo en la IP host-only.
- **Un usuario por componente:** `logstash_internal` solo crea documentos (no lee ni borra); `lab_analyst` lee y escribe solo alertas; `elastic` queda para administrar.
- **Sin TLS:** Elastic lo permite en nodo único. Se declara como limitación.
- **Una sola VM con todo:** un único reloj para medir latencias. Costo: ruido en auditd y competencia por recursos (ver R4 del plan).
- **Ubuntu Server 24.04.5 LTS (18/11):** la 26.04 LTS ya existía, pero se descartó porque todo el diseño estaba probado y documentado sobre 24.04 y la 26.04 trae cambios de base recientes.
- **Primer intento con VirtualBox 7.1.4 (18/11), descartado:** VM con 10 GB de RAM, 4 vCPU, disco VDI dinámico de 40 GB, NAT + host-only. Instalación manual, no desatendida: la desatendida no deja fijar la IP ni elegir OpenSSH, y el nombre de máquina por defecto tenía puntos (Linux toma lo que sigue al primer punto como dominio).
- **Problema: la VM se colgó durante `docker compose up -d`** (descarga y descompresión de unos 2 GB de imágenes). El contador dejó de avanzar, no respondían ni ping ni SSH, y la consola quedó congelada.
  - *Diagnóstico:* el `VBox.log` decía `HM: HMR3Init: Attempting fall back to NEM: AMD-V is not available` y después `Guest seems to be unresponsive`. En Windows, `Win32_DeviceGuard` mostraba VBS en ejecución con **Integridad de memoria (HVCI)** activa, y `HypervisorPresent = True`. El hipervisor de Windows ocupa AMD-V, así que VirtualBox corre sobre la API de Hyper-V (NEM), que es lenta y se cuelga con carga alta de disco o CPU.
  - *Alternativas:* (A) desactivar Integridad de memoria y el hipervisor (`bcdedit /set hypervisorlaunchtype off`) mientras dure el TP; (B) usar Hyper-V directamente.
  - *Decisión: B.* No obliga a bajar la seguridad del equipo anfitrión, Hyper-V es el hipervisor nativo de la plataforma y evita la sobrecarga de NEM, que además habría distorsionado las latencias medidas (H3). Costo: rehacer la VM y armar la red a mano.
- **VM en Hyper-V:** generación 2 con arranque seguro (plantilla Microsoft UEFI CA), 10 GB de RAM **fija** (la memoria dinámica haría variar los recursos durante las mediciones y choca con `bootstrap.memory_lock` de Elasticsearch), 4 vCPU y disco VHDX dinámico de 40 GB. Red: switch interno `LabSwitch`, Windows en `192.168.56.1`, NAT de Windows para salir a internet y VM en `192.168.56.10` con gateway `.1`. Se mantuvo el mismo direccionamiento para no cambiar `.env` ni la documentación. Todo se crea con `scripts/hyperv_crear_vm.ps1`.
- **Problema: `Start-VM` falló con "memoria insuficiente" (0x8007000E) con 10 GB.** Con memoria fija, Hyper-V reserva toda la RAM al arrancar, y el anfitrión de 16 GB tenía ~9,9 GB libres. VirtualBox no lo había detectado porque reserva la memoria de a poco. *Solución:* VM con **8 GB fijos**. Alcanza para el presupuesto de los contenedores (ES 3 GB + Kibana 1 GB + Logstash 1 GB) más el sistema, Apache y auditd, y deja margen a Windows.
- _completar con lo que surja en la VM_

**Evidencia generada:**
- `results/t1/pruebas_<fecha>.txt`, `results/t1/inventario_<fecha>.txt`
- Capturas: Kibana Dev Tools con `lab-test`, `Test-NetConnection` desde Windows
- Diagrama: `informe/figuras/arquitectura.drawio` (+ PNG)

**Para el informe:** 5.2 Herramientas y justificación · 6.1 Diseño · 6.2 Implementación (infraestructura) · 6.4 Pruebas

**Preguntas que me podrían hacer en el oral:**
- ¿Por qué Docker Compose? ¿Por qué no correr auditd en un contenedor?
- ¿Cómo comprobás que el acceso está restringido?
- ¿Qué pasa si alguien de la red obtiene la contraseña de Logstash?

---

## T2 — Ingesta y normalización

**Fecha:** 19/11/2026 (parte mínima)

**Qué hice:**
- Reglas de auditd (`configs/auditd/lab.rules`), Filebeat (`configs/filebeat/filebeat.yml`), pipeline final `lab-ingested`, plantilla de índice `lab` y los scripts `t2_ingesta_setup.sh` y `t2_verificar.sh`. Guía: `paso_a_paso/02_ingesta.md`.
- Primera ejecución (19/11, 23:35): `t2_verificar.sh` dio **4 OK y 3 fallas**. Los eventos estaban en `audit.log` y `access.log` y llegaban a Elasticsearch, pero mal parseados.
- Segunda ejecución (19/11, 23:57), después de corregir el parseo: **8 OK y 2 fallas, 0 errores de parseo**. Los documentos estaban bien, pero las consultas de la verificación no los encontraban (ver abajo).
- Diagnóstico con documentos reales (20/11, ~00:10): todos los registros llegan. En `audit.log` había 6 líneas SYSCALL y en el índice hay 6 documentos `event.action: syscall`, además de `path`, `cwd`, `proctitle` y `execve`. Filebeat: 152 eventos publicados y confirmados.
- **Tercera ejecución (20/11, 00:17): 11 OK, 0 fallas** (`results/t2/verificacion_20261120_001735.txt`).
  - Apache: la petición 404 quedó con IP, método, URL y código 404, y `event.outcome: failure`.
  - auditd: el SYSCALL del acceso denegado tiene `auditd.log.key: lab_protegido`, serie 733, `success: no`, código -13, uid 1001 y auid 1000.
  - Reconstrucción por serie 733: `proctitle`, `cwd`, `path` y `syscall`.
- **Latencias observadas en esa ejecución:**
  - Apache: escritura 03:17:35,000 → lectura de Filebeat 03:17:37,951 (+2,95 s) → Logstash 03:17:48,077 (+10,1 s) → indexación 03:17:48,090 (+13 ms). Total ≈ 13,1 s.
  - auditd: 03:17:35,615 → Logstash 03:17:48,078 (+12,5 s) → indexación 03:17:48,095 (+17 ms).
  - El mayor tramo es el envío de Filebeat a Logstash (~10 s, espera para armar lotes). La indexación es despreciable.
- **Comparación con los logs originales (20/11, 01:11, `results/t2/recuentos_20261120_011135.txt`):** auditd 298 líneas comparadas, con 0 faltantes, 0 de más y 0 errores, y los 18 tipos de registro coinciden. Apache: `access.log` y `error.log` tenían solo 2 líneas cada uno, porque `logrotate` los rotó a medianoche; los documentos "de más" (4 y 5) eran líneas que ya estaban en `*.log.1`. Filebeat siguió el inodo durante la rotación sin perder ni duplicar. *Ajuste del script:* ahora clasifica aparte las líneas de archivos rotados y descuenta las líneas recientes también en el desglose por tipo (la primera versión marcaba "difiere" por ese motivo). *Para el lote:* la rotación diaria de Apache ocurre a medianoche; conviene que el lote no la cruce, aunque está comprobado que no pierde eventos.
- **Ajuste:** el módulo auditd no conserva `event.created`. En Logstash se copia el `@timestamp` que trae Filebeat (su hora de lectura) a `lab.filebeat_read`, para tener las cuatro marcas en las dos fuentes. Se aplica con el reinicio de la ingesta.

**Qué falló y cómo lo resolví:** (evidencia: `results/t2/diagnostico_parseo_incorrecto_20261119.txt`)
- **Apache sin parsear:** los 20 documentos tenían `error.message: "field [event.original] already exists"`. Con `ecs_compatibility` v8, el input beats de Logstash ya copia la línea en `event.original` (tag `beats_input_codec_plain_applied`), y el pipeline del módulo apache falla al intentar hacer lo mismo. *Solución:* `lab.conf` elimina `[event][original]` de los eventos que van a un pipeline de módulo.
- **auditd mal parseado:** Ubuntu 24.04 usa `log_format = ENRICHED`, que agrega al final de cada registro, tras un separador 0x1D, los valores traducidos (`UID="root" AUID="unset"`). El módulo no lo contempla: `event.outcome` quedó como `success'␝UID="root"`, el mensaje anidado quedó partido y `user.id` tomó el auid sin asignar (4294967295). Por eso la búsqueda por la clave `lab_protegido` devolvió 0, aunque `ausearch` mostraba 2 eventos. *Solución:* `log_format = RAW`. Los nombres de usuario no se inventan: se usan los uid que da la fuente.
- **`node=(null)`:** `name_format = HOSTNAME` aplicado con SIGHUP no resolvió el nombre. *Solución:* `name_format = NONE`; el host sale de `host.name`, que pone Filebeat.
- **403 en `_cat/indices` con `lab_analyst`:** al rol le faltaba `monitor` (estadísticas de índices, solo lectura). Agregado en `setup.sh`.
- **Datos ya indexados mal:** se creó `t2_reiniciar_ingesta.sh` (rota `audit.log`, borra los índices de logs y vacía el registro de Filebeat), que además sirve para partir limpio antes del lote.
- **La verificación no encontraba eventos indexados.** Había tres causas, todas en las consultas y no en los datos:
  - (a) *Latencia:* la petición de las 02:57:46 se leyó a las 02:57:52,9 (`event.created`), llegó a Logstash a las 02:58:04,9 y se indexó 15 ms después. Fueron unos 19 s, casi todo en Filebeat, que lee con backoff de hasta 10 s y envía en lotes con espera de hasta 10 s. A eso se suman hasta 5 s de refresco del índice, y el script consultaba a los 20 s. *Solución:* esperar 45 s. *Decisión:* no ajustar Filebeat. Se mantiene la configuración por defecto, que es la realista, y se mide en la T7 (H3). La reducción queda como mejora posible.
  - (b) En los registros SYSCALL el módulo no deja `auditd.log.record_type`: el tipo queda en `event.action`.
  - (c) `event.original` está mapeado sin indexar, así que no se puede buscar por él.
- **Lo que muestran los documentos reales (para la tabla de campos):**
  - La clave de la regla queda en `auditd.log.key` y el número de serie en `auditd.log.sequence`.
  - El resultado está en `auditd.log.success` (`yes`/`no`). El código de retorno de la llamada (-13 = EACCES) queda en `process.exit_code`. ECS lo nombra así, aunque no es el código de salida del proceso: hay que aclararlo en el informe.
  - El acceso de `labuser` aparece con `user.id: 1001` y `user.audit.id: 1000` (`labadmin`). Esto **confirma con datos** que `sudo -u` conserva el auid y justifica haber filtrado las reglas por `uid`.
  - Un acceso genera varios documentos con la misma serie (SYSCALL, CWD, PATH, PROCTITLE). Esa es la agregación que hay que reconstruir.
  - Hay ruido propio del sistema: cada pocos minutos `cron` abre sesión y el núcleo emite un SYSCALL (`write`, `key=(null)`) asociado al LOGIN, sin que ninguna regla nuestra lo pida. Es actividad legítima de fondo que va a aparecer en las ventanas de la T4.
- *Lección para el informe:* el pipeline "funcionaba" (había documentos en los índices), pero los campos estaban mal. Sin comparar contra el log original y sin la búsqueda por la marca, no se habría detectado. Es justo lo que pide la consigna con "comparación con los logs originales".

**Decisiones y por qué:**
- **Reglas de auditd acotadas:** vigilancia del archivo protegido (cualquier usuario), accesos denegados (`EACCES`/`EPERM`) y `execve` solo del `uid` de `labuser`. Exclusiones de Filebeat, dockerd y containerd al principio, porque en la lista `exit` gana la primera regla que coincide. Se filtra por `uid` y no por `auid`, porque `sudo -u labuser` conserva el auid del administrador. Ninguna vigilancia de lectura sobre `/var/log/audit` (evita la realimentación con Filebeat).
- **auditd.conf:** rotación de 50 MB × 10 archivos para que no se pierdan eventos durante el lote; `name_format = HOSTNAME` para que cada registro diga de qué máquina viene.
- **Dónde se transforma cada cosa:** Filebeat solo lee y etiqueta; Logstash agrega la marca de recepción y enruta por fuente; el ingest pipeline del módulo en Elasticsearch parsea a ECS. Se reutilizan los pipelines oficiales de los módulos en lugar de escribir grok propios: están probados y producen campos ECS estándar.
- **Plantilla propia `lab`:** se exporta el mapeo ECS de Filebeat y se adapta a los índices `lab-auditd-*`, `lab-apache-*` y `lab-otros-*`, sin data stream ni ILM, con una réplica de 0 (nodo único) y las marcas `lab.*` mapeadas como fecha. Sin plantilla, los campos se mapearían por inferencia y algunos (IP, códigos, fechas) quedarían con el tipo incorrecto.
- **Pipeline final `lab-ingested`:** agrega `lab.es_ingested` en todos los documentos. No depende de que el pipeline de cada módulo complete `event.ingested`.
- **Filebeat lee solo los archivos activos:** no los rotados ni los `.gz`, para no duplicar eventos. Sigue cada archivo por su inodo aunque se renombre.

**Evidencia generada:**

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**

---

## T3 — Escenarios etiquetados

**Fecha:** 20/11/2026

**Qué hice:**
- Generadores `src/generacion/linux_actividad.py` (B1/I1) y `http_cliente.py` (B2/I2, más el sitio de prueba), el orquestador `lote.py`, `scripts/t3_setup.sh` y `t3_archivar_logs.sh`. Guía: `paso_a_paso/03_escenarios.md`.
- `t3_setup.sh` (20/11, 03:09): prueba corta de los generadores OK. Cliente HTTP con 45 peticiones (42 × 200, 3 × 404, 0 fallos de red); Apache registró la IP del contenedor (`172.30.0.5`); `linux_actividad` corrió con uid 1001 (`labuser`).
- **Piloto** (20/11, 03:13–03:26), una sesión por escenario (`data/piloto/`): **4 ok / 4**, `auditctl lost` 0 → 0 en todas.

  | Sesión | Escenario | Conjunto | Evidencia en la sesión | Evidencia del incidente |
  |---|---|---|---|---|
  | S01 | B1 | entrenamiento | 1462 | — |
  | S02 | I1 | validación | 1081 | 104 registros `lab_protegido` |
  | S03 | B2 | entrenamiento | 662 | — |
  | S04 | I2 | validación | 1956 | 256 líneas de la IP atacante 172.30.0.13 |

  En Elasticsearch: `lab_protegido` = **104**, igual a la evidencia en `audit.log` de S02 (no se perdió ningún registro del incidente). Hay **377** respuestas 404: las peticiones del atacante de S04 (hasta 256), los enlaces rotos y el favicon de los clientes benignos de S03 y S04 y, si no se reinició la ingesta antes del piloto, 3 de la prueba de `t3_setup.sh`. Es coherente; el desglose exacto por IP no se revisó porque los datos del piloto se descartan antes del lote.
- **Lote** (20/11, 03:38:21–05:51:47 hora local; 06:38–08:51 UTC, sin cruzar la rotación de medianoche de Apache): **40 ok / 40**, sin `FALLO` ni reintentos, `auditctl lost` 0 → 0 en las 40 sesiones. Evidencia en `data/lote/` (`plan.json`, `manifiesto.csv`, `consola.log`) y logs brutos archivados con `t3_archivar_logs.sh lote`.

  | Escenario | Entrenamiento | Validación | Prueba | Evidencia en la sesión (mín / mediana / máx) | Evidencia del incidente (mín / mediana / máx; total) |
  |---|---|---|---|---|---|
  | B1 | 6 | 2 | 2 | 330 / 1271 / 2063 | — |
  | B2 | 6 | 2 | 2 | 202 / 759 / 1514 | — |
  | I1 | — | 5 | 5 | 774 / 1618 / 2302 | 43 / 99,5 / 170; 1038 registros `lab_protegido` |
  | I2 | — | 5 | 5 | 870 / 1400 / 2154 | 79 / 223 / 374; 2308 líneas de la IP atacante |

  - En total, **50 794** registros o líneas de evidencia en las sesiones (lo que `lote.py` contó en los logs originales).
  - Intensidad sorteada de los incidentes en este lote: I1 entre 0,96 y 2,88 intentos/s (rango posible 0,3–3,0); I2 entre 1,16 y 7,76 peticiones/s (rango 1,0–8,0); duración entre 30,5 y 59,2 s; inicio entre los segundos 46,5 y 101,9.
  - Los casos más difíciles quedaron uno en cada conjunto de cada fuente: I1 S31 (validación, 0,96/s, 43 registros) y S14 (prueba, 1,24/s, 72 registros); I2 S32 (prueba, 1,16/s, 79 líneas) y S02 (validación, 2,81/s, 133 líneas).
  - B1 con 0–3 accesos denegados normales por sesión (solo una sesión con 0): el ruido benigno que tienen que tolerar las reglas.
  - Los atacantes de I2 tuvieron 10 IPs distintas, sorteadas en el mismo rango que los clientes benignos.

**Qué falló y cómo lo resolví:**
- Al arrancar el lote parecía colgado: estaba esperando la contraseña de `sudo` (el mensaje queda arriba de todo en tmux). Sin consecuencias.

**Decisiones y por qué:**
- **Plan reproducible fijado antes de generar datos:** `plan.json` guarda con una semilla el orden de las sesiones, sus parámetros y el **conjunto asignado** (benignas 6/2/2, incidentes 5/5 entre validación y prueba). La partición queda decidida antes de ver cualquier resultado, lo que evita elegirla a conveniencia.
- **Orden aleatorio de las sesiones:** si los escenarios se corrieran en bloques, cualquier deriva en el tiempo (índices más grandes, caché, carga) quedaría confundida con el escenario.
- **Variabilidad dentro de cada escenario:** tasa de actividad, ráfagas, errores normales, cantidad de clientes, inicio, duración e intensidad del incidente se sortean por sesión. Algunos incidentes son de baja intensidad (0,3 intentos/s o 1 petición/s), de modo que no todos deberían ser triviales de detectar (H1).
- **Benignas con ruido realista:** B1 incluye 0–3 accesos denegados normales (`/etc/shadow`, `/root`, `/etc/sudoers`) y B2 incluye 404 normales (favicon inexistente, enlaces rotos). Así ni "hubo un acceso denegado" ni "hubo un 404" alcanzan para identificar un incidente, y el detector por reglas tiene falsos positivos posibles.
- **Sin rasgos artificiales que delaten al atacante:** el cliente de I2 usa los mismos User-Agent de navegador que los benignos, y las IPs de todos los clientes se sortean en 172.30.0.10–250 por sesión. La IP del atacante queda en el manifiesto como evidencia, pero no lo identifica de antemano.
- **Incidente dentro de una sesión con actividad legítima de fondo:** el incidente ocurre entre los segundos 45 y 165, nunca al principio ni al final, y convive con actividad benigna. La ventana real (inicio y fin) la informa el propio generador con el reloj de la VM.
- **Verificación contra los logs originales, sesión por sesión:** `lote.py` lee `audit.log` y `access.log` (no Elasticsearch). En I1 exige registros `lab_protegido` del uid de `labuser` dentro de la ventana; en I2, líneas de la IP atacante en la ventana. En las benignas exige actividad de fondo, y en B1 que **no** haya `lab_protegido` (control de contaminación). Además registra `auditctl -s lost` antes y después de cada sesión.
- **Reanudable:** el manifiesto se reescribe después de cada sesión y las que quedaron `ok` no se repiten. Los generadores corren con `sudo -u labuser` (uid 1001, auid del administrador) y en contenedores de `labnet`, cuya IP Apache registra tal cual porque el tráfico va al anfitrión sin NAT.
- **Pausa de 20 s entre sesiones:** separa las ventanas de 30 s de sesiones distintas.

**Evidencia generada:**
- `data/piloto/` y `data/lote/`: plan, manifiesto (una fila por sesión con tiempos, parámetros, IPs, evidencia y `lost`) y consola del lote.
- `data/raw/lote_<fecha>/logs.tar.gz` en la VM, con su SHA-256 (no se versiona).

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**

---

## T4 — Ventanas y features

**Fecha:** 20/11/2026

**Qué hice:**
- `src/extraccion/ventanas.py`: consulta Elasticsearch como `lab_analyst`, arma 6 ventanas de 30 s por sesión `ok` del manifiesto y genera `data/procesado/ventanas_auditd.csv` (B1, I1), `ventanas_apache.csv` (B2, I2) y `diccionario_caracteristicas.md`. Guía: `paso_a_paso/04_ventanas.md`.
- Probado en Windows con un Elasticsearch simulado: 6 sesiones sintéticas, ventanas, etiquetas y validación correctas, incluidos los dos casos de borde (ventana ambigua en auditd y primera petición del atacante en la ventana anterior en Apache).
- **Corrida sobre el lote** (20/11, 17:25, `results/t4/validacion_20261120_172538.txt`): 29 462 SYSCALL, 31 957 PATH y 21 997 líneas de `access.log` del período del lote.
  - **auditd:** 120 ventanas de 20 sesiones. B1: 36/12/12 (entrenamiento, validación, prueba), todas con etiqueta 0. I1: 12 con etiqueta 1 en validación y 12 en prueba, más 18 + 18 con etiqueta 0. Ninguna ambigua.
  - **Apache:** 120 ventanas. I2: 13 con etiqueta 1 en validación y 11 en prueba; el resto con etiqueta 0.
  - **Medias por grupo:**

    | Grupo | aud_eventos | aud_fallidos | aud_denegados_proc | aud_denegados | aud_clave_protegido |
    |---|---|---|---|---|---|
    | B1 (e=0) | 212,0 | 190,2 | 130,0 | 0,35 | 0 |
    | I1 (e=0) | 235,6 | 212,7 | 151,8 | 0,11 | 0 |
    | I1 (e=1) | 316,4 | 281,2 | 137,2 | 43,8 | 43,6 |

    | Grupo | web_peticiones | web_4xx | web_rutas_4xx_distintas | web_clientes | web_max_4xx_cliente |
    |---|---|---|---|---|---|
    | B2 (e=0) | 125,9 | 7,2 | 1,9 | 1,8 | 5,1 |
    | I2 (e=0) | 193,6 | 10,6 | 2,1 | 2,2 | 6,4 |
    | I2 (e=1) | 307,0 | 108,8 | 95,3 | 3,3 | 96,2 |

  - **Validación:** los 6 recuentos dan 120/120 contra `_count` directo. Eventos del incidente: 20/20 (8 de las I1 con el +1 explicado abajo).
  - *Lectura:* en promedio, las ventanas del incidente se separan con claridad. La dificultad va a estar en las ventanas de borde (solape parcial, pocos eventos) y en los incidentes de baja intensidad (S31, S14, S32).

**Qué falló y cómo lo resolví:**
- **`aud_denegados` medía otra cosa** (primera corrida, 17:02). En B1 daba ~190 "denegados" por ventana sobre ~212 eventos, con solo 0–3 errores normales por sesión. Un diagnóstico sobre los registros crudos (`src/extraccion/diag_incidente.py --solo-denegados`, sesión S01) mostró que, de 925 SYSCALL con `success = no` en 180 s:
  - 607 eran de `ps` con EACCES sobre `/proc/<pid>/environ` de procesos de root: denegación real, pero benigna por construcción.
  - 315 eran `execve` con ENOENT de Python buscando cada comando en las carpetas del `PATH` (`/usr/local/sbin/head`, `/usr/local/bin/head`…): no son denegaciones.
  - Solo 3 eran los `cat /etc/shadow` del escenario.
  
  *Solución:* tres características en lugar de una. `aud_fallidos` (cualquier `success = no`), `aud_denegados` (EACCES o EPERM, `process.exit_code` -13 o -1, sobre archivos reales sin `/proc`) y `aud_denegados_proc`. `aud_archivos_denegados_distintos` y `aud_frac_denegados` pasan a la definición nueva. La validación agrega el total de denegaciones por código de salida contra `_count`. *Por qué no es ajustar a las etiquetas:* es una corrección de qué significa "denegación". Se decidió antes de entrenar y sin mirar el rendimiento de ningún detector, e Isolation Forest sigue viendo el ruido en su propia columna.
- **+1 registro del incidente en 8 de 10 sesiones I1** (ES vs. manifiesto de la T3). El diagnóstico mostró que es el **primer intento del incidente** (mismo proceso, `labuser`, `secreto.txt`, EACCES), fechado por auditd **1 ms antes** del `inicio_real` que informó el generador. auditd usa un reloj de grano grueso del núcleo, que puede ir unos milisegundos atrasado respecto del reloj de Python. En S08 y S16 el primer intento cayó un poco más tarde y coinciden. *Solución:* el conteo de Elasticsearch es el correcto (las etiquetas no cambian). El contraste de `ventanas.py` acepta registros a menos de 50 ms del borde y lo informa, y `lote.py` usa la misma tolerancia para la T7. El manifiesto del lote queda como está, y la diferencia queda explicada en el reporte.
- *Lección:* los conteos cuadraban contra `_count` (el pipeline era consistente consigo mismo), pero una característica no medía lo que decía su nombre. Solo se vio mirando las medias por grupo y bajando a los registros crudos.

**Decisiones y por qué:**
- **Un dataset por fuente.** auditd y Apache miden cosas distintas (eventos del núcleo vs. peticiones HTTP) y sus sesiones son distintas. Mezclarlos en una fila pondría ceros artificiales en la mitad de las columnas.
- **Ventanas de 30 s alineadas al inicio de cada sesión** (6 por sesión): una ventana nunca mezcla dos sesiones (hay 20 s de pausa entre sesiones) ni dos conjuntos, así que no hay fuga entre entrenamiento y prueba. En operación real las ventanas se alinearían al reloj (T7). Se descarta lo que llega después de los 180 s.
- **auditd: se cuentan los SYSCALL** (un SYSCALL = un evento) y los PATH se usan solo para saber qué archivo tocó cada evento (unidos por marca de tiempo y número de serie). **No se usan los registros de sudo/PAM**: en el laboratorio los produce el orquestador al lanzar los generadores con `sudo -u labuser`, también al empezar el incidente de I1. Usarlos haría que el modelo detecte cómo se lanzó el incidente y no lo que hizo.
- **Apache: solo `access.log`.** Su resolución es de 1 s.
- **Características** (17 de auditd y 14 de Apache, ver el diccionario): volumen, resultado (fallos, 4xx), recuento por regla, tipo de operación (apertura, cambio de permisos), diversidad (procesos, archivos, rutas, clientes), concentración por cliente (máximo de peticiones, de 4xx y de rutas de un mismo cliente) y ritmo (máximo por segundo, segundos activos).
- **`aud_clave_protegido` es específica del escenario:** cuenta accesos al archivo vigilado, que es justamente lo que hace I1. Es legítima, porque vigilar un archivo sensible es parte de la configuración defensiva, pero vuelve trivial la detección. Queda marcada para un análisis de ablación en la T5 (modelo sin esa columna), para ver si el resto de las características alcanza.
- **Etiqueta de ventanas con solape parcial (criterio fijado antes de entrenar):** `etiqueta = 1` si la ventana contiene al menos un evento del incidente (auditd: SYSCALL `lab_protegido`; Apache: línea de la IP atacante), aunque el solape sea parcial. Si se solapa con el intervalo del incidente pero no tiene eventos suyos (décimas de segundo en el borde), queda como `ambigua` y se excluye de las métricas por ventana. Así no se cuenta como "no detectada" una ventana en la que no había nada que detectar.
- **Sin variables que delaten la etiqueta:** sesión, escenario, conjunto, tiempos, IPs y etiqueta quedan como metadatos y no entran al modelo. No hay características de IP ni de user agent.

**Evidencia generada:**
- `data/procesado/ventanas_auditd.csv`, `ventanas_apache.csv`, `diccionario_caracteristicas.md`.
- `results/t4/validacion_20261120_170208.txt` (primera corrida, con `aud_denegados` mal definida) y `validacion_20261120_172538.txt` (la definitiva).

**Para el informe:**
- Tabla del diccionario de características (`data/procesado/diccionario_caracteristicas.md`).
- Recuento de ventanas por escenario, conjunto y etiqueta, y medias por grupo (`results/t4/validacion_<fecha>.txt`).
- Validación: cada ventana recalculada con `_count` directo a Elasticsearch, y eventos del incidente en Elasticsearch vs. evidencia en los logs originales (T3).

**Preguntas que me podrían hacer en el oral:**
- ¿Por qué 30 s? Lo fija la consigna. Además, con un incidente de 30–60 s, el incidente ocupa al menos una ventana completa o dos parciales.
- ¿Qué pasa con una ventana que toca el incidente solo una décima de segundo? Es `ambigua` y se excluye de las métricas por ventana; el incidente igual cuenta para el recall por incidente.
- ¿Por qué no usar la IP como característica? Las IPs se sortean por sesión; el modelo aprendería IPs del laboratorio y no comportamiento.
- ¿Por qué sacaron `/proc` de las denegaciones? Porque `ps` genera cientos de denegaciones benignas por sesión al listar procesos de otros usuarios, y eso ahogaba la señal. Se mantienen en su propia columna (`aud_denegados_proc`), así que Isolation Forest las ve igual; lo que cambia es que la regla A1 mide denegaciones sobre archivos.
- ¿Un evento fechado antes del inicio del incidente? El reloj de auditd es de grano grueso (1–4 ms). Es irrelevante para ventanas de 30 s, pero había que explicar la diferencia de conteo.

---

## T5 — Isolation Forest

**Fecha:** 20/11/2026

**Qué hice:**
- `src/modelos/isolation_forest.py` (entrenamiento, búsqueda, umbral, evaluación, estabilidad, guardado) y `src/evaluacion/metricas.py` (métricas comunes con la T6). Guía: `paso_a_paso/05_isolation_forest.md`.
- Probado en Windows con datasets sintéticos con la forma de la T4: corre de punta a punta y genera resumen, configuraciones, predicciones y modelos.
- **Corrida sobre el lote** (20/11, 17:29, `results/t5/resumen_20261120_172914.txt`). Entorno: Python 3.12.3, scikit-learn 1.9.1, numpy 2.5.5 (congelado en `requirements.lock`); semilla 20261120. Ventanas: 36 de entrenamiento y 42 de validación y 42 de prueba por fuente, sin ventanas ambiguas.

  | Modelo | Configuración elegida | Umbral | Validación F1 | Prueba: TP / FP / FN / TN | Prueba: precisión / recall / F1 | Incidentes en prueba | 1.ª alerta (mediana / máx.) | Estabilidad, 10 semillas: F1 · FA/h |
  |---|---|---|---|---|---|---|---|---|
  | auditd completo (17) | log1p, 300 árboles, 8 muestras, 0,6 de las características | 0,5540 | 0,960 | 9 / 1 / 3 / 29 | 0,900 / 0,750 / 0,818 | 5/5 | 32,9 / 45,4 s | 0,806 ± 0,074 · 10,6 ± 4,1 |
  | auditd sin `aud_clave_protegido` (16) | log1p, 100 árboles, muestras auto, todas las características | 0,5925 | 0,960 | 11 / 1 / 1 / 29 | 0,917 / 0,917 / 0,917 | 5/5 | 15,4 / 32,9 s | 0,883 ± 0,048 · 6,9 ± 1,4 |
  | Apache completo (14) | sin transformar, 100 árboles, muestras auto, todas (la de scikit-learn por defecto) | 0,6050 | 1,000 | 11 / 1 / 0 / 30 | 0,917 / 1,000 / 0,957 | 5/5 | 23,8 / 28,1 s | 0,983 ± 0,028 · 1,1 ± 1,9 |

  - **Umbral sin etiquetas** (máximo de entrenamiento), en prueba: auditd completo detecta 1/5 incidentes (F1 0,143); auditd sin clave, 4/5 (F1 0,667, 0 FP); Apache, 5/5 (F1 0,917, 2 FP). En auditd, sin las etiquetas de validación para calibrar el umbral, el detector casi no sirve: algunas ventanas benignas de entrenamiento ya tienen puntajes altos.
  - **Falsas alarmas por hora:** con 0,35 h de prueba por fuente, un solo FP equivale a 2,9/h. Son estimaciones con muy pocas horas y hay que decirlo así.
  - **Tiempo hasta la primera alerta (offline):** fin de la primera ventana alertada menos el inicio real del incidente. No incluye la ingesta ni la espera de la T7.

**Qué falló y cómo lo resolví:**
- **Resultado inesperado: la ablación (sin `aud_clave_protegido`) rinde mejor en prueba que el modelo completo** (F1 0,917 vs. 0,818; 3 FN vs. 1). No es un error, y se explica:
  1. Desde la T4, `aud_denegados` ya cuenta los accesos denegados al archivo protegido (EACCES de `labuser`), así que el modelo sin la clave igual ve el incidente a través de una característica genérica.
  2. La configuración del modelo completo salió con `max_samples=8` y `max_features=0,6`: árboles de 8 ventanas que ven el 60 % de las columnas. Con 8 muestras, cada árbol tiene a lo sumo 3 niveles de profundidad útil, así que el puntaje se satura: una ventana con 32 accesos denegados en 15 s (S26 v2) quedó con 0,5526, por debajo del umbral 0,5540, casi igual que ventanas benignas algo raras. Es una configuración muy ruidosa, y lo muestra la estabilidad: F1 0,806 ± 0,074 y 10,6 ± 4,1 FA/h, contra 0,883 ± 0,048 y 6,9 ± 1,4 del modelo sin la clave.
  3. Se eligió por AP en validación, con 0,979 contra 0,975 de la siguiente: la diferencia es una ventana en el ranking de 42. Con validación tan chica, el criterio de selección tiene ruido.
  
  *Qué no se hizo:* cambiar el criterio o la configuración después de ver la prueba. Eso sería ajustar a la prueba. Se informa tal cual, con la estabilidad como medida honesta de la variabilidad.
- La semilla principal dio menos FP en prueba (1) que el promedio de las 10 semillas (3,7 para auditd completo). Se informan ambos; el número representativo es el de la estabilidad.

**Decisiones y por qué:**
- **Un detector por fuente** (consigna): auditd y Apache tienen características distintas; un modelo conjunto necesitaría filas que combinen dos sesiones distintas.
- **Entrenamiento solo con ventanas benignas** (6 sesiones × 6 ventanas = 36 por fuente). Isolation Forest aprende qué es normal; no ve ningún incidente.
- **Validación para elegir; prueba para medir, una sola vez.** La división por sesiones completas está fijada en `plan.json` desde la T3.
- **Búsqueda de hiperparámetros chica (24 combinaciones):** transformación (ninguna / log1p), árboles (100 / 300), muestras por árbol (todas / 16 / 8) y fracción de características (1,0 / 0,6). Criterio: precisión promedio (AP) en validación, que no depende de un umbral. En empate gana la combinación más simple (la primera es la de scikit-learn por defecto). No se estandariza: Isolation Forest corta cada característica al azar entre su mínimo y su máximo, así que cambiar la escala no cambia nada; log1p sí cambia dónde caen los cortes.
- **Umbral con máximo F1 por ventana en validación**, ubicado a mitad de camino entre dos puntajes. Usa las etiquetas de validación, así que el ajuste es semisupervisado. Como contraste se informa un umbral sin etiquetas: el puntaje más alto de entrenamiento.
- **Ablación en auditd:** variante sin `aud_clave_protegido`, para ver si el detector encuentra el incidente sin la característica que lo nombra.
- **Estabilidad:** se repite el entrenamiento con 10 semillas (recalculando el umbral en validación) y se informa media ± desvío en prueba.
- **Explicación de cada alerta:** las 3 características más alejadas de la mediana de entrenamiento (en rangos intercuartílicos). Se calcula en el espacio del modelo (con log1p si corresponde), pero muestra el valor real de la ventana. La primera versión mostraba el valor transformado (`aud_eventos=6.41` en lugar de 611) y se corrigió después de la primera corrida; las métricas no cambian. Sirve para el análisis de falsos positivos y para el dashboard.
- **Trazabilidad:** cada variante guarda características, hiperparámetros, semilla, umbral, resultados de la búsqueda, versiones de Python, scikit-learn y numpy, y el SHA-256 del dataset usado.

**Evidencia generada:**
- `results/t5/resumen_20261120_172914.txt`; `results/t5/<fuente>_<variante>_config.json` y `_predicciones.csv`; modelos en `results/t5/modelos/*.joblib` (en la VM); `requirements.lock`.

**Para el informe:**
- La tabla de arriba (prueba con la semilla principal y estabilidad).
- Comparación del umbral calibrado en validación vs. sin etiquetas: muestra cuánto depende el detector de tener ejemplos de incidentes para calibrarse.
- La ablación y su lectura. La característica que nombra el escenario no es necesaria; alcanza con contar denegaciones bien definidas.

**Preguntas que me podrían hacer en el oral:**
- ¿Por qué el modelo sin la característica del archivo protegido anda mejor? Porque `aud_denegados` ya captura los intentos, y porque la configuración elegida para el completo era muy ruidosa (8 muestras por árbol). Con 42 ventanas de validación, la elección del hiperparámetro tiene ruido; la estabilidad con 10 semillas lo muestra.
- ¿Por qué no cambiaron la configuración después de ver eso? Porque se vio en prueba. Cambiarla sería elegir con los datos de prueba.
- ¿2,9 falsas alarmas por hora es mucho? Es 1 FP en 21 minutos de prueba: con tan pocas horas, el número es muy impreciso. En un sistema real se mediría durante días.
- ¿Por qué Isolation Forest? No necesita ejemplos de ataques para entrenar, funciona con pocas muestras y pocas características, y su idea se explica fácil: lo raro se aísla con menos cortes al azar.
- ¿El umbral no hace trampa al usar etiquetas? Usa las de validación, nunca las de prueba. Igual se informa el umbral sin etiquetas para mostrar cuánto depende de esa calibración.
- ¿Por qué el detector marca una ventana? Por las 3 características que más se apartan de lo normal (columna `explicacion` de las predicciones).
- ¿Una anomalía estadística es un incidente? No: una ráfaga legítima también es rara. Por eso se cuentan los falsos positivos por hora y se miran uno por uno.

---

## T6 — Baseline por reglas

**Fecha:** 20/11/2026

**Qué hice:**
- `src/reglas/reglas.py`: reglas A1, A2 (auditd) y W1, W2, W3 (Apache), ajuste de umbrales en validación, evaluación y comparación con Isolation Forest en las mismas ventanas de prueba. Guía: `paso_a_paso/06_reglas.md`.
- Probado en Windows con los datasets sintéticos y las predicciones de la prueba de la T5: genera reporte, umbrales, predicciones y tabla comparativa.
- **Corrida sobre el lote** (20/11; primero en Windows con los datos copiados de la VM, `reglas.py` es determinista y solo usa la biblioteca estándar). Umbrales elegidos en validación:

  | Regla | Condición | Umbral | Cómo se eligió | Sin etiquetas |
  |---|---|---|---|---|
  | A1 accesos denegados | `aud_denegados >= k` | 10 | máximo F1 en validación (1,000); un solo valor | 3 |
  | A2 archivo vigilado | `aud_clave_protegido >= 1` | 1 | fijo por definición | 1 |
  | W1 frecuencia de 4xx | `web_4xx >= k` | 27 | máximo F1 (1,000); un solo valor | 20 |
  | W2 proporción de 4xx | `web_frac_4xx >= p` y ≥ 10 peticiones | 0,1149 | máximo F1 (0,960); 3 valores empatados entre 0,10 y 0,1298 | 0,13 |
  | W3 4xx de un cliente | `web_max_4xx_cliente >= k` | 18 | máximo F1 (0,960); un solo valor | 14 |

  **Comparación en prueba, umbrales calibrados en validación** (42 ventanas por fuente, 5 incidentes):

  | Fuente | Detector | Precisión | Recall | F1 | Incidentes | 1.ª alerta (mediana) | FA/h |
  |---|---|---|---|---|---|---|---|
  | auditd | Reglas A1 o A2 | 1,00 | 1,00 | **1,00** | 5/5 | 15,1 s | 0 |
  | auditd | IF completo | 0,90 | 0,75 | 0,82 | 5/5 | 32,9 s | 2,9 |
  | auditd | Regla A1 (genérica) | 1,00 | 0,92 | **0,96** | 5/5 | 15,4 s | 0 |
  | auditd | IF sin clave protegido | 0,92 | 0,92 | 0,92 | 5/5 | 15,4 s | 2,9 |
  | Apache | Reglas W1 o W2 | 1,00 | 1,00 | **1,00** | 5/5 | 23,8 s | 0 |
  | Apache | IF completo | 0,92 | 1,00 | 0,96 | 5/5 | 23,8 s | 2,9 |

  **La misma comparación sin etiquetas** (reglas: máximo de entrenamiento + 1; IF: alerta si supera el puntaje máximo de entrenamiento):

  | Fuente | Detector | Precisión | Recall | F1 | Incidentes | FA/h |
  |---|---|---|---|---|---|---|
  | auditd | Reglas A1 o A2 | 1,00 | 1,00 | **1,00** | 5/5 | 0 |
  | auditd | IF completo | 0,50 | 0,08 | 0,14 | 1/5 | 2,9 |
  | auditd | Regla A1 (genérica) | 1,00 | 1,00 | **1,00** | 5/5 | 0 |
  | auditd | IF sin clave protegido | 1,00 | 0,50 | 0,67 | 4/5 | 0 |
  | Apache | Reglas W1 o W2 | 0,79 | 1,00 | 0,88 | 5/5 | 8,6 |
  | Apache | IF completo | 0,85 | 1,00 | **0,92** | 5/5 | 5,7 |

  - *Lectura:* con umbrales calibrados, las reglas igualan o superan a Isolation Forest en las dos fuentes, sin falsos positivos. Las dos detectan los 10 incidentes de prueba; la diferencia está en las ventanas de borde y en los FP. Isolation Forest nunca alerta antes que las reglas: en S14, S26 y S35 el IF completo alerta una ventana más tarde (32,9 / 45,1 / 45,4 s contra 2,9 / 15,1 / 15,4 s).
  - *Sin etiquetas, el cuadro cambia por fuente:* en auditd las reglas siguen perfectas (los benignos tienen 0–2 denegaciones por ventana: el máximo + 1 ya separa) y el IF cae mucho. En Apache, el IF supera a las reglas (F1 0,92 vs. 0,88): sin calibración, W2 con el máximo benigno + 0,01 dispara en ventanas benignas con varios 404.
  - Con los dos criterios, todos los detectores encuentran los 5 incidentes de Apache. Lo que cambia son las falsas alarmas y las ventanas de borde.

**Qué falló y cómo lo resolví:**
- La primera versión informaba el umbral sin etiquetas de cada regla pero no sus métricas, así que no se podía comparar con el umbral sin etiquetas de Isolation Forest (T5). Se agregó la segunda tabla (`results/t6/comparacion_sin_etiquetas.csv`), con el mismo criterio para los dos: el máximo de entrenamiento.

**Decisiones y por qué:**
- **Las reglas que nombra la consigna:** accesos denegados en auditd (A1) y frecuencia (W1) y proporción (W2) de respuestas HTTP fallidas en Apache. Se agregan dos: A2, de firma (cualquier acceso al archivo vigilado), que es lo que haría un SIEM con una vigilancia de auditd, y W3 (4xx de un mismo cliente), solo informativa.
- **Mismas ventanas, misma división, mismas métricas que Isolation Forest:** las dos cosas leen el mismo CSV de la T4 y usan `src/evaluacion/metricas.py`. La asociación alerta–incidente está definida en ese módulo antes de ver resultados de prueba.
- **Mismo criterio de umbral que Isolation Forest:** máximo F1 por ventana en validación. En empate, el punto medio del rango empatado, para dejar margen hacia los dos lados. Se informa también el umbral sin etiquetas (máximo de entrenamiento + 1).
- **W2 exige al menos 10 peticiones en la ventana** (fijado a priori): con 2 peticiones y un favicon 404, la proporción ya es 50 %.
- **Comparaciones parejas:** reglas `completo` (A1 o A2) contra IF `auditd_completo`; reglas `generico` (solo A1) contra IF `auditd_sin_clave_protegido`. En los dos pares, ambos detectores tienen la misma información.

**Evidencia generada:**

**Para el informe:**
- Tabla de reglas y umbrales con su justificación (rango empatado y referencia sin etiquetas).
- Tabla comparativa ML vs. reglas en prueba (`results/t6/comparacion_prueba.csv`) y la misma sin etiquetas (`comparacion_sin_etiquetas.csv`).
- Tabla incidente por incidente con el tiempo hasta la primera alerta de cada detector.
- Lista de falsos positivos de cada detector, para analizarlos uno por uno en la T8.

**Preguntas que me podrían hacer en el oral:**
- ¿Si las reglas andan igual o mejor, para qué el ML? La regla detecta lo que ya sabemos buscar (un archivo vigilado, muchos 404). Isolation Forest no necesita saber qué buscar, pero paga con más falsos positivos y menos explicación. La ablación muestra qué pasa cuando la regla de firma no existe.
- ¿Cómo se eligieron los umbrales? En validación, con el mismo criterio que el umbral de Isolation Forest; nunca con prueba.
- ¿Por qué un mínimo de 10 peticiones en W2? Para que una ventana casi vacía con un favicon 404 no dispare la regla.
- ¿Entonces el ML no sirve? En este laboratorio, con incidentes bien separados de lo normal y reglas que miran justo la característica correcta, la regla gana. Sin etiquetas, en Apache el IF anduvo mejor que las reglas, y no necesitó saber de antemano qué característica mirar. La ventaja del IF es no depender de saber qué buscar; su costo son las falsas alarmas y la calibración del umbral.
- ¿No es injusto calibrar las reglas con etiquetas? Se calibraron igual que el IF (máximo F1 en validación), y la tabla sin etiquetas muestra los dos sin esa ayuda.

---

## T7 — Alertas y evaluación temporal

**Fecha:** 20/11/2026

**Qué hice:**
- `src/deteccion/detector_vivo.py` (detector en vivo con medición de recursos) y `src/deteccion/cronologia.py` (cronología, latencia por tramo, completitud, métricas en vivo y resumen de CPU/RAM). Se agregó `--alinear 30` a `lote.py`. Guía: `paso_a_paso/07_vivo.md`.
- Probado en Windows con un Elasticsearch simulado, latencias de ingesta realistas (lectura 0–3 s, a veces ~10 s; envío 0–10 s) y los modelos y umbrales de las pruebas de T5/T6. Con 15 s de espera llegaron tarde ~0,5 % de los eventos; con 30 s, ninguno.
- **Prueba en vivo** (20/11, 18:10:45–18:27:45 hora local, 21:10–21:27 UTC; `results/t7/vivo_20261120_181045`, reporte `cronologia_20261120_182948.txt`): detector durante 17 min y 4 sesiones nuevas (`data/vivo/`, semilla 20261121), **4 ok / 4**, alineadas a :00 y :30 (S01 I2, S02 I1, S03 B2, S04 B1). Reloj: chrony con 0,06 ms de desfase respecto de NTP.
  - **Métricas en vivo** (12 ventanas de sesión por fuente):
    - auditd: los 4 detectores (IF completo, IF sin clave, A1, A2) con TP=2, FP=0, FN=0; incidente detectado.
    - Apache: IF con TP=2, FP=1, FN=1; reglas (W1, W2, W3) con TP=1, FP=0, FN=2. Todos detectan el incidente.
  - **Cronología** (t = 0 es el inicio real del incidente):

    | Incidente | Detector | Primer evento | Indexado | Fin de la ventana alertada | ALERTA | Espera | Procesamiento |
    |---|---|---|---|---|---|---|---|
    | S01 I2 | IF Apache | −0,5 s* | 10,4 s | 5,5 s | **35,5 s** | 30 s | 0,06 s |
    | S01 I2 | Reglas W1 o W2 | −0,5 s* | 10,4 s | 35,5 s | **65,5 s** | 30 s | 0,05 s |
    | S02 I1 | IF auditd completo | 0,0 s | 8,1 s | 21,4 s | **51,4 s** | 30 s | 0,06 s |
    | S02 I1 | Reglas A1 o A2 | 0,0 s | 8,1 s | 21,4 s | **51,4 s** | 30 s | 0,06 s |

    *Apache registra al segundo: el primer evento queda con la hora redondeada hacia abajo.
  - **En S01 (I2), Isolation Forest alertó una ventana antes que las reglas** (35,5 s contra 65,5 s). El incidente empezó 5,5 s antes del fin de la ventana 21:11:30–21:12:00, que tuvo 21 respuestas 4xx (13 del atacante). Eso no alcanzó el umbral de W1 (27) pero sí volvió rara la ventana para el IF (puntaje 0,621, umbral 0,605). En cambio, la última ventana del incidente (17 4xx) quedó apenas por debajo (0,593) y fue el FN del IF.
  - **Latencia de ingesta de todos los eventos de la prueba** (mediana / p95 / máximo, en s):

    | Tramo | auditd (2274 eventos) | Apache (1688) |
    |---|---|---|
    | Lectura (generación → Filebeat) | 0,68 / 5,32 / 9,90 | 0,82 / 5,84 / 9,85 |
    | Envío (Filebeat → Logstash) | 8,09 / 10,14 / 10,21 | 6,90 / 10,13 / 11,32 |
    | Indexación (Logstash → ES) | 0,03 / 0,07 / 0,12 | 0,01 / 0,05 / 0,09 |
    | **Total** | **8,71 / 15,39 / 17,77** | **7,93 / 14,00 / 19,98** |

    El tramo que más pesa es Filebeat → Logstash (~8 s de mediana, techo de ~10 s), compatible con que Filebeat junta los eventos en su cola en memoria y los despacha por lotes con un tiempo máximo de espera. Se dejó la configuración por defecto, y es la principal palanca para bajar la latencia.
  - **Completitud:** 0 de 2221 eventos de auditd y 0 de 1669 de Apache llegaron después de la consulta. Con 30 s de espera y un máximo de ~20 s de ingesta, el detector vio todas las ventanas completas, con al menos 23 s de margen en las ventanas alertadas.
  - **Recursos** (CPU en % de un núcleo, media / máximo; memoria en MiB, media):
    - Elasticsearch: 4,6 / 37,7 %, 2996 MiB.
    - Logstash: 2,0 / 39,0 %, 1008 MiB.
    - Kibana: 1,4 / 6,4 %, 1224 MiB.
    - Filebeat: 0,1 / 0,4 %, 137 MiB.
    - Apache, auditd y el detector: ≤ 0,5 % de CPU; el detector, 162 MiB.
    - VM entera: 2,8 % de media y 7,7 % de máximo de 4 núcleos, con ~2,2 GB de memoria libre de 8 GB.
    - El costo lo pone el stack ELK, sobre todo en memoria; el detector y la recolección son marginales.
  - **Alertas fuera de las sesiones:** IF auditd completo 20, IF auditd sin clave 5 e IF Apache 1. Son las pausas y las ventanas en que solo estaba activa la otra fuente. Es el mismo efecto de la VM en reposo.

**Qué falló y cómo lo resolví:**
- **Primera corrida en vivo sin sesiones** (20/11, 17:46–18:02, `results/t7/vivo_20261120_174604`, cortada a mano): el detector corrió solo, sin lanzar las sesiones, por una indicación ambigua de la guía (ya corregida: las sesiones se lanzan apenas arranca el detector). No sirve para la cronología, pero dejó dos datos:
  - El detector funciona en la VM: 32 ventanas procesadas cada 30 s, con 0,03–0,12 s de procesamiento.
  - **Con la VM en reposo (0 eventos), `IF_auditd_completo` alertó en todas las ventanas.** `IF_auditd_sin_clave_protegido` solo alertó en una, con 1 evento; las reglas y el IF de Apache, en ninguna. El modelo aprendió la "actividad normal del usuario de prueba" (unos 200 eventos por ventana), no el "sistema normal": una ventana vacía le resulta tan rara como un ataque. En una operación real habría que entrenar también con períodos inactivos o no evaluar ventanas sin actividad. Es una limitación para el informe, y muestra que la novedad no siempre es amenaza.
- (Prueba local) La primera versión de `cronologia.py` recalculaba las ventanas alineadas al inicio de cada sesión, que arranca unos milisegundos después del borde de 30 s. Una línea de Apache registrada justo en el segundo del borde caía en ventanas distintas y parecía un evento "llegado tarde". Se redondea el inicio de la sesión al múltiplo de 30 s, así se recalculan exactamente las mismas ventanas que vio el detector.

**Decisiones y por qué:**
- **Consulta periódica a Elasticsearch, no lectura de archivos:** el detector usa lo mismo que el analista (los índices) con el usuario de mínimo privilegio, y la latencia medida incluye todo el camino de ingesta.
- **Ventanas alineadas al reloj** (:00 y :30): en operación no hay "sesiones". Para la prueba, `lote.py --alinear 30` arranca cada sesión en un borde, así sus ventanas coinciden con las del detector y con las del entrenamiento.
- **Espera de 30 s después del fin de cada ventana:** la ingesta medida en la T2 fue de ~13–19 s, más hasta 5 s de refresco del índice. Esperar menos alerta antes pero arriesga ventanas incompletas. El costo de esa decisión se mide (completitud) en lugar de suponerlo.
- **Solo eventos de la ventana:** la decisión no usa nada posterior al fin de la ventana. La alerta más temprana posible es *fin de ventana + espera + procesamiento*.
- **Un solo reloj:** generadores, auditd, Apache, Filebeat, Logstash, Elasticsearch y el detector corren en la misma VM, sincronizada por NTP (chrony; el detector guarda el estado del reloj al empezar). No hay desfase entre equipos que corregir.
- **Marcas registradas:** inicio real del incidente (lo informa el generador), generación del evento (`@timestamp`), lectura de Filebeat, recepción en Logstash, indexación, fin de ventana, consulta y emisión de la alerta. Cada tramo se mide por separado.
- **Alertas en un índice propio** (`lab-alertas-*`, el único donde escribe `lab_analyst`) para verlas en Kibana junto con los eventos (T8). Los umbrales y puntajes se escriben como decimales para que el mapeo dinámico no los fije como enteros.
- **CPU y memoria cada 10 s:** auditd, Filebeat y Apache (por `/proc`), contenedores de Elasticsearch, Logstash y Kibana (`docker stats`), el propio detector y el total de la VM.

**Evidencia generada:**
- `results/t7/vivo_20261120_181045/` (`meta.json`, `ventanas.csv`, `alertas.jsonl`, `recursos.csv`, `cronologia.csv`, `latencias.csv`, `cronologia_20261120_182948.txt`) y `data/vivo/` (plan y manifiesto). Corridas descartadas: `vivo_20261120_174011` y `vivo_20261120_174604` (sin sesiones).

**Para el informe:**
- Gráfico de la cronología de un incidente: inicio → primer evento → indexado → fin de ventana → consulta → alerta.
- Tabla de latencia de ingesta por tramo (mediana, p95, máximo) y por fuente.
- Tabla de CPU y memoria por componente.
- Captura de Kibana con las alertas (`informe/figuras/t7_kibana_alertas.png`).
- Declarar que la evaluación de T5/T6 es **offline** (sobre datos ya indexados) y que la T7 es la prueba **en vivo** con el sistema funcionando.

**Preguntas que me podrían hacer en el oral:**
- ¿Cuánto tarda en alertar y de qué depende? De la ventana (hasta 30 s) y de la espera (30 s); el procesamiento son décimas de segundo, y la ingesta corre en paralelo.
- ¿Por qué no alertar evento por evento? El modelo y las reglas trabajan sobre recuentos por ventana; una regla por evento (p. ej. A2) podría alertar en segundos, pero un detector de anomalías necesita contexto.
- ¿Por qué en vivo el IF detectó el incidente web antes que las reglas? El incidente empezó en los últimos 5 s de una ventana. Esa ventana tenía pocos 404 del atacante para el umbral de W1, pero la combinación (más 4xx, concentrados en un cliente, más rutas distintas) ya la hacía rara. El umbral fijo de la regla no mira esa combinación.
- ¿De dónde salen los ~8 s de ingesta? Sobre todo de Filebeat → Logstash: Filebeat agrupa eventos antes de enviarlos. Elasticsearch indexa en centésimas de segundo.
- ¿Una sola prueba en vivo alcanza? Es una demostración de funcionamiento y de los tiempos (un incidente por fuente), no una estimación estadística. Las métricas de detección salen de la evaluación offline (T5/T6).
- ¿Cómo sé que los relojes están sincronizados? Todo corre en la misma VM con el mismo reloj; además, chrony informa el desfase respecto de NTP.

---

## T8 — Evaluación y dashboards

**Fecha:** 20/11/2026

**Qué hice:**
- `src/evaluacion/evaluar.py`: regenera desde los resultados de T2–T7 la tabla comparativa, las matrices de confusión, los incidentes uno por uno, los falsos positivos con su explicación, el resumen por escenario, la estabilidad de IF, la cronología y la latencia en vivo, CPU/RAM y pérdidas. Salida: `analysis/evaluacion.md`, `analysis/tablas/`, `analysis/figuras/`.
- `src/evaluacion/indexar_alertas.py`: carga las alertas offline en `lab-alertas-offline` (con `_id` fijo, sin duplicar) para verlas en el dashboard junto a los eventos del lote.
- Guía `paso_a_paso/08_evaluacion.md`: recuento de pérdidas sobre el lote, dashboard de 6 paneles en Kibana y su exportación en NDJSON por la API de Saved Objects.
- Probado en Windows con las salidas sintéticas de las pruebas de T4–T7: genera el informe, las 8 tablas y las 7 figuras.
- **Corrida real** (21/11, 00:43–01:22):
  - **Recuento de pérdidas** sobre el lote y la prueba en vivo: ver "Qué falló" (0 eventos perdidos).
  - **Alertas offline:** `indexar_alertas.py` cargó 195 alertas en `lab-alertas-offline`; una segunda corrida dio "0 nuevas, 195 ya estaban" (no duplica).
  - **Dashboard** «SOR2 E3 — Detección de anomalías» con el rango del lote (20/11, 03:35–06:00), seis paneles: volumen por fuente, denegaciones de auditd por ejecutable (se ve el fondo de `ps` y encima `cat`, `cp` y `python3` en los incidentes), códigos HTTP (picos de 404 en I2), peticiones por cliente, alertas por detector y tabla detector × fuente × sesión.
  - **Exportación NDJSON** por la API de Saved Objects (`dashboards/sor2_e3_dashboard.ndjson`): 5 objetos (el dashboard y 4 vistas de datos; las visualizaciones de Lens quedan dentro del dashboard), `missingRefCount: 0`, sin contraseñas.
  - **Evaluación final** (`analysis/evaluacion.md`, 9 tablas y 7 figuras): idéntica a la vista previa con la que se redactó la sección 7 del informe; las 7 tablas comparadas coinciden.

**Qué falló y cómo lo resolví:**
- **Recuento de pérdidas al día siguiente del lote** (21/11, 00:43, `results/t8/recuentos_20261121_004357.txt`):
  - *Problema:* `validar_ingesta.py` solo comparaba el log activo. A medianoche `logrotate` había rotado `access.log`, y las líneas del lote estaban en `access.log.1`: la pérdida de Apache del lote no se habría verificado y el resultado habría dicho "0 faltan" igual. *Solución:* compara también el archivo rotado, desde el primer documento de Elasticsearch (probado con un caso con una línea faltante a propósito).
  - *Resultado:* Apache 26 350 líneas, 26 350 documentos, 0 faltan, 0 errores (incluye el lote, leído de `access.log.1`). auditd 137 194 líneas: 21 "faltan" y 15 documentos con error de parseo.
  - *Diagnóstico* (opción nueva `--detalle`, `results/t8/detalle_20261121_004603.txt`), ninguna línea cae en una sesión:
    - **15 = los 15 documentos con error:** registros de los tres arranques de la VM (17:00, 20:47 y 00:21 del 20–21/11): `DAEMON_START` de auditd, `AVC` de AppArmor y `TRUSTED_APP` de snapd, cinco por arranque. Llegaron a Elasticsearch, pero el pipeline del módulo auditd no puede separar sus pares clave=valor (`does not contain value_split`) y los guarda sin `event.original`, así que el script no puede comparar su texto y los cuenta también como faltantes. No afectan a la detección: las ventanas usan solo SYSCALL y PATH.
    - **6 del instante del reinicio de la ingesta** (20/11 03:33:45, antes del lote): el `sudo` de `t2_reiniciar_ingesta.sh` y el `SERVICE_STOP` de Filebeat, escritos en el log viejo justo antes de rotarlo, que el reinicio descarta a propósito. Aparecieron porque la comparación del archivo rotado redondeaba la hora de auditd al segundo. *Solución:* compara con los milisegundos de auditd.
  - *Corrida definitiva* (21/11, 00:48, `results/t8/recuentos_20261121_004838.txt`): auditd 137 249 líneas y 137 249 documentos, faltan 15 = los 15 documentos con error sin `event.original`, 0 de más; Apache access 26 350 / 26 350, 0 faltan, 0 errores; Apache error 2 líneas (81 documentos de `error.log.1`).
  - *Conclusión para el informe:* 0 eventos perdidos en el lote y en la prueba en vivo; 15 registros de arranque del sistema (0,011 %) mal parseados por el módulo, ajenos a las reglas del laboratorio.

**Decisiones y por qué:**
- **Todo se regenera con un script** (consigna): ningún número del informe se copia a mano. Si cambia un resultado, se vuelve a correr `evaluar.py`.
- **Deduplicación por episodios:** alertas de un detector en ventanas consecutivas de una sesión = una alerta para el analista. Se informan las falsas alarmas por hora por ventana y por episodio.
- **Tolerancia 0:** una alerta posterior al incidente no lo detecta. La etiqueta por ventana ya incluye el solape parcial, así que una tolerancia extra contaría como acierto la alerta de una ventana sin nada del incidente.
- **Resultados separados por fuente** en todas las tablas; los incidentes no detectados aparecen marcados con su intensidad, para explicar por qué fallaron.
- **Alertas offline con `@timestamp` = fin de la ventana:** es el primer momento en que podían emitirse, así el dashboard las muestra donde las vería un analista.
- **Dashboard armado en la interfaz y exportado por API:** escribir a mano el NDJSON de Lens es frágil entre versiones; exportarlo desde Kibana 9.5.6 garantiza que se pueda importar en la misma versión.

**Evidencia generada:**
- `results/t8/recuentos_20261121_004838.txt` (definitivo) y `detalle_20261121_004603.txt` (diagnóstico de las líneas faltantes y con error).
- `analysis/` (evaluación, tablas y figuras), `dashboards/sor2_e3_dashboard.ndjson` e `informe/figuras/t8_dashboard.png`.

**Para el informe:**
- `analysis/evaluacion.md` completo: secciones 7 (resultados) y 8 (conclusiones) del informe.
- Figuras: matrices de confusión, puntajes de IF con el umbral, comparación, cronología en vivo, latencia por tramo y CPU.
- Captura del dashboard (`informe/figuras/t8_dashboard.png`; las capturas sueltas de cada panel quedan en `informe/figuras/t8_capturas/`) y `dashboards/sor2_e3_dashboard.ndjson`.

**Preguntas que me podrían hacer en el oral:**
- ¿Por qué precisión por ventana y recall por incidente? Al analista le importa no perderse incidentes (recall por incidente) y no recibir alertas falsas (precisión y falsas alarmas por hora); el F1 por ventana mide además cuánto del incidente se cubrió.
- ¿Qué incidentes no se detectaron y por qué? Ver la tabla 2 de `evaluacion.md`: se cruza con la intensidad del incidente.
- ¿Diferencia entre anomalía estadística e incidente? Los falsos positivos de IF son ventanas raras pero legítimas (p. ej. ráfagas o varios errores normales juntos); la tabla 3 los muestra con su explicación.
