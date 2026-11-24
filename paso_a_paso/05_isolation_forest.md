# 05 — Isolation Forest (T5)

Entrena un detector Isolation Forest **por fuente** con las ventanas de las sesiones benignas de entrenamiento,
elige hiperparámetros y umbral en validación, y evalúa **una sola vez** en prueba. Parte de los datasets de la guía
[04 — Ventanas y características](04_ventanas.md).
Siguiente guía: [06 — Reglas](06_reglas.md).

**Archivos que intervienen**

| Archivo | Para qué |
|---|---|
| `src/modelos/isolation_forest.py` | Búsqueda de hiperparámetros, umbral, evaluación, estabilidad por semilla y guardado |
| `src/evaluacion/metricas.py` | Métricas por ventana, por incidente y falsas alarmas por hora (las mismas que usará la T6) |
| `results/t5/resumen_<fecha>.txt` | Todo el resultado en texto: búsqueda, umbral, métricas de validación y prueba, incidentes uno por uno |
| `results/t5/<fuente>_<variante>_config.json` | Características, hiperparámetros, umbral, semilla, versiones y hash del dataset |
| `results/t5/<fuente>_<variante>_predicciones.csv` | Puntaje y alerta de cada ventana, con las 3 características que más se apartan de lo normal |
| `results/t5/modelos/*.joblib` | Modelos entrenados (no se versionan; se regeneran con el script) |

**Variantes:** `auditd_completo`, `auditd_sin_clave_protegido` (ablación: sin la característica que cuenta accesos
al archivo vigilado) y `apache_completo`.

---

### 1. Crear el entorno de Python (una sola vez) 🐧

Instala scikit-learn y compañía en `.venv`, dentro del repo, y congela las versiones exactas.

```bash
cd ~/sor2-e3-elk-ml && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/pip freeze > requirements.lock && .venv/bin/python -c "import sklearn; print(sklearn.__version__)"
```

**Resultado:** después de uno o dos minutos, la versión de scikit-learn (por ejemplo `1.7.2`).

### 2. Entrenar y evaluar 🐧

```bash
.venv/bin/python src/modelos/isolation_forest.py
```

**Resultado** (tarda menos de un minuto). Para cada variante:
- `Ventanas: entrenamiento 36 (6 sesiones), validación ..., prueba ...`.
- Las 5 mejores combinaciones de la búsqueda y la elegida.
- El umbral y los puntajes de entrenamiento como referencia.
- Validación y prueba: matriz por ventana (TP, FP, FN, TN), precisión, recall y F1; incidentes detectados y
  tiempo hasta la primera alerta; falsas alarmas por hora. En prueba, una línea por incidente.
- La comparación con un umbral que no usa etiquetas y la estabilidad con 10 semillas.

### 3. Traer los resultados a Windows 🪟

Dos copias (cada una pide la contraseña):

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/results/t5 C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\results\
```

```powershell
scp labadmin@192.168.56.10:~/sor2-e3-elk-ml/requirements.lock C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\
```

**Resultado:** `results\t5\` con el resumen, los JSON, las predicciones y los modelos; `requirements.lock` en la raíz del repo.

---

## Cómo leer el resultado

- **Por ventana:** la unidad es una ventana de 30 s. Precisión = de las ventanas alertadas, cuántas tenían incidente.
  Recall = de las ventanas con incidente, cuántas se alertaron.
- **Por incidente:** un incidente cuenta como detectado si hay al menos una alerta en una de sus ventanas.
  "Primera alerta" = fin de la primera ventana alertada − inicio real del incidente: es lo antes que se podía
  alertar, porque la ventana se evalúa cuando termina. La latencia de ingesta se suma en la T7.
- **Umbral sin etiquetas:** alerta solo lo que supera al peor puntaje visto en entrenamiento. Muestra qué pasaría
  si no hubiera incidentes de validación para calibrar.
- **Estabilidad:** Isolation Forest es aleatorio; si el ± es grande, el resultado depende de la semilla.
