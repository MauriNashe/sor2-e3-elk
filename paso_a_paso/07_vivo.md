# 07 — Alertas y latencia (T7: prueba en vivo)

Corre el detector **en vivo** contra Elasticsearch mientras se generan 4 sesiones nuevas (una por escenario). Cada
30 s arma la ventana que acaba de cerrar, aplica Isolation Forest y las reglas, y registra las alertas con todas sus
marcas de tiempo. Después se arma la cronología de cada incidente y se mide la latencia, la completitud y el
consumo de CPU y memoria. Parte de los resultados de las guías [05](05_isolation_forest.md) y [06](06_reglas.md)
(modelos en `results/t5/modelos/` y umbrales en `results/t6/umbrales.json`, en la VM).
Siguiente guía: [08 — Evaluación y dashboard](08_evaluacion.md).

**Archivos que intervienen**

| Archivo | Para qué |
|---|---|
| `src/deteccion/detector_vivo.py` | Detector: ventanas de 30 s alineadas al reloj, consulta en fin + 30 s, alertas y medición de recursos |
| `src/generacion/lote.py --alinear 30` | Genera las sesiones de la prueba empezando en un múltiplo exacto de 30 s |
| `src/deteccion/cronologia.py` | Cronología por incidente, latencia por tramo, completitud, métricas en vivo y resumen de recursos |
| `results/t7/vivo_<fecha>/ventanas.csv` | Lo que vio y decidió el detector en cada ventana, con sus tiempos |
| `results/t7/vivo_<fecha>/alertas.jsonl` | Las alertas (también en el índice `lab-alertas-AAAA.MM.DD`) |
| `results/t7/vivo_<fecha>/recursos.csv` | CPU y memoria cada 10 s: auditd, Filebeat, Apache, contenedores del stack, detector y VM |
| `results/t7/vivo_<fecha>/cronologia_<fecha>.txt` | El reporte final de la prueba |
| `data/vivo/` | Plan y manifiesto de las 4 sesiones de la prueba |

---

### 1. Preparar el anfitrión 🪟

**Antes de medir:** cerrar Steam, Discord, el navegador con muchas pestañas y todo lo que no se use. Compiten por
CPU con la VM y ensucian la medición de recursos. Mantener *Suspender: Nunca*.

### 2. Abrir tmux con dos ventanas 🐧

```bash
tmux new -s vivo
```

### 3. Arrancar el detector (ventana 0 de tmux) 🐧

```bash
cd ~/sor2-e3-elk-ml && .venv/bin/python src/deteccion/detector_vivo.py --minutos 20
```

**Resultado:** `Detector en marcha hasta HH:MM:SS; ventanas de 30 s, espera 30 s. Primera ventana: ...`. A partir
de ahí, una línea por ventana (cada 30 s, con 30 s de retraso) con los eventos de cada fuente y `sin alertas`.

### 4. Lanzar las 4 sesiones (ventana 1 de tmux) 🐧

**En cuanto el detector muestre `Detector en marcha`, sin esperar a que termine:** el detector y las sesiones
tienen que correr al mismo tiempo. Si el detector corre solo, únicamente ve la VM en reposo y la prueba no sirve.
Las 4 sesiones tardan unos 14 minutos, así que tienen que arrancar dentro de los primeros 5 minutos del detector.

Abrir otra ventana de tmux con `Ctrl+B` y después `C`:

```bash
cd ~/sor2-e3-elk-ml && sudo python3 src/generacion/lote.py --salida data/vivo --sesiones 1 --semilla 20261121 --alinear 30
```

**Resultado:** como el piloto: 4 sesiones con `-> OK` y `Resumen: 4 ok / 4 sesiones` (unos 15 minutos). Cada sesión
arranca en un segundo :00 o :30.

- Cambiar de ventana de tmux: `Ctrl+B` y después `0` o `1`.
- En la ventana del detector tienen que aparecer líneas `ALERTA: ...` durante los incidentes (I1 e I2).

### 5. Captura de Kibana (mientras corre o al terminar) 🪟

En `http://192.168.56.10:5601`, entrar como `elastic`:

1. *Stack Management → Data Views → Create data view*: nombre `lab-alertas`, patrón `lab-alertas-*`, campo de
   tiempo `@timestamp`. Guardar.
2. *Discover*: elegir `lab-alertas`, rango *Last 30 minutes*. Agregar como columnas `lab.detector`, `lab.fuente`,
   `lab.ventana_inicio`, `lab.ventana_fin`, `lab.t_alerta`, `lab.puntaje` y `lab.explicacion`.
3. Captura con las alertas de los dos incidentes → `informe/figuras/t7_kibana_alertas.png`.

### 6. Armar la cronología (cuando el detector diga `Listo`) 🐧

Usar la carpeta que imprimió el detector al terminar:

```bash
python3 src/deteccion/cronologia.py --vivo results/t7/vivo_<fecha> --manifiesto data/vivo/manifiesto.csv
```

**Resultado:**
- **Métricas en vivo** de cada detector en las ventanas de las sesiones, y alertas fuera de las sesiones.
- **Cronología de cada incidente:** inicio real (t = 0) → primer evento → Filebeat → Logstash → indexado | fin de la
  ventana → consulta → **ALERTA**, con la espera y el procesamiento.
- **Latencia de ingesta** de todos los eventos: mediana, p95 y máximo, por tramo y por fuente.
- **Completitud:** eventos que llegaron después de la consulta (lo esperable con 30 s de espera: 0 o casi 0).
- **CPU y memoria** por componente: media y máximo.

### 7. Traer los resultados a Windows 🪟

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/results/t7 C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\results\
```

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/data/vivo C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\data\
```

---

## Cómo leer la cronología

- **t = 0** es el momento en que arrancó el generador del incidente, con el mismo reloj que todo lo demás.
- La **ingesta** (Filebeat → Logstash → Elasticsearch) corre **en paralelo** a la acumulación de la ventana: no se
  suma. La alerta sale en *fin de la ventana + espera + procesamiento*.
- **Espera:** 30 s. Es un compromiso: más corta alerta antes, pero el detector puede consultar antes de que lleguen
  todos los eventos (la sección de completitud lo muestra).
- Lo que más pesa en el tiempo hasta la alerta es la **ventana** (hasta 30 s) y la **espera** (30 s), no el
  procesamiento (décimas de segundo).

## Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `FileNotFoundError: results/t5/modelos/...` | Falta correr la T5 en la VM (guía 05) |
| `FileNotFoundError: results/t6/umbrales.json` | Falta correr la T6 en la VM (guía 06) |
| `no se pudo indexar la alerta: HTTP Error 403` | El rol `lab_analyst` no tiene escritura en `lab-alertas*`: volver a correr `configs/elasticsearch/setup.sh` (guía 01) |
| En `recursos.csv` no hay filas `docker:` | `labadmin` no está en el grupo `docker`: salir y volver a entrar por SSH |
