# 03 — Escenarios (T3: generadores, piloto y lote de sesiones)

Genera las sesiones etiquetadas de los cuatro escenarios, verifica cada una contra los logs originales y
deja el manifiesto. Parte del estado final de la guía [02 — Ingesta](02_ingesta.md).
Siguiente guía: [04 — Ventanas y características](04_ventanas.md).

**Escenarios** (10 sesiones de 3 minutos cada uno, en orden aleatorio):

| Código | Fuente | Qué pasa | Conjuntos |
|---|---|---|---|
| B1 | auditd | `labuser` usa el sistema: comandos, escritura de archivos propios, ráfagas y 0–3 errores normales de permisos (`/etc/shadow`, `/root`) | 6 entrenamiento, 2 validación, 2 prueba |
| B2 | Apache | 1–3 clientes navegan el sitio: páginas, recursos, ráfagas y 404 normales (favicon, enlaces rotos) | 6 / 2 / 2 |
| I1 | auditd | Actividad de B1 + entre los segundos 45 y 105, durante 30–60 s, intentos de leer, escribir o cambiar permisos de `/srv/lab/protegido/secreto.txt` | 5 validación, 5 prueba |
| I2 | Apache | Actividad de B2 + en la misma ventana, otro cliente recorre rutas típicas de escáneres (1–8 peticiones/s) | 5 / 5 |

**Archivos que intervienen**

| Archivo | Para qué |
|---|---|
| `src/generacion/linux_actividad.py` | Actividad de `labuser` (modos `benigno` e `intrusion`) |
| `src/generacion/http_cliente.py` | Cliente HTTP en contenedor (modos `benigno` y `exploracion`) y generador del sitio de prueba |
| `src/generacion/lote.py` | Orquestador: plan reproducible, ejecución, verificación contra los logs y manifiesto reanudable |
| `scripts/t3_setup.sh` | Prepara generadores, sitio, red Docker `labnet`, ufw e imagen |
| `scripts/t3_archivar_logs.sh` | Archiva los logs brutos después del lote |
| `data/<piloto o lote>/plan.json` | Orden, semillas, parámetros y conjunto de cada sesión (se crea la primera vez) |
| `data/<piloto o lote>/manifiesto.csv` | Una fila por sesión: tiempos, parámetros, IPs, evidencia, eventos perdidos y estado |

---

### 1. Copiar el repo actualizado a la VM 🪟

```powershell
cmd /c "tar -cf - --exclude=.git -C C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml . | ssh labadmin@192.168.56.10 tar -xf - -C sor2-e3-elk-ml"
```

**Resultado:** pide la contraseña y termina sin mensajes (ver [README de las guías](README.md#copiar-el-repo-actualizado-a-la-vm-)).

### 2. Aplicar el ajuste pendiente de la T2 (`lab.filebeat_read`) 🐧

Reinicia Logstash con el `lab.conf` nuevo y actualiza la plantilla de índice.

```bash
cd ~/sor2-e3-elk-ml && docker compose restart logstash && sudo bash scripts/t2_ingesta_setup.sh
```

**Resultado:** el script de la T2 termina igual que antes (`OK PUT /_index_template/lab`, Filebeat `active`).

### 3. Preparar los escenarios 🐧

Revisarlo antes con `less scripts/t3_setup.sh`.

```bash
sudo bash scripts/t3_setup.sh
```

**Resultado:**
- `== 1`: los tres `.py` en `/opt/lab/gen`.
- `== 2`: `notas.txt`, `datos.csv` y `diario.txt` de `labuser`.
- `== 3`: `Sitio generado en /var/www/html: 31 páginas, 13 recursos`.
- `== 4`: `172.30.0.0/24 gw 172.30.0.1`.
- `== 5`: nueva regla `80/tcp ALLOW IN 172.30.0.0/24`.
- `== 7`: un resumen JSON del cliente HTTP con códigos `200` (y algún `404`), la última línea de `access.log` empezando con `172.30.0.5` y un resumen JSON de `linux_actividad` con `"uid": 1001`.

### 4. Partir de índices limpios 🐧

```bash
sudo bash scripts/t2_reiniciar_ingesta.sh
```

**Resultado:** `DELETE ... -> HTTP 200` por índice, Filebeat `active`.

### 5. Piloto: una sesión por escenario 🐧

Corre 4 sesiones (una por escenario, unos 13 minutos) con su propio plan en `data/piloto`.

```bash
sudo python3 src/generacion/lote.py --salida data/piloto --sesiones 1
```

**Resultado:** cada sesión termina con `-> OK` y su evidencia: en I1 y I2, `incidente=` mayor que 0. Al final, `Resumen: 4 ok / 4 sesiones`. Si una sesión da `FALLO`, la nota dice por qué. Volver a correr el mismo comando repite solo las que fallaron.

### 6. Revisar el piloto 🐧

Muestra el manifiesto resumido y comprueba que los incidentes también llegaron a Elasticsearch.

```bash
python3 -c "import csv; [print(r['sesion'], r['escenario'], r['estado'], 'sesion=', r['evid_sesion'], 'incidente=', r['evid_incidente'], r['ip_atacante'], r['nota']) for r in csv.DictReader(open('data/piloto/manifiesto.csv'))]"
```

```bash
set -a && source .env && set +a && curl -s -u "lab_analyst:$ANALYST_PASSWORD" "http://127.0.0.1:9200/lab-auditd-*/_count?q=auditd.log.key:lab_protegido" && echo && curl -s -u "lab_analyst:$ANALYST_PASSWORD" "http://127.0.0.1:9200/lab-apache-*/_count?q=http.response.status_code:404" && echo
```

**Resultado:** 4 filas `ok`. En Elasticsearch, los `count` de `lab_protegido` y de 404 tienen que ser mayores que 0 y del mismo orden que la evidencia del manifiesto.

> **Si el piloto no da 4 ok, no lanzar el lote.** Revisar las notas y la salida antes de seguir.

### 7. Preparar el anfitrión para el lote 🪟

- Cerrar Steam, Discord y los programas que no se usen (compiten por CPU y disco con la VM).
- Desactivar la suspensión de Windows mientras dure el lote: *Configuración → Sistema → Energía → Suspender: Nunca*. Si Windows se suspende, la VM se congela.

### 8. Volver a partir de índices limpios 🐧

Así los índices tienen solo los datos del lote (los del piloto quedan en su manifiesto y en los logs).

```bash
sudo bash scripts/t2_reiniciar_ingesta.sh
```

### 9. Lanzar el lote completo (unas 2 h 15 min) 🐧

Se corre dentro de `tmux`, para que siga aunque se cierre la sesión SSH.

```bash
tmux new -s lote
```

Dentro de tmux:

```bash
cd ~/sor2-e3-elk-ml && mkdir -p data/lote && sudo python3 src/generacion/lote.py --salida data/lote --sesiones 10 2>&1 | tee -a data/lote/consola.log
```

**Resultado:** pide la contraseña de sudo una vez y muestra `Plan nuevo: ... (40 sesiones ...)`, `Pendientes: 40 de 40 (≈ 133 min)` y una línea por sesión con `-> OK`.

- Para **salir sin cortarlo**: `Ctrl+B`, soltar y después `D`. Se puede cerrar el SSH.
- Para **volver a verlo**: `tmux attach -t lote`.
- Si se corta (reinicio, Ctrl+C), **el mismo comando lo retoma** desde las sesiones que faltan.

Al final: `Resumen: 40 ok / 40 sesiones` y el detalle por escenario (`B1: 10 ok`, etc.).

### 10. Archivar los logs brutos 🐧

```bash
sudo bash scripts/t3_archivar_logs.sh lote
```

**Resultado:** la lista de archivos dentro de `data/raw/lote_<fecha>/logs.tar.gz` y su SHA-256.

### 11. Traer el plan y el manifiesto al repo 🪟

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/data/piloto labadmin@192.168.56.10:~/sor2-e3-elk-ml/data/lote C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\data\
```

**Resultado:** `plan.json`, `manifiesto.csv` y `consola.log` de cada uno en `data/piloto` y `data/lote`.
