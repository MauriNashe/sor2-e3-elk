# Detección de anomalías de seguridad en logs auditd y Apache con ELK e Isolation Forest

Trabajo Final Integrador — Sistemas Operativos y Redes II (UNGS, 2026) — Consigna E3, Fase 1.

**Pregunta de investigación:** ¿en qué medida un detector de anomalías basado en Isolation Forest, aplicado a
registros de auditd y Apache centralizados con ELK, identifica incidentes conocidos frente a un detector
basado en reglas, considerando la tasa de detección, las falsas alarmas y el tiempo hasta la primera alerta?

## Estado

| Tarea | Estado |
|---|---|
| T1 Infraestructura | En curso: repo y configuración listos, falta desplegar en la VM |
| T2 Ingesta y normalización | Pendiente |
| T3 Escenarios etiquetados | Pendiente |
| T4 Ventanas y features | Pendiente |
| T5 Isolation Forest | Pendiente |
| T6 Baseline por reglas | Pendiente |
| T7 Alertas y latencia | Pendiente |
| T8 Evaluación y dashboards | Pendiente |

## Arquitectura

Todo corre en **una VM Ubuntu Server 24.04 LTS**. auditd, Apache y Filebeat están instalados en la VM. El stack
ELK y el cliente HTTP generador corren en Docker dentro de esa misma VM. Al haber un único reloj, las
latencias (incidente → evento → ingesta → alerta) se miden sin depender de sincronizar equipos.

```
 Windows (host)                         VM Ubuntu 24.04 — host-only 192.168.56.10
┌──────────────────┐                  ┌───────────────────────────────────────────────────┐
│ Navegador ───────┼── :5601 ───────► │ Kibana (Docker)                                   │
│ SSH / editor ────┼── :22 ─────────► │                                                   │
└──────────────────┘                  │  contenedor "cliente" ──HTTP──► Apache :80        │
                                      │  labuser (escenarios) ────────► archivos / auditd │
                                      │  audit.log, access.log, error.log                 │
                                      │        │                                          │
                                      │   Filebeat ──► Logstash :5044 (127.0.0.1)         │
                                      │                    │                              │
                                      │              Elasticsearch :9200 (127.0.0.1)      │
                                      │                    ▲                              │
                                      │     Python: extracción, IF, reglas, detector      │
                                      └───────────────────────────────────────────────────┘
```

| Componente | Versión | Dónde | Puerto expuesto |
|---|---|---|---|
| Elasticsearch | 9.5.6 | Docker | `127.0.0.1:9200` |
| Logstash | 9.5.6 | Docker | `127.0.0.1:5044` |
| Kibana | 9.5.6 | Docker | `192.168.56.10:5601` |
| Filebeat | 9.5.6 | VM (paquete apt, versión retenida) | — |
| auditd, Apache 2.4 | Los de Ubuntu 24.04 | VM | Apache: 80 (red host-only) |

### Seguridad

- Elastic con autenticación obligatoria. Cada componente usa su propio usuario con mínimo privilegio:

  | Usuario | Uso | Permisos |
  |---|---|---|
  | `elastic` | Administración: Kibana UI, setup, `filebeat setup` | Superusuario |
  | `kibana_system` | Kibana → ES | Rol interno de Kibana |
  | `logstash_internal` | Logstash → ES | Solo **crear** documentos en `lab-*`; no lee ni borra |
  | `lab_analyst` | Scripts de Python | Lee `lab-*`; escribe solo en `lab-alertas*` |

- Las contraseñas solo están en `.env`, que está en `.gitignore`. El repo lleva `.env.example` con valores de ejemplo.
- Docker publica los puertos con iptables propio, **sin pasar por ufw**. Por eso cada puerto está atado a una IP
  concreta en `docker-compose.yml`, y ufw queda como segunda barrera para los servicios de la VM (SSH, Apache).
- No hay TLS entre componentes. Elastic lo permite en nodo único, y se declara como limitación del laboratorio.

## Reproducción paso a paso

> Versión corta, solo comandos con su resultado esperado: [PASO_A_PASO.md](PASO_A_PASO.md).

### 1. Crear la VM (Hyper-V)

Configuración usada en el laboratorio de referencia:

| Parámetro | Valor |
|---|---|
| Anfitrión | Windows 11 Pro for Workstations · AMD Ryzen 5 5600 (6 núcleos/12 hilos) · 16 GB de RAM · Integridad de memoria (VBS/HVCI) activa |
| Hipervisor | Hyper-V (rol de Windows) |
| ISO | `ubuntu-24.04.5-live-server-amd64.iso` ([releases.ubuntu.com/24.04](https://releases.ubuntu.com/24.04/); verificar con `SHA256SUMS`) |
| VM | Generación 2, arranque seguro con la plantilla *Microsoft UEFI Certificate Authority* |
| Memoria | 8 GB **fija** (memoria dinámica desactivada). Con 10 GB Hyper-V no pudo arrancar la VM: necesita esa memoria libre de una vez y el anfitrión tenía ~9,9 GB libres |
| Procesadores | 4 vCPU |
| Disco | VHDX dinámico de 40 GB |
| Red | Switch **interno** `LabSwitch`: Windows en `192.168.56.1/24`, con NAT de Windows (`LabNAT`) para la salida a internet |
| IP de la VM | `192.168.56.10/24` fija, gateway `192.168.56.1`, DNS `1.1.1.1` y `8.8.8.8` |
| Nombre de máquina | `sor2-lab` |

> **Por qué Hyper-V y no VirtualBox:** con Integridad de memoria activa, el hipervisor de Windows está siempre
> encendido. VirtualBox no puede usar AMD-V directamente y corre sobre Hyper-V en un modo lento (NEM). En la
> primera prueba, la VM se colgó al descomprimir las imágenes de Docker. Hyper-V convive con esa protección sin
> desactivarla.

Pasos:

1. Habilitar Hyper-V (PowerShell como administrador) y reiniciar:
   `Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All`
2. Crear la red y la VM con [`scripts/hyperv_crear_vm.ps1`](scripts/hyperv_crear_vm.ps1) (PowerShell como administrador; leerlo antes):
   `powershell -ExecutionPolicy Bypass -File .\scripts\hyperv_crear_vm.ps1`
3. `Start-VM sor2-lab; vmconnect.exe localhost sor2-lab` y, en el instalador de Ubuntu:
   - **Red:** `eth0` en *Manual*: subred `192.168.56.0/24`, dirección `192.168.56.10`, gateway `192.168.56.1`, DNS `1.1.1.1,8.8.8.8`.
   - **Almacenamiento:** llevar `ubuntu-lv` al tamaño máximo.
   - **SSH:** marcar **Install OpenSSH server** (con la barra espaciadora).
   - **Featured server snaps:** no marcar nada. Docker se instala después desde el repositorio oficial.
4. Antes de reiniciar al final de la instalación, quitar la ISO: `Set-VMDvdDrive -VMName sor2-lab -Path $null`.
5. Si la IP no quedó fija en el instalador, ver [`scripts/netplan-hostonly.example.yaml`](scripts/netplan-hostonly.example.yaml).
6. Desde Windows: `ssh labadmin@192.168.56.10`. Si antes hubo otra VM en esa IP, primero `ssh-keygen -R 192.168.56.10`.

### 2. Llevar el repo a la VM

La opción recomendada es un repositorio Git privado y `git clone` en la VM. Como alternativa, desde PowerShell en Windows:

```powershell
scp -r .\sor2-e3-elk-ml <usuario>@192.168.56.10:~/
```

### 3. Preparar el sistema

```bash
cd ~/sor2-e3-elk-ml
less scripts/vm_setup.sh          # leerlo antes de correrlo como root
sudo bash scripts/vm_setup.sh
exit                              # volver a entrar para usar docker sin sudo
```

### 4. Configurar credenciales y levantar ELK

```bash
cd ~/sor2-e3-elk-ml
cp .env.example .env && chmod 600 .env
# una contraseña aleatoria por variable, sin mostrarlas en pantalla
for v in ELASTIC_PASSWORD KIBANA_PASSWORD KIBANA_ENCRYPTION_KEY LOGSTASH_INTERNAL_PASSWORD ANALYST_PASSWORD; do
  sed -i "s|^$v=.*|$v=$(openssl rand -hex 16)|" .env
done
grep -c '=cambiar' .env                            # debe dar 0
docker compose up -d
docker compose ps -a                               # setup: Exited (0); es01, kibana, logstash: healthy
docker compose logs setup                          # debe terminar en "[setup] Listo."
```

### 5. Pruebas e inventario (evidencia de la T1)

```bash
bash scripts/t1_pruebas.sh        # -> results/t1/pruebas_<fecha>.txt
bash scripts/t1_inventario.sh     # -> results/t1/inventario_<fecha>.txt
```

Comprobaciones manuales, para capturas:

- Navegador en Windows → `http://192.168.56.10:5601`, entrar con `elastic`. En **Dev Tools**, ejecutar `GET lab-test/_search`.
- Desde PowerShell en Windows, Elasticsearch no tiene que responder:
  ```powershell
  Test-NetConnection 192.168.56.10 -Port 9200    # TcpTestSucceeded : False
  Test-NetConnection 192.168.56.10 -Port 5601    # TcpTestSucceeded : True
  ```

### 6. Entorno de Python (para T4 en adelante)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip freeze > requirements.lock
```

## Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `es01` se reinicia y en el log aparece `max virtual memory areas vm.max_map_count [65530] is too low` | Falta `vm.max_map_count=262144`. Ejecutar `scripts/vm_setup.sh` o `sudo sysctl -w vm.max_map_count=262144` |
| `es01` termina con código 137 | Falta memoria: subir la RAM de la VM o bajar `ES_HEAP`/`ES_MEM_LIMIT` en `.env` |
| `setup` termina con error de contraseña | Las contraseñas deben ser alfanuméricas y de 12 caracteres o más |
| Kibana muestra "Kibana server is not ready yet" | Esperar 1–2 minutos y revisar `docker compose logs kibana` |
| Kibana no abre desde Windows | `LAB_IP` en `.env` tiene que coincidir con la IP host-only real (`ip -br addr`) |
| Volver a empezar de cero | `docker compose down -v` (**borra los índices**) y luego `docker compose up -d` |

## Estructura del repositorio

```
configs/elasticsearch/   setup.sh: roles y usuarios de mínimo privilegio
configs/logstash/        pipeline beats -> Elasticsearch (lab-<módulo>-AAAA.MM.DD)
configs/filebeat/        configuración de Filebeat (T2)
configs/auditd/          reglas de auditd del laboratorio (T2/T3)
scripts/                 preparación de la VM, pruebas e inventario
src/generacion/          generadores de escenarios B1, B2, I1, I2 (T3)
src/extraccion/          consultas a ES y ventanas de 30 s (T4)
src/modelos/             Isolation Forest (T5)
src/reglas/              baseline por reglas (T6)
src/deteccion/           detector incremental y alertas (T7)
data/                    manifiesto de sesiones, datasets (los logs brutos no se versionan)
analysis/                métricas, tablas y gráficos regenerables (T8)
results/                 salidas de pruebas, predicciones y alertas
dashboards/              Saved Objects de Kibana en NDJSON (T8)
informe/                 informe, figuras y referencias
```
