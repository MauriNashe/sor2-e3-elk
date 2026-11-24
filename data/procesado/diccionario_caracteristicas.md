# Diccionario de características (T4)

Generado por `src/extraccion/ventanas.py`. Cada fila de los datasets es una **ventana de 30 s** de una sesión; las ventanas se alinean al inicio de la sesión (6 por sesión).

## Metadatos (no son variables predictoras)

| Columna | Contenido |
|---|---|
| `sesion`, `orden`, `escenario`, `conjunto` | Sesión de la T3, su posición en el lote, escenario (B1, I1, B2, I2) y conjunto (entrenamiento, validacion, prueba) |
| `ventana` | Índice de la ventana dentro de la sesión (0 a 5) |
| `inicio`, `fin` | Límites de la ventana en UTC, intervalo [inicio, fin) |
| `inicio_incidente`, `fin_incidente` | Intervalo real del incidente de la sesión (vacío en las benignas), informado por el generador |
| `incidente_solape_s` | Segundos de la ventana que se solapan con el intervalo real del incidente |
| `incidente_eventos` | Eventos del incidente en la ventana (auditd: SYSCALL con clave `lab_protegido`; Apache: líneas de la IP atacante) |
| `etiqueta` | 1 si la ventana contiene al menos un evento del incidente, aunque el solape sea parcial; 0 en otro caso |
| `ambigua` | 1 si hay solape pero ningún evento del incidente (borde del intervalo); se excluye de las métricas por ventana |

## auditd (`ventanas_auditd.csv`, sesiones B1 e I1)

| Característica | Grupo | Descripción |
|---|---|---|
| `aud_eventos` | volumen | Eventos del núcleo (registros SYSCALL) en la ventana |
| `aud_exec` | regla | Ejecuciones de programas del usuario de prueba (clave lab_exec) |
| `aud_clave_denegado` | regla | Aperturas denegadas del usuario de prueba fuera del archivo vigilado (clave lab_acceso_denegado) |
| `aud_clave_protegido` | regla | Accesos al archivo vigilado (clave lab_protegido). Específica del escenario: se puede excluir en un análisis de ablación |
| `aud_sin_clave` | regla | Eventos sin clave de nuestras reglas (actividad del sistema, p. ej. cron) |
| `aud_fallidos` | resultado | Eventos con resultado fallido de cualquier tipo (success = no). Incluye los execve que fallan con ENOENT al buscar un programa en cada carpeta del PATH |
| `aud_denegados` | resultado | Denegaciones de permiso (EACCES o EPERM) sobre archivos reales, sin contar /proc |
| `aud_denegados_proc` | resultado | Denegaciones de permiso sobre /proc (p. ej. ps intentando leer /proc/<pid>/environ de procesos de otros usuarios): ruido benigno de las herramientas de listado de procesos |
| `aud_frac_denegados` | resultado | Proporción de denegaciones (aud_denegados / aud_eventos; 0 si no hay eventos) |
| `aud_op_apertura` | operación | Llamadas de apertura o truncado (open, openat, creat, truncate…) |
| `aud_op_permisos` | operación | Llamadas de cambio de permisos o dueño (chmod, fchmodat, chown…) |
| `aud_procesos_distintos` | diversidad | Ejecutables distintos (process.executable) |
| `aud_pids_distintos` | diversidad | Procesos distintos (process.pid) |
| `aud_archivos_distintos` | diversidad | Archivos distintos en los registros PATH de la ventana |
| `aud_archivos_denegados_distintos` | diversidad | Archivos distintos involucrados en denegaciones de permiso (sin /proc) |
| `aud_max_por_segundo` | ritmo | Máximo de eventos en un mismo segundo (ráfagas) |
| `aud_segundos_activos` | ritmo | Segundos de la ventana con al menos un evento (actividad sostenida vs. ráfaga) |

## Apache (`ventanas_apache.csv`, sesiones B2 e I2)

| Característica | Grupo | Descripción |
|---|---|---|
| `web_peticiones` | volumen | Peticiones HTTP en la ventana |
| `web_4xx` | resultado | Respuestas 4xx |
| `web_404` | resultado | Respuestas 404 |
| `web_5xx` | resultado | Respuestas 5xx |
| `web_frac_4xx` | resultado | Proporción de respuestas 4xx (0 si no hay peticiones) |
| `web_rutas_distintas` | diversidad | Rutas distintas pedidas (url.original) |
| `web_rutas_4xx_distintas` | diversidad | Rutas distintas que dieron 4xx |
| `web_clientes` | clientes | Clientes distintos (source.ip) |
| `web_max_pet_cliente` | clientes | Peticiones del cliente más activo |
| `web_max_4xx_cliente` | clientes | Respuestas 4xx del cliente con más 4xx |
| `web_max_rutas_cliente` | clientes | Rutas distintas del cliente con más rutas distintas |
| `web_bytes_medio` | volumen | Tamaño medio de respuesta en bytes (0 si no hay peticiones) |
| `web_max_por_segundo` | ritmo | Máximo de peticiones en un mismo segundo (ráfagas) |
| `web_segundos_activos` | ritmo | Segundos de la ventana con al menos una petición |
