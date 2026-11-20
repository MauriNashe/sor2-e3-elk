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

Estados: `candidata` (sin verificar) → `metadatos ok` (pasos 1–3: DOI y datos comprobados) → `verificada` (pasos 1–5, leída) → `citada` (está en el texto del informe).

> El 18/11/2026 se comprobaron con la API de Crossref los DOI y metadatos de A1–A6 (pasos 1–3). Falta leer cada artículo (paso 4) y contrastarlo con lo escrito en el marco teórico del informe.
> He et al.: Crossref da 2021 como fecha en línea y 2022 como fecha del número (54(6), julio de 2022). En APA 7 se cita el año del número: **2022**.
> Como hay dos "Landauer et al. (2023)" con distintos coautores, APA 7 los distingue así: (Landauer, Onder, et al., 2023) y (Landauer, Skopik, et al., 2023).

### 3.1 Académicas (marco teórico)

| # | Referencia | Aporte esperado | Sección del informe | DOI | Estado |
|---|---|---|---|---|---|
| A1 | Landauer, M., Onder, S., Skopik, F., & Wurzenberger, M. (2023). *Deep learning for anomaly detection in log data: A survey.* Machine Learning with Applications, 12, 100470 | Panorama de detección de anomalías en logs; preprocesamiento y ventanas | 2, 4.2 | 10.1016/j.mlwa.2023.100470 | metadatos ok · citada (borrador) |
| A2 | Landauer, M., Skopik, F., Frank, M., Hotwagner, W., Wurzenberger, M., & Rauber, A. (2023). *Maintainable log datasets for evaluation of intrusion detection systems.* IEEE TDSC, 20(4), 3466–3482 | Escenarios de ataque etiquetados con logs de Apache y de audit; metodología de etiquetado | 2, 4.4 | 10.1109/TDSC.2022.3201582 | metadatos ok · citada (borrador) |
| A3 | He, S., He, P., Chen, Z., Yang, T., Su, Y., & Lyu, M. R. (2022). *A survey on automated log analysis for reliability engineering.* ACM Computing Surveys, 54(6), 1–37 | Etapas del análisis de logs: parseo, features, detección | 4.1 | 10.1145/3460345 | metadatos ok · citada (borrador) |
| A4 | Le, V.-H., & Zhang, H. (2022). *Log-based anomaly detection with deep learning: How far are we?* ICSE 2022, pp. 1356–1367 | Advertencias de evaluación: división de datos, etiquetas, detección temprana | 2, 4.3 | 10.1145/3510003.3510155 | metadatos ok · citada (borrador) |
| A5 | Zhu, J., He, S., He, P., Liu, J., & Lyu, M. R. (2023). *Loghub: A large collection of system log datasets for AI-driven log analytics.* ISSRE 2023, pp. 355–366 | Datasets públicos de logs; contraste con un dataset propio de laboratorio | 2, 4.4 | 10.1109/ISSRE59848.2023.00071 | metadatos ok · citada (borrador) |
| A6 | Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). *Isolation forest.* IEEE ICDM 2008, pp. 413–422 | Definición del método (clásica, **fuera de 2020–2026**: no cuenta entre las 5 recientes) | 4.5 | 10.1109/ICDM.2008.17 | metadatos ok · citada (borrador) |
| A7 | *(buscar)* Isolation Forest aplicado a detección de intrusiones o logs, 2020–2026 | Justificar que el método es pertinente | 4 | | — |
| A8 | *(buscar)* Comparación entre reglas o firmas y ML en detección, 2020–2026 | Respaldo para H2 | 4, 7 | | — |

### 3.2 Planteamiento del problema (datos cuantitativos 2020–2026)

Son informes de la industria: no son académicos, pero sirven para los datos concretos del planteamiento. Hay que usar **la edición más reciente** y citar el número exacto con su página.

| # | Fuente | Dato a buscar | Estado |
|---|---|---|---|
| P1 | IBM, *Cost of a Data Breach Report 2026* | Edición 2026, según la cobertura publicada: 247 días para identificar y contener (241 el año anterior); costo promedio global de USD 4,99 millones. **Confirmar en el PDF y anotar la página** | citada (borrador) |
| P2 | Mandiant, *M-Trends 2026* | Según la cobertura publicada: mediana global de 14 días de permanencia en 2025 (11 en 2024); unos 9 días con detección interna contra 25 días con aviso externo. **Confirmar en el PDF y anotar la página** | citada (borrador) |
| P3 | Verizon, *Data Breach Investigations Report* (anual) | Peso de las aplicaciones web y los accesos indebidos entre los vectores | candidata |

### 3.3 Documentación técnica (cuenta para las 8, no para las 5 académicas)

| # | Fuente | Uso | Estado |
|---|---|---|---|
| D1 | Elastic, documentación de Elasticsearch/Logstash/Filebeat 9.x (módulos auditd y apache, ingest pipelines, seguridad) | Implementación (6.2) | candidata |
| D2 | Linux Audit Framework: páginas de manual `auditd(8)`, `auditctl(8)`, `audit.rules(7)`, `ausearch(8)` | Capas del SO (6.3): cómo se agrupan los registros por número de serie | candidata |
| D3 | Apache HTTP Server 2.4, documentación de *Log Files* (formato combined) | Campos de Apache (T2) | candidata |
| D4 | scikit-learn, documentación de `IsolationForest`, y Pedregosa et al. (2011), *Scikit-learn: Machine Learning in Python*, JMLR, 12, 2825–2830 (sin DOI) | Implementación del modelo (2011: no cuenta como reciente) | citada (borrador) |

---

## 4. Plantilla APA 7 (referencia rápida)

- **Revista:** Apellido, A. A., & Apellido, B. B. (Año). Título del artículo. *Nombre de la Revista, Vol*(N), pp–pp. https://doi.org/xxxx
- **Congreso:** Apellido, A. A. (Año). Título. En *Proceedings of …* (pp. xx–yy). Editorial. https://doi.org/xxxx
- **Informe:** Organización. (Año). *Título del informe*. URL
- **Documentación:** Organización. (s.f. o año). *Título de la página*. Recuperado el DD de mes de AAAA, de URL
