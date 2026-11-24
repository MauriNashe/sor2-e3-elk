# 06 — Reglas (T6: baseline y comparación con Isolation Forest)

Aplica reglas de umbral explícito sobre las **mismas ventanas** de la T4, ajusta los umbrales sin usar prueba y
compara con Isolation Forest en las mismas ventanas de prueba y con las mismas métricas. Parte de los resultados de
la guía [05 — Isolation Forest](05_isolation_forest.md).
Siguiente guía: [07 — Alertas y latencia](07_vivo.md).

**Reglas**

| Código | Fuente | Regla | Umbral |
|---|---|---|---|
| A1 | auditd | Accesos denegados en la ventana: `aud_denegados >= k` | Ajustado en validación |
| A2 | auditd | Acceso al archivo vigilado: `aud_clave_protegido >= 1` | Fijo: cualquier acceso alerta |
| W1 | Apache | Respuestas 4xx en la ventana: `web_4xx >= k` | Ajustado en validación |
| W2 | Apache | Proporción de 4xx: `web_frac_4xx >= p`, con al menos 10 peticiones | Ajustado en validación |
| W3 | Apache | 4xx de un mismo cliente: `web_max_4xx_cliente >= k` | Ajustado en validación (informativa) |

**Qué se compara con qué** (en las mismas ventanas de prueba):

| Reglas | Isolation Forest |
|---|---|
| auditd `completo` = A1 o A2 | `auditd_completo` |
| auditd `generico` = solo A1 | `auditd_sin_clave_protegido` (ninguno usa la clave del archivo vigilado) |
| Apache `completo` = W1 o W2 | `apache_completo` |

**Archivos que intervienen**

| Archivo | Para qué |
|---|---|
| `src/reglas/reglas.py` | Reglas, ajuste de umbrales, evaluación y comparación |
| `src/evaluacion/metricas.py` | Las mismas métricas que la T5 |
| `results/t6/reglas_<fecha>.txt` | Umbrales con su justificación, métricas, incidentes uno por uno, falsos positivos y tabla comparativa |
| `results/t6/umbrales.json` | Umbrales finales (los usa la T7) |
| `results/t6/predicciones_<fuente>.csv` | Alerta de cada regla y de cada conjunto, por ventana |
| `results/t6/comparacion_prueba.csv` | Tabla ML vs. reglas en prueba |
| `results/t6/comparacion_sin_etiquetas.csv` | La misma tabla con umbrales sin etiquetas (máximo de entrenamiento) para los dos detectores |

---

### 1. Correr las reglas y la comparación 🐧

Necesita los resultados de la T5 en `results/t5/`. Solo usa la biblioteca estándar.

```bash
cd ~/sor2-e3-elk-ml && python3 src/reglas/reglas.py
```

**Resultado** (instantáneo):
- Por cada regla: el umbral, cómo se eligió (cuántos valores empataban en validación y en qué rango), la
  referencia sin etiquetas y las métricas de validación y prueba.
- Por cada conjunto de reglas: sus métricas en prueba, las de Isolation Forest en las mismas ventanas, una
  tabla incidente por incidente (segundos hasta la primera alerta de cada detector) y los falsos positivos de cada uno.
- Al final, la **tabla comparativa** (y la misma sin etiquetas): precisión, recall y F1 por ventana, incidentes detectados, mediana del tiempo
  hasta la primera alerta y falsas alarmas por hora.

### 2. Traer los resultados a Windows 🪟

```powershell
scp -r labadmin@192.168.56.10:~/sor2-e3-elk-ml/results/t6 C:\Users\mauri\OneDrive\Escritorio\UNI\SOR_2\Tp_final\sor2-e3-elk-ml\results\
```

---

## Cómo leer el resultado

- **Mismo criterio de umbral para los dos detectores:** máximo F1 por ventana en validación. Así la comparación no
  favorece a uno por haberlo calibrado mejor.
- **"empatan N valores entre a y b":** cualquier umbral en ese rango daba el mismo F1 en validación. Se toma el punto
  medio. Un rango ancho significa que la regla separa bien; un rango de un solo valor significa que está justa.
- **Referencia sin etiquetas:** el umbral que pondría alguien que solo conoce la actividad normal (máximo de
  entrenamiento + 1). Si está cerca del ajustado, la regla no depende de haber visto incidentes.
