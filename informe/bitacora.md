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

**Fecha:**

**Qué hice:**

**Qué falló y cómo lo resolví:**

**Decisiones y por qué:**

**Evidencia generada:**

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**

---

## T3 — Escenarios etiquetados

**Fecha:**

**Qué hice:**

**Qué falló y cómo lo resolví:**

**Decisiones y por qué:**

**Evidencia generada:**

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**

---

## T4 — Ventanas y features

**Fecha:**

**Qué hice:**

**Qué falló y cómo lo resolví:**

**Decisiones y por qué:**

**Evidencia generada:**

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**

---

## T5 — Isolation Forest

**Fecha:**

**Qué hice:**

**Qué falló y cómo lo resolví:**

**Decisiones y por qué:**

**Evidencia generada:**

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**

---

## T6 — Baseline por reglas

**Fecha:**

**Qué hice:**

**Qué falló y cómo lo resolví:**

**Decisiones y por qué:**

**Evidencia generada:**

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**

---

## T7 — Alertas y evaluación temporal

**Fecha:**

**Qué hice:**

**Qué falló y cómo lo resolví:**

**Decisiones y por qué:**

**Evidencia generada:**

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**

---

## T8 — Evaluación y dashboards

**Fecha:**

**Qué hice:**

**Qué falló y cómo lo resolví:**

**Decisiones y por qué:**

**Evidencia generada:**

**Para el informe:**

**Preguntas que me podrían hacer en el oral:**
