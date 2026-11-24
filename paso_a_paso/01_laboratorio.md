# 01 — Laboratorio (T1: infraestructura)

Guía corta para montar el laboratorio: cada paso tiene qué hace, el comando y qué debería devolver.
Siguiente guía: [02 — Ingesta](02_ingesta.md).
Las explicaciones y decisiones están en el [README](../README.md) y en [informe/bitacora.md](../informe/bitacora.md).

**Dónde se ejecuta cada comando:**
- 🪟 **PowerShell en Windows** (el equipo anfitrión).
- 🐧 **Dentro de la VM**, conectado por SSH (`labadmin@sor2-lab`).

> Si un comando de la VM se pega en PowerShell, falla con errores como *"El token '&&' no es un separador de instrucciones válido"*. Primero hay que entrar a la VM con `ssh`.

---

## T1 — Infraestructura

> **Hipervisor: Hyper-V.** Se probó primero con VirtualBox, pero en este Windows el hipervisor está activo
> (lo usa *Integridad de memoria*). VirtualBox cae entonces en un modo lento sobre Hyper-V y la VM se colgó al
> descargar las imágenes de Docker. Ver la bitácora de la T1.

### 0. Habilitar Hyper-V (una sola vez) 🪟 *como administrador*

Instala el rol de Hyper-V y sus herramientas en Windows.

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
```

**Resultado:** termina pidiendo reiniciar. Hay que reiniciar Windows.

> Si VirtualBox se usó antes, hay que eliminar su red host-only, porque ocupa la IP `192.168.56.1`:
> VirtualBox → *Archivo → Herramientas → Administrador de red* → seleccionarla → *Eliminar*.

### 1. Crear la red y la VM 🪟 *como administrador*

Crea el switch interno `LabSwitch`, le da a Windows la IP `192.168.56.1`, configura la NAT para salir a internet y crea la VM `sor2-lab`: generación 2, 8 GB de RAM fija, 4 vCPU, disco VHDX dinámico de 40 GB e ISO de Ubuntu Server 24.04.5 cargada.

```powershell
cd C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\hyperv_crear_vm.ps1
```

**Resultado:** los pasos `== 1` a `== 4` y un resumen con `Generation : 2`, `ProcessorCount : 4`, `MemoriaGB : 8` y `RAMDinamica : False`. Si falla por la IP `192.168.56.1`, falta eliminar la red de VirtualBox (paso 0).

> Si `Start-VM` responde *"no tiene memoria suficiente"*, Hyper-V no encontró libre toda la RAM fija de la VM. Cerrar programas o bajar la memoria (con la VM apagada): `Set-VMMemory -VMName sor2-lab -StartupBytes 8GB`.

### 2. Instalar Ubuntu Server

Arranca la VM y abre su consola:

```powershell
Start-VM sor2-lab; vmconnect.exe localhost sor2-lab
```

En el instalador, sin comandos:
- **Tipo de instalación:** *Ubuntu Server* (no la versión minimized), sin drivers de terceros.
- **Red:** hay **una sola** interfaz (`eth0`). Ponerla en Manual: subred `192.168.56.0/24`, dirección `192.168.56.10`, **gateway `192.168.56.1`** (Windows hace la NAT) y name servers `1.1.1.1,8.8.8.8`.
- **Almacenamiento:** disco completo con LVM. Editar `ubuntu-lv` y llevarlo al **tamaño máximo** (el instalador deja la mitad libre).
- **Perfil:** nombre de máquina `sor2-lab`, usuario `labadmin`.
- **Ubuntu Pro:** *Skip*. **SSH:** marcar *Install OpenSSH server*. **Snaps:** ninguno.

Al terminar, antes de *Reboot now*, quitar la ISO y hacer que la VM arranque desde el disco. Si no, vuelve a arrancar el instalador (🪟 como administrador):

```powershell
Set-VMDvdDrive -VMName sor2-lab -Path $null
```

```powershell
Set-VMFirmware -VMName sor2-lab -FirstBootDevice (Get-VMHardDiskDrive -VMName sor2-lab)
```

**Resultado:** al reiniciar, la consola muestra `Ubuntu 24.04.5 LTS sor2-lab tty1` y las huellas de las claves SSH.

> Si ya se reinició con la ISO puesta y apareció de nuevo el instalador, no hay que reinstalar: ejecutar los dos comandos de arriba y después `Restart-VM sor2-lab -Force`.

### 3. Conectarse por SSH desde Windows 🪟

Si antes hubo otra VM en `192.168.56.10`, Windows recuerda su huella y rechaza la conexión con *"REMOTE HOST IDENTIFICATION HAS CHANGED"*. Este comando borra la huella vieja:

```powershell
ssh-keygen -R 192.168.56.10
```

Abre una sesión en la VM:

```powershell
ssh labadmin@192.168.56.10
```

**Resultado:** la primera vez pregunta si se confía en la huella. Hay que comparar la huella **ED25519** con la que mostró la consola de la VM al arrancar; si coinciden, responder `yes`. Después pide la contraseña y queda el prompt `labadmin@sor2-lab:~$`.

### 4. (Solo si hace falta) Renombrar la máquina 🐧

Corrige el nombre de la máquina si en el instalador quedó otro.

```bash
sudo hostnamectl set-hostname sor2-lab && sudo sed -i 's/<nombre_viejo>/sor2-lab/g' /etc/hosts
```

```bash
hostnamectl hostname
```

**Resultado:** el primer comando no imprime nada si sale bien. El segundo responde `sor2-lab`. El prompt se actualiza al volver a entrar por SSH.

### 5. Actualizar el sistema 🐧

Instala las actualizaciones pendientes y reinicia.

```bash
sudo apt update && sudo apt full-upgrade -y && sudo reboot
```

**Resultado:** la sesión SSH se corta por el reinicio. Esperar unos 30 segundos y volver a conectar (paso 3).

### 6. Copiar el repositorio a la VM 🪟

Copia la carpeta del proyecto desde Windows a `~/sor2-e3-elk-ml` en la VM, sin la carpeta `.git`. El primer comando crea la carpeta; el segundo es el mismo que se usa después para actualizar la copia (ver [README de las guías](README.md#copiar-el-repo-actualizado-a-la-vm-)).

```powershell
ssh labadmin@192.168.56.10 mkdir -p sor2-e3-elk-ml
```

```powershell
cmd /c "tar -cf - --exclude=.git -C C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml . | ssh labadmin@192.168.56.10 tar -xf - -C sor2-e3-elk-ml"
```

**Resultado:** cada comando pide la contraseña de `labadmin` y termina sin mensajes. En la VM, `ls ~/sor2-e3-elk-ml` muestra el contenido del repo.

### 7. Revisar el script de preparación 🐧

Muestra el script antes de ejecutarlo como root.

```bash
cd ~/sor2-e3-elk-ml && less scripts/vm_setup.sh
```

**Resultado:** el contenido del script en pantalla. Se sale con `q`.

### 8. Preparar el sistema 🐧

Instala auditd, Apache, Docker y Filebeat 9.5.6, fija `vm.max_map_count`, crea `labuser`, configura NTP y el firewall.

```bash
sudo bash scripts/vm_setup.sh
```

**Resultado:** tarda unos minutos y termina con `Listo. Cerrá la sesión y volvé a entrar...`. Antes de ese mensaje se ven `vm.max_map_count = 262144` y el estado de ufw con tres reglas `ALLOW IN` desde `192.168.56.0/24` (puertos 22, 80 y 5601).

### 9. Volver a entrar y comprobar 🐧

Hay que cerrar la sesión para que `labadmin` pueda usar Docker sin `sudo`.

```bash
exit
```

Volver a conectar (paso 3) y ejecutar:

```bash
docker version --format '{{.Server.Version}}' && dpkg-query -W filebeat && systemctl is-active auditd apache2
```

**Resultado:** la versión de Docker Engine, `filebeat 9.5.6` y dos líneas `active`. Si Docker responde *permission denied*, la sesión no se cerró después del paso 8.

### 10. Generar las credenciales 🐧

Crea `.env` a partir del ejemplo y le pone una contraseña aleatoria a cada usuario, sin mostrarlas en pantalla.

```bash
cd ~/sor2-e3-elk-ml && cp .env.example .env && chmod 600 .env
```

```bash
for v in ELASTIC_PASSWORD KIBANA_PASSWORD KIBANA_ENCRYPTION_KEY LOGSTASH_INTERNAL_PASSWORD ANALYST_PASSWORD; do sed -i "s|^$v=.*|$v=$(openssl rand -hex 16)|" .env; done
```

```bash
grep -c '=cambiar' .env
```

**Resultado:** el último comando devuelve `0`, es decir, no quedó ningún valor de ejemplo. Para ver la contraseña de `elastic` (para entrar a Kibana): `grep ELASTIC_PASSWORD .env`. El archivo `.env` nunca se sube al repo.

### 11. Levantar ELK 🐧

Descarga las imágenes 9.5.6 y arranca Elasticsearch, Kibana y Logstash. El servicio `setup` crea los usuarios y termina.

```bash
docker compose up -d
```

```bash
docker compose ps -a
```

**Resultado:** la primera vez tarda varios minutos en descargar. Después, `docker compose ps -a` muestra `es01`, `kibana` y `logstash` como `Up ... (healthy)`, y `setup` como `Exited (0)`. Kibana puede tardar 1–2 minutos más en quedar `healthy`.

```bash
docker compose logs setup | tail -3
```

**Resultado:** la última línea es `[setup] Listo.`

### 12. Pruebas de la T1 🐧

Comprueba la autenticación, la indexación y la búsqueda, el acceso restringido, el mínimo privilegio y el heap. Guarda la salida en `results/t1/`.

```bash
bash scripts/t1_pruebas.sh
```

**Resultado:** termina con `=== Resultado: 9 OK, 0 fallas ===`.

### 13. Comprobar el acceso desde Windows 🪟

Confirma que Elasticsearch no es accesible desde fuera de la VM y que Kibana sí lo es.

```powershell
Test-NetConnection 192.168.56.10 -Port 9200
```

```powershell
Test-NetConnection 192.168.56.10 -Port 5601
```

**Resultado:** en el puerto 9200, `TcpTestSucceeded : False`. En el 5601, `TcpTestSucceeded : True`. Guardar captura de ambos.

### 14. Ver el documento de prueba en Kibana 🪟

Abrir en el navegador `http://192.168.56.10:5601`, entrar con `elastic` y en **Dev Tools** ejecutar:

```
GET lab-test/_search
```

**Resultado:** un resultado (`"hits"`) con el documento `"documento de prueba T1"`. Guardar captura.

### 15. Inventario de recursos y versiones 🐧

Registra CPU, memoria, disco, versiones, heap y consumo de los contenedores para el informe.

```bash
bash scripts/t1_inventario.sh
```

**Resultado:** se guarda `results/t1/inventario_<fecha>.txt`. Con esos datos se arma la tabla de recursos del informe (sección 6.2).
