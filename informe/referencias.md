# Referencias del informe: búsqueda, verificación y seguimiento

Requisitos de la consigna general:
- Formato **APA 7**.
- **Mínimo 8 referencias**, de las cuales **al menos 5 académicas del período 2020–2026** (artículos de revista o congreso, RFC, libros de texto).
- **Toda referencia tiene que estar citada en el texto.**
- El planteamiento del problema necesita **al menos una referencia de 2020–2026 con datos concretos**.
- En el marco teórico, cada referencia se analiza: **qué aporta y qué limitaciones tiene**.

> Los PDF se guardan en `informe/referencias/`. Esa carpeta está en `.gitignore` (`*.pdf`) para no redistribuir material con copyright.

---

## 1. Dónde buscar

| Fuente | Para qué |
|---|---|
| Google Scholar, Semantic Scholar | Búsqueda general, "citado por", artículos relacionados |
| dblp (dblp.org) | Comprobar autores, año y congreso o revista de trabajos de informática |
| IEEE Xplore, ACM Digital Library | Congresos y revistas de seguridad e ingeniería de software |
| ScienceDirect, SpringerLink | Revistas (Computers & Security, Journal of Network and Computer Applications…) |
| USENIX, MDPI | Acceso abierto (MDPI: *Sensors*, *Electronics*, *Applied Sciences*; revisar la calidad caso por caso) |
| Biblioteca Electrónica de Ciencia y Tecnología (MinCyT), vía biblioteca UNGS | Texto completo de editoriales pagas |
| arXiv | Versión del autor de un artículo publicado. Si **solo** está en arXiv, es un preprint y no cuenta entre las 5 académicas |

**Palabras clave útiles:**
- "log anomaly detection", "log-based anomaly detection survey"
- "isolation forest intrusion detection", "unsupervised anomaly detection security logs"
- "auditd", "Linux audit framework", "host-based intrusion detection"
- "web server access log anomaly detection", "HTTP log intrusion detection"
- "SIEM Elastic Stack evaluation", "alert fatigue false positives"
- "detection latency", "rule-based vs machine learning intrusion detection"

---

## 2. Cómo verificar cada referencia

Hay que hacerlo con **todas**, incluidas las que sugiera una IA, que puede inventar o mezclar datos.

1. **DOI**: abrir `https://doi.org/<DOI>`. Tiene que llevar a la página de la editorial.
2. **Metadatos**: autores, año, título, revista o congreso, volumen, número y páginas tienen que coincidir con la editorial o con dblp. Copiarlos desde ahí, no desde la IA.
3. **Revisión por pares**: confirmar que se publicó en una revista o un congreso, y no solo como preprint.
4. **Lectura**: leer como mínimo el resumen y la sección que se usa. Anotar la página para citas textuales: `(Autor, año, p. X)`.
5. **Calidad**: la revista no tiene que ser predatoria y el artículo no tiene que estar retractado (Retraction Watch).
6. **Registro**: cargarla en Zotero (desde el DOI) y exportarla en APA 7. Marcarla como verificada en la tabla de abajo.

---

## 3. Seguimiento

Estados: `candidata` (sin verificar) → `verificada` (pasos 1–5) → `citada` (está en el texto del informe).

### 3.1 Académicas (marco teórico)

| # | Referencia (verificar los datos) | Aporte esperado | Sección del informe | DOI | Estado |
|---|---|---|---|---|---|
| A1 | Landauer, M. et al. (2023). *Deep learning for anomaly detection in log data: A survey.* Machine Learning with Applications | Panorama de detección de anomalías en logs; preprocesamiento y ventanas | 4 Marco teórico | | candidata |
| A2 | Landauer, M. et al. (2023). *Maintainable log datasets for evaluation of intrusion detection systems.* IEEE Transactions on Dependable and Secure Computing | Escenarios de ataque etiquetados con logs de Apache y de audit; metodología de etiquetado | 4, 5 Metodología | | candidata |
| A3 | He, S., He, P., Chen, Z., Yang, T., Su, Y., & Lyu, M. R. (2021). *A survey on automated log analysis for reliability engineering.* ACM Computing Surveys | Etapas del análisis de logs: parseo, features, detección | 4 | | candidata |
| A4 | Le, V.-H., & Zhang, H. (2022). *Log-based anomaly detection with deep learning: How far are we?* ICSE 2022 | Advertencias de evaluación: división de datos, fuga de información, ventanas | 4, 7 Resultados | | candidata |
| A5 | Zhu, J. et al. (2023). *Loghub: A large collection of system log datasets for AI-driven log analytics.* ISSRE 2023 | Datasets públicos de logs; contraste con un dataset propio de laboratorio | 4 | | candidata |
| A6 | Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). *Isolation Forest.* IEEE ICDM | Definición del método (clásica, **fuera de 2020–2026**: no cuenta entre las 5 recientes) | 4, 6.2 | | candidata |
| A7 | *(buscar)* Isolation Forest aplicado a detección de intrusiones o logs, 2020–2026 | Justificar que el método es pertinente | 4 | | — |
| A8 | *(buscar)* Comparación entre reglas o firmas y ML en detección, 2020–2026 | Respaldo para H2 | 4, 7 | | — |

### 3.2 Planteamiento del problema (datos cuantitativos 2020–2026)

Son informes de la industria: no son académicos, pero sirven para los datos concretos del planteamiento. Hay que usar **la edición más reciente** y citar el número exacto con su página.

| # | Fuente | Dato a buscar | Estado |
|---|---|---|---|
| P1 | IBM / Ponemon, *Cost of a Data Breach Report* (anual) | Días promedio para identificar y contener una brecha | candidata |
| P2 | Mandiant, *M-Trends* (anual) | Tiempo de permanencia (dwell time) del atacante | candidata |
| P3 | Verizon, *Data Breach Investigations Report* (anual) | Peso de las aplicaciones web y los accesos indebidos entre los vectores | candidata |

### 3.3 Documentación técnica (cuenta para las 8, no para las 5 académicas)

| # | Fuente | Uso | Estado |
|---|---|---|---|
| D1 | Elastic, documentación de Elasticsearch/Logstash/Filebeat 9.x (módulos auditd y apache, ingest pipelines, seguridad) | Implementación (6.2) | candidata |
| D2 | Linux Audit Framework: páginas de manual `auditd(8)`, `auditctl(8)`, `audit.rules(7)`, `ausearch(8)` | Capas del SO (6.3): cómo se agrupan los registros por número de serie | candidata |
| D3 | Apache HTTP Server 2.4, documentación de *Log Files* (formato combined) | Campos de Apache (T2) | candidata |
| D4 | scikit-learn, documentación de `IsolationForest`, y Pedregosa et al. (2011), *Scikit-learn: Machine Learning in Python*, JMLR | Implementación del modelo (2011: no cuenta como reciente) | candidata |

---

## 4. Plantilla APA 7 (referencia rápida)

- **Revista:** Apellido, A. A., & Apellido, B. B. (Año). Título del artículo. *Nombre de la Revista, Vol*(N), pp–pp. https://doi.org/xxxx
- **Congreso:** Apellido, A. A. (Año). Título. En *Proceedings of …* (pp. xx–yy). Editorial. https://doi.org/xxxx
- **Informe:** Organización. (Año). *Título del informe*. URL
- **Documentación:** Organización. (s.f. o año). *Título de la página*. Recuperado el DD de mes de AAAA, de URL
