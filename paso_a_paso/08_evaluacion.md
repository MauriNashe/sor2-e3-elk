# 08 — Evaluación y dashboard (T8)

Junta todo: recuento de eventos perdidos y mal parseados después del lote, alertas offline cargadas en Kibana,
el dashboard (exportado en NDJSON) y la evaluación final con tablas y gráficos regenerables. Parte de las guías
04 a 07 terminadas.

**Archivos que intervienen**

| Archivo | Para qué |
|---|---|
| `src/extraccion/validar_ingesta.py --salida results/t8` | Logs originales vs. Elasticsearch después del lote: perdidos, duplicados, mal parseados |
| `src/evaluacion/indexar_alertas.py` | Carga las alertas offline de IF y reglas en `lab-alertas-offline` para el dashboard |
| `src/evaluacion/evaluar.py` | Genera `analysis/evaluacion.md`, `analysis/tablas/*.csv` y `analysis/figuras/*.png` |
| `dashboards/sor2_e3_dashboard.ndjson` | Dashboard exportado (Saved Objects) |

---

### 1. Recuento de pérdidas y parseo sobre el lote 🐧

```bash
cd ~/sor2-e3-elk-ml && sudo python3 src/extraccion/validar_ingesta.py --salida results/t8
```

**Resultado:** como en la T2, pero sobre todo lo ingerido desde el reinicio previo al lote. Lo esperable:
`faltan 0`, `de más 0` y `errores 0` en auditd y Apache.

Apache rota `access.log` a medianoche (y auditd rota `audit.log` al llegar a 50 MB): si la corrida es al día
siguiente del lote, sus líneas están en `access.log.1`. El script las compara igual, desde el primer documento que
tiene Elasticsearch; la línea `líneas en el archivo` dice cuántas tomó del archivo rotado (para el lote, varios
miles). Si ese número diera 0 al día siguiente, la pérdida del lote **no** se estaría verificando.

### 2. Cargar las alertas offline en Elasticsearch 🐧

```bash
python3 src/evaluacion/indexar_alertas.py
```

**Resultado:** `Alertas offline en lab-alertas-offline: N nuevas, 0 ya estaban, 0 errores.` Si se vuelve a correr,
dice `0 nuevas, N ya estaban`: no duplica.

### 3. Vistas de datos en Kibana 🪟

En `http://192.168.56.10:5601`, entrar como `elastic`. *Stack Management → Data Views → Create data view*, una por
línea (campo de tiempo `@timestamp` en todas). La de alertas puede existir ya desde la T7.

| Nombre | Patrón |
|---|---|
| `lab-auditd` | `lab-auditd-*` |
| `lab-apache` | `lab-apache-*` |
| `lab-eventos` | `lab-auditd-*,lab-apache-*` |
| `lab-alertas` | `lab-alertas-*` |

### 4. Armar el dashboard 🪟

*Dashboards → Create dashboard*. Arriba a la derecha, el rango de tiempo del **lote** (por ejemplo de 03:35 a 06:00
del 20/11). Cada panel: *Create visualization* (Lens), elegir la vista de datos, configurar y *Save and return*.

| # | Panel | Vista | Configuración en Lens |
|---|---|---|---|
| 1 | Volumen por fuente | `lab-eventos` | Barras apiladas. Eje horizontal `@timestamp`; vertical *Count*; *Breakdown* `event.module` |
| 2 | Denegaciones de auditd | `lab-auditd` | Filtro (barra de búsqueda del panel): `event.action : "syscall" and process.exit_code : (-13 or -1)`. Barras: `@timestamp` / *Count* / *Breakdown* `process.executable` (top 5). Se ve el fondo de `ps` (denegaciones sobre `/proc`) y, encima, los picos de los incidentes |
| 3 | Códigos HTTP | `lab-apache` | Filtro `event.dataset : "apache.access"`. Barras apiladas: `@timestamp` / *Count* / *Breakdown* `http.response.status_code` (top 5) |
| 4 | Peticiones por cliente | `lab-apache` | Filtro `event.dataset : "apache.access"`. Barras horizontales: *Count* por `source.ip` (top 10) |
| 5 | Alertas de ML y reglas | `lab-alertas` | Barras: `@timestamp` / *Count* / *Breakdown* `lab.detector` (top 10) |
| 6 | Detalle de alertas | `lab-alertas` | Tabla: filas `lab.detector`, `lab.fuente`, `lab.sesion`; métrica *Count* |

Guardar el dashboard como **`SOR2 E3 — Detección de anomalías`**.

**Captura:** el dashboard completo con el rango del lote → `informe/figuras/t8_dashboard.png`. Si sirve para el
informe, otra con zoom en un incidente (rango de 3 minutos de una sesión I1 o I2).

### 5. Exportar el dashboard en NDJSON 🐧

Exporta el dashboard con sus visualizaciones y vistas de datos, usando la API de Kibana desde la VM:

```bash
set -a && source .env && set +a && curl -s -u "elastic:$ELASTIC_PASSWORD" -X POST "http://$LAB_IP:5601/api/saved_objects/_export" -H "kbn-xsrf: true" -H "Content-Type: application/json" -d '{"type": ["dashboard"], "includeReferencesDeep": true}' > dashboards/sor2_e3_dashboard.ndjson && wc -l dashboards/sor2_e3_dashboard.ndjson && tail -1 dashboards/sor2_e3_dashboard.ndjson
```

**Resultado:** varias líneas (dashboard, visualizaciones y vistas de datos) y en la última
`"exportedCount":N,"missingRefCount":0`. Alternativa desde la interfaz: *Stack Management → Saved objects*,
marcar el dashboard, *Export* con *Include related objects*.

> El NDJSON no tiene contraseñas, pero sí los nombres de índices y campos: se puede versionar.

### 6. Generar la evaluación 🐧

```bash
.venv/bin/python src/evaluacion/evaluar.py
```

**Resultado:** imprime `analysis/evaluacion.md` completo y termina con `Listo`. Contiene:
1. Tabla comparativa ML vs. reglas en prueba, con episodios (alertas deduplicadas).
2. Incidentes uno por uno con su intensidad y el tiempo hasta la primera alerta de cada detector (**no** = no detectado).
3. Falsos positivos con la explicación de Isolation Forest.
4. Resumen por escenario.
5. Configuración y estabilidad de Isolation Forest.
6. Prueba en vivo: cronología, latencia de ingesta, CPU y memoria, completitud.
7. Eventos perdidos y mal parseados.

Figuras en `analysis/figuras/`: `matrices_confusion.png`, `puntajes_if_auditd.png`, `puntajes_if_apache.png`,
`comparacion.png`, `cronologia_vivo.png`, `latencia_ingesta.png`, `recursos_cpu.png`.

### 7. Traer todo a Windows 🪟

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/analysis labadmin@192.168.56.10:~/sor2-e3-elk-ml/dashboards C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\
```

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/results/t8 C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\results\
```

---

## Definiciones que usa la evaluación

- **Unidad por ventana:** 30 s. Las ventanas ambiguas (tocan el incidente sin eventos suyos) no cuentan.
- **Asociación alerta–incidente:** la alerta tiene que caer en una ventana de esa sesión con eventos del incidente o
  solapada con su intervalo. Tolerancia adicional: 0.
- **Deduplicación:** alertas del mismo detector en ventanas consecutivas de una sesión = un episodio. Un episodio sin
  ninguna ventana del incidente es una falsa alarma.
- **Tiempo hasta la primera alerta (offline):** fin de la primera ventana alertada − inicio real del incidente. En
  vivo (T7) se suma la espera de 30 s y el procesamiento.
