# 04 — Ventanas y características (T4)

Convierte las sesiones del lote en dos datasets tabulares, uno por fuente, con una fila por **ventana de 30 s**
y columnas numéricas (características). Los datos salen de Elasticsearch, consultado con el usuario de solo lectura
`lab_analyst`. Parte del estado final de la guía [03 — Escenarios](03_escenarios.md): lote terminado y
`data/lote/manifiesto.csv` en la VM.
Siguiente guía: [05 — Isolation Forest](05_isolation_forest.md).

**Archivos que intervienen**

| Archivo | Para qué |
|---|---|
| `src/extraccion/ventanas.py` | Consulta Elasticsearch, arma las ventanas, calcula las características y valida cada ventana con `_count` |
| `data/lote/manifiesto.csv` | Sesiones de la T3 (solo se usan las `ok`), con sus tiempos reales y la IP atacante |
| `data/procesado/ventanas_auditd.csv` | Dataset de auditd: sesiones B1 e I1, 6 ventanas por sesión |
| `data/procesado/ventanas_apache.csv` | Dataset de Apache: sesiones B2 e I2, 6 ventanas por sesión |
| `data/procesado/diccionario_caracteristicas.md` | Qué mide cada columna |
| `results/t4/validacion_<fecha>.txt` | Resumen por escenario y contrastes con Elasticsearch y con los logs originales |

**Cómo se arma cada ventana**
- 6 ventanas por sesión, alineadas al inicio de la sesión: 0–30 s, 30–60 s, …, 150–180 s. Una ventana nunca
  mezcla dos sesiones ni dos conjuntos.
- auditd: cuenta los registros SYSCALL (uno por evento) y usa los PATH para saber qué archivo tocó cada evento.
  No usa los registros de sudo/PAM, que en el laboratorio los genera el orquestador al lanzar los generadores.
- Apache: solo `access.log`.
- **Etiqueta:** 1 si la ventana tiene al menos un evento del incidente (auditd: acceso al archivo protegido;
  Apache: petición de la IP atacante). Si se solapa con el incidente pero no tiene ningún evento suyo, queda como
  `ambigua` y no cuenta en las métricas por ventana.

---

### 1. Copiar el repo actualizado a la VM 🪟

Hacerlo **después** de que termine el lote.

```powershell
cmd /c "tar -cf - --exclude=.git -C C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml . | ssh labadmin@192.168.56.10 tar -xf - -C sor2-e3-elk-ml"
```

**Resultado:** termina sin mensajes. No toca `data/lote/` (en Windows todavía no existe).

### 2. Armar los datasets 🐧

No necesita `sudo` ni el entorno virtual: solo usa la biblioteca estándar de Python.

```bash
cd ~/sor2-e3-elk-ml && python3 src/extraccion/ventanas.py --manifiesto data/lote/manifiesto.csv
```

**Resultado** (tarda unos segundos):
- `Manifiesto: ... (40 sesiones ok de 40)`.
- `== auditd: 120 ventanas de 20 sesiones` y `== apache: 120 ventanas de 20 sesiones`, con el recuento por
  escenario, conjunto y etiqueta. Cada sesión de incidente aporta entre 1 y 3 ventanas con `etiqueta=1`.
- La tabla de medias: en `I1 e=1`, `aud_clave_protegido` y `aud_denegados` mucho mayores que en `B1`, donde
  `aud_denegados` queda cerca de 0 (solo los errores normales). `aud_fallidos` y `aud_denegados_proc` son altos en
  todos los grupos: son ruido de fondo. En `I2 e=1`, `web_4xx` y `web_max_4xx_cliente` mucho mayores que en `B2`.
- `Eventos del incidente ... 20/20 coinciden`: lo que hay en Elasticsearch coincide con lo que la T3 contó en los
  logs originales. En las I1 puede decir `OK (+1 a menos de 50 ms del borde del intervalo)`: el primer intento quedó
  fechado por auditd unos milisegundos antes del inicio que anotó el generador (ver "Cómo se definen las denegaciones").
- `Ventanas vs. consultas _count`: `120/120 ventanas coinciden` en las seis filas y `Sin diferencias.`

Si algo da `DIFIERE` o hay diferencias, no seguir: pasar el reporte completo.

### 3. Mirar los datasets 🐧

```bash
head -3 data/procesado/ventanas_auditd.csv | cut -c1-300 && head -3 data/procesado/ventanas_apache.csv | cut -c1-300
```

**Resultado:** el encabezado (metadatos y después las características) y dos filas por archivo.

### 4. Traer los resultados a Windows 🪟

Dos copias (cada una pide la contraseña):

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/data/procesado C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\data\
```

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/results/t4 C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\results\
```

**Resultado:** los dos CSV y el diccionario en `data\procesado\`, y el reporte en `results\t4\`.

---

## Cómo se definen las denegaciones

La primera corrida sobre el lote mostró que, en B1, ~190 de ~212 eventos por ventana tenían `success = no`, con solo
0–3 errores normales por sesión. Un diagnóstico (`src/extraccion/diag_incidente.py --solo-denegados`, con `sudo`)
mostró de dónde salían:

| Origen | Por sesión B1 | Qué es |
|---|---|---|
| `execve` con `exit=-2` (ENOENT) | ~315 | Python busca cada comando en cada carpeta del `PATH` (`/usr/local/sbin/head`, `/usr/local/bin/head`…) hasta encontrarlo. No es una denegación |
| `ps` con `exit=-13` sobre `/proc/<pid>/environ` | ~600 | `ps` intenta leer el entorno de procesos de root. Denegación real, pero benigna por construcción |
| `cat /etc/shadow` y similares | 0–3 | Los errores normales del escenario |

Por eso hay tres características separadas: `aud_fallidos` (cualquier `success = no`), `aud_denegados` (EACCES o EPERM
sobre archivos reales, sin `/proc`) y `aud_denegados_proc`. La regla A1 usa `aud_denegados`. Isolation Forest ve las tres.

El mismo diagnóstico explica el `+1` de las I1: el primer intento del incidente quedó fechado **1 ms antes** del inicio
informado por el generador. auditd usa un reloj de grano grueso del núcleo, que puede ir unos milisegundos atrasado
respecto del de Python. El registro es del incidente. `lote.py` y el contraste de `ventanas.py` usan 50 ms de tolerancia.

## Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `El manifiesto no tiene sesiones ok` | Ruta equivocada o el lote no terminó: revisar `data/lote/manifiesto.csv` |
| `HTTP Error 401` | Falta o cambió `ANALYST_PASSWORD` en `.env` |
| Muchas ventanas con 0 eventos | Se reinició la ingesta (paso 8 de la guía 03) **después** del lote: los datos ya no están en Elasticsearch |
| Una ventana de Apache con `etiqueta=1` e `incidente_solape_s` = 0 | Esperable: Apache registra al segundo, y la primera petición del incidente puede caer en la ventana anterior |
