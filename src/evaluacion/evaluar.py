#!/usr/bin/env python3
"""Evaluación consolidada (T8): regenera desde los resultados de T2–T7 todas las tablas y gráficos del informe.

    .venv/bin/python src/evaluacion/evaluar.py

Entradas: data/procesado (T4), data/lote/manifiesto.csv (T3), results/t5, results/t6, la última results/t7/vivo_*,
y opcionalmente el último results/t8/recuentos_*.txt (validar_ingesta.py corrido después del lote).
Salidas en analysis/:
    evaluacion.md                 informe de resultados (tablas en Markdown, referencias a figuras)
    tablas/*.csv                  las mismas tablas en CSV
    figuras/*.png                 matrices de confusión, puntajes, cronología, latencias, recursos, comparación

Definiciones (las mismas de src/evaluacion/metricas.py, fijadas antes de evaluar en prueba):
  - Unidad por ventana: 30 s. Las ventanas ambiguas no cuentan en precisión/recall/F1 por ventana.
  - Asociación alerta–incidente: una alerta detecta un incidente si cae en una ventana de su sesión que contiene
    eventos del incidente o se solapa con su intervalo. Tolerancia adicional: 0 (una alerta posterior no lo detecta).
  - Deduplicación: las alertas de un mismo detector en ventanas consecutivas de una misma sesión forman un
    EPISODIO (lo que vería un analista como una sola alerta). Un episodio es verdadero si alguna de sus ventanas
    tiene incidente o es ambigua; si no, es una falsa alarma.
"""
import argparse
import csv
import glob
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "src", "evaluacion"))
import metricas  # noqa: E402

# detector -> (archivo de predicciones, columna de alerta)
DETECTORES = {
    "auditd": {
        "IF completo": ("t5", "auditd_completo_predicciones.csv", "alerta"),
        "IF sin clave protegido": ("t5", "auditd_sin_clave_protegido_predicciones.csv", "alerta"),
        "Reglas A1 o A2": ("t6", "predicciones_auditd.csv", "reglas_completo"),
        "Regla A1 (genérica)": ("t6", "predicciones_auditd.csv", "reglas_generico"),
    },
    "apache": {
        "IF completo": ("t5", "apache_completo_predicciones.csv", "alerta"),
        "Reglas W1 o W2": ("t6", "predicciones_apache.csv", "reglas_completo"),
        "Regla W3 (por cliente)": ("t6", "predicciones_apache.csv", "W3"),
    },
}
INCIDENTE = {"auditd": "I1", "apache": "I2"}
BENIGNO = {"auditd": "B1", "apache": "B2"}


def leer(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def tabla_md(cab, filas):
    out = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    out += ["| " + " | ".join(str(x) for x in f) + " |" for f in filas]
    return out


def escribir_csv(ruta, cab, filas):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cab)
        w.writerows(filas)


def episodios(filas, alertas):
    """Agrupa alertas en ventanas consecutivas de la misma sesión. Devuelve (verdaderos, falsos)."""
    por_sesion = defaultdict(list)
    for f, a in zip(filas, alertas):
        por_sesion[f["sesion"]].append((int(f["ventana"]), a, int(f["etiqueta"]) or int(f["ambigua"])))
    cuenta = {True: 0, False: 0}
    for vs in por_sesion.values():
        vs.sort()
        episodio, previa = None, None          # episodio: None (ninguno abierto) o si toca el incidente
        for k, a, inc in vs:
            if a:
                if episodio is not None and previa == k - 1:
                    episodio = episodio or bool(inc)
                else:
                    if episodio is not None:
                        cuenta[episodio] += 1
                    episodio = bool(inc)
                previa = k
            elif episodio is not None:
                cuenta[episodio] += 1
                episodio = None
        if episodio is not None:
            cuenta[episodio] += 1
    return cuenta[True], cuenta[False]


def f2(x):
    return "-" if x is None else f"{x:.2f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", default="data/procesado")
    ap.add_argument("--manifiesto", default="data/lote/manifiesto.csv")
    ap.add_argument("--results", default="results")
    ap.add_argument("--salida", default="analysis")
    ap.add_argument("--vivo", help="carpeta de la prueba en vivo (por defecto, la última con cronología)")
    args = ap.parse_args()
    d_tab, d_fig = os.path.join(args.salida, "tablas"), os.path.join(args.salida, "figuras")
    os.makedirs(d_tab, exist_ok=True)
    os.makedirs(d_fig, exist_ok=True)
    man = {s["sesion"]: s for s in leer(args.manifiesto)}
    md = [f"# Evaluación (T8) — generado por `src/evaluacion/evaluar.py` el {datetime.now():%d/%m/%Y %H:%M}", "",
          "Todo lo de este archivo se regenera con el script. Unidad por ventana: **30 s**. "
          "Resultados de **prueba** (sesiones nunca usadas para entrenar ni ajustar), salvo donde se indica.", "",
          "**Asociación alerta–incidente:** una alerta detecta un incidente si cae en una ventana de su sesión con "
          "eventos del incidente o solapada con su intervalo; tolerancia adicional 0. **Deduplicación:** alertas de un "
          "mismo detector en ventanas consecutivas de una sesión = un episodio.", ""]

    comp_cab = ["fuente", "detector", "TP", "FP", "FN", "TN", "precisión", "recall", "F1", "incidentes",
                "t. 1ª alerta mediana (s)", "t. 1ª alerta máx. (s)", "falsas alarmas/h", "episodios", "episodios falsos",
                "episodios falsos/h"]
    comp, incid, fps = [], [], []
    matrices = []
    for fuente, dets in DETECTORES.items():
        ventanas = leer(os.path.join(args.datos, f"ventanas_{fuente}.csv"))
        vmap = {(v["sesion"], v["ventana"]): v for v in ventanas}
        pr = [v for v in ventanas if v["conjunto"] == "prueba"]
        pred = {}
        for nombre, (t, archivo, col) in dets.items():
            ruta = os.path.join(args.results, t, archivo)
            if not os.path.exists(ruta):
                print(f"Falta {ruta}: se omite {fuente}/{nombre}")
                continue
            p = {(r["sesion"], r["ventana"]): r for r in leer(ruta)}
            pred[nombre] = (p, col)
            al = [p[(f["sesion"], f["ventana"])][col] == "1" for f in pr]
            r = metricas.resumen(pr, al)
            v = r["ventana"]
            ep_v, ep_f = episodios(pr, al)
            horas = r["horas_observadas"]
            comp.append([fuente, nombre, v["tp"], v["fp"], v["fn"], v["tn"], f2(v["precision"]), f2(v["recall"]),
                         f2(v["f1"]), f"{r['incidentes_detectados']}/{r['incidentes']}",
                         f2(r["t_primera_alerta_mediana_s"]), f2(r["t_primera_alerta_max_s"]),
                         f2(r["falsas_alarmas_hora"]), ep_v + ep_f, ep_f, f2(ep_f / horas if horas else 0)])
            matrices.append((f"{fuente}: {nombre}", v))
            for d in r["detalle_incidentes"]:
                incid.append((fuente, d["sesion"], nombre, d))
            for f, a in zip(pr, al):
                if a and f["etiqueta"] == "0" and f["ambigua"] == "0":
                    fps.append((fuente, f, nombre))
        # puntajes de IF por clase, con el umbral
        if "IF completo" in pred:
            p, _ = pred["IF completo"]
            cfg = json.load(open(os.path.join(args.results, "t5", f"{fuente}_completo_config.json"), encoding="utf-8"))
            fig, ax = plt.subplots(figsize=(7, 3.2))
            for i, (conj, etq, color, rot) in enumerate((
                    ("entrenamiento", "0", "#4C78A8", "entrenamiento (benignas)"),
                    ("validacion", "0", "#72B7B2", "validación, sin incidente"),
                    ("validacion", "1", "#F58518", "validación, con incidente"),
                    ("prueba", "0", "#54A24B", "prueba, sin incidente"),
                    ("prueba", "1", "#E45756", "prueba, con incidente"))):
                xs = [float(r["puntaje"]) for r in p.values() if r["conjunto"] == conj and r["etiqueta"] == etq
                      and r["ambigua"] == "0"]
                ax.scatter(xs, [i] * len(xs), s=14, alpha=0.7, color=color)
            ax.axvline(cfg["umbral"], color="black", ls="--", lw=1)
            ax.set_ylim(-0.9, 4.5)
            ax.text(cfg["umbral"], -0.7, " umbral", fontsize=8, va="center")
            ax.set_yticks(range(5), ["entrenamiento", "valid. sin inc.", "valid. con inc.", "prueba sin inc.",
                                     "prueba con inc."], fontsize=8)
            ax.set_xlabel("Puntaje de anomalía de Isolation Forest (mayor = más anómalo)")
            ax.set_title(f"{fuente}: puntaje por ventana de 30 s", fontsize=10)
            fig.tight_layout()
            fig.savefig(os.path.join(d_fig, f"puntajes_if_{fuente}.png"), dpi=150)
            plt.close(fig)

    # ---- tabla comparativa
    escribir_csv(os.path.join(d_tab, "comparacion_prueba.csv"), comp_cab, comp)
    md += ["## 1. Comparación ML vs. reglas (prueba)", ""] + tabla_md(comp_cab, comp)
    md += ["", "Pares comparables: *IF completo* vs. *Reglas A1 o A2*; *IF sin clave protegido* vs. *Regla A1* "
           "(ninguno sabe cuál es el archivo vigilado); en Apache, *IF completo* vs. *Reglas W1 o W2*.", ""]
    # misma comparación sin etiquetas (la calcula la T6: reglas con máximo de entrenamiento + 1, IF > máximo)
    ruta_sin = os.path.join(args.results, "t6", "comparacion_sin_etiquetas.csv")
    if os.path.exists(ruta_sin):
        sin = leer(ruta_sin)
        cab_sin = ["fuente", "detector", "precision", "recall", "f1", "incidentes", "falsas_alarmas_hora"]
        filas_sin = [[r[c] for c in cab_sin] for r in sin]
        escribir_csv(os.path.join(d_tab, "comparacion_sin_etiquetas.csv"), cab_sin, filas_sin)
        md += ["### 1.1 La misma comparación sin etiquetas", "",
               "Umbral de cada regla = máximo de entrenamiento + 1 paso (A2 fijo en 1); Isolation Forest alerta si "
               "supera el puntaje máximo de entrenamiento. Ninguno usa las etiquetas de validación.", ""]
        md += tabla_md(cab_sin, filas_sin) + [""]

    # ---- matrices de confusión
    n = len(matrices)
    cols = 4
    filas_fig = (n + cols - 1) // cols
    fig, axs = plt.subplots(filas_fig, cols, figsize=(3.0 * cols, 2.8 * filas_fig))
    axs = axs.flatten() if n > 1 else [axs]
    for ax, (titulo, v) in zip(axs, matrices):
        m = [[v["tn"], v["fp"]], [v["fn"], v["tp"]]]
        ax.imshow(m, cmap="Blues")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, m[i][j], ha="center", va="center", fontsize=12,
                        color="white" if m[i][j] > max(max(m)) / 2 else "black")
        ax.set_xticks([0, 1], ["sin alerta", "alerta"], fontsize=8)
        ax.set_yticks([0, 1], ["sin inc.", "con inc."], fontsize=8)
        ax.set_title(titulo, fontsize=8)
    for ax in axs[n:]:
        ax.axis("off")
    fig.suptitle("Matrices de confusión por ventana de 30 s (prueba)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(d_fig, "matrices_confusion.png"), dpi=150)
    plt.close(fig)
    md += ["![Matrices de confusión](figuras/matrices_confusion.png)", "",
           "![Puntajes auditd](figuras/puntajes_if_auditd.png)", "", "![Puntajes Apache](figuras/puntajes_if_apache.png)", ""]

    # ---- gráfico comparativo
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.4))
    etiquetas = [f"{c[0]}\n{c[1]}" for c in comp]
    for ax, (idx, titulo) in zip(axs, ((8, "F1 por ventana"), (9, "Incidentes detectados (fracción)"),
                                       (12, "Falsas alarmas por hora"))):
        vals = []
        for c in comp:
            x = str(c[idx])
            if "/" in x:
                a, b = x.split("/")
                vals.append(int(a) / int(b) if int(b) else 0.0)
            else:
                vals.append(float(x) if x != "-" else 0.0)
        ax.barh(range(len(comp)), vals, color=["#4C78A8" if "IF" in c[1] else "#F58518" for c in comp])
        ax.set_yticks(range(len(comp)), etiquetas if ax is axs[0] else [""] * len(comp), fontsize=7)
        ax.invert_yaxis()
        ax.set_title(titulo, fontsize=9)
    fig.suptitle("Prueba: Isolation Forest (azul) vs. reglas (naranja)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(d_fig, "comparacion.png"), dpi=150)
    plt.close(fig)
    md += ["![Comparación](figuras/comparacion.png)", ""]

    # ---- incidentes uno por uno
    md += ["## 2. Incidentes de prueba, uno por uno", "",
           "Segundos desde el inicio real del incidente hasta el fin de la primera ventana alertada ("
           "evaluación offline: sin la latencia de ingesta, que se mide en la T7). **no** = no detectado.", ""]
    nombres = defaultdict(list)
    for fuente, ses, nombre, d in incid:
        if nombre not in nombres[fuente]:
            nombres[fuente].append(nombre)
    for fuente in DETECTORES:
        sesiones = sorted({ses for f_, ses, _, _ in incid if f_ == fuente})
        cab = ["sesión", "intensidad (eventos/s)", "duración (s)", "eventos del incidente"] + nombres[fuente]
        filas = []
        for ses in sesiones:
            p = json.loads(man[ses]["parametros"]) if ses in man else {}
            fila = [ses, p.get("inc_tasa", ""), p.get("inc_duracion", ""), man.get(ses, {}).get("evid_incidente", "")]
            for nombre in nombres[fuente]:
                d = next((d for f_, s, n_, d in incid if f_ == fuente and s == ses and n_ == nombre), None)
                fila.append(f"{d['t_primera_alerta_s']:.1f}" if d and d["detectado"] else "**no**")
            filas.append(fila)
        escribir_csv(os.path.join(d_tab, f"incidentes_{fuente}.csv"), cab, filas)
        md += [f"### {fuente} ({INCIDENTE[fuente]})", ""] + tabla_md(cab, filas) + [""]

    # ---- falsos positivos
    md += ["## 3. Falsos positivos (prueba)", "",
           "Ventanas sin incidente que alertaron. *Explicación* = las 3 características de la ventana más alejadas de la "
           "mediana de entrenamiento (columna `explicacion` de Isolation Forest).", ""]
    agrup = defaultdict(list)
    for fuente, f, nombre in fps:
        agrup[(fuente, f["sesion"], f["ventana"])].append(nombre)
    cab = ["fuente", "sesión", "escenario", "ventana", "detectores", "explicación (IF)", "valores clave"]
    filas = []
    for (fuente, ses, ven), dets in sorted(agrup.items()):
        f = next(v for v in leer(os.path.join(args.datos, f"ventanas_{fuente}.csv"))
                 if v["sesion"] == ses and v["ventana"] == ven)
        p_if = os.path.join(args.results, "t5", f"{fuente}_completo_predicciones.csv")
        expl = next((r["explicacion"] for r in leer(p_if) if r["sesion"] == ses and r["ventana"] == ven), "") \
            if os.path.exists(p_if) else ""
        clave = (f"denegados={f['aud_denegados']}, exec={f['aud_exec']}, eventos={f['aud_eventos']}"
                 if fuente == "auditd" else
                 f"peticiones={f['web_peticiones']}, 4xx={f['web_4xx']}, clientes={f['web_clientes']}")
        filas.append([fuente, ses, f["escenario"], ven, ", ".join(dets), expl or "-", clave])
    escribir_csv(os.path.join(d_tab, "falsos_positivos.csv"), cab, filas)
    md += (tabla_md(cab, filas) if filas else ["Ninguno."]) + [""]

    # ---- por escenario
    md += ["## 4. Resumen por escenario (prueba)", ""]
    cab = ["escenario", "sesiones", "ventanas", "con incidente", "ambiguas"] + \
          [f"alertas {n}" for n in ("IF completo", "reglas")]
    filas = []
    for fuente in DETECTORES:
        ventanas = [v for v in leer(os.path.join(args.datos, f"ventanas_{fuente}.csv")) if v["conjunto"] == "prueba"]
        reg = "Reglas A1 o A2" if fuente == "auditd" else "Reglas W1 o W2"
        for esc in (BENIGNO[fuente], INCIDENTE[fuente]):
            vs = [v for v in ventanas if v["escenario"] == esc]
            fila = [esc, len({v["sesion"] for v in vs}), len(vs), sum(v["etiqueta"] == "1" for v in vs),
                    sum(v["ambigua"] == "1" for v in vs)]
            for nombre in ("IF completo", reg):
                ruta = os.path.join(args.results, *DETECTORES[fuente][nombre][:2])
                col = DETECTORES[fuente][nombre][2]
                if os.path.exists(ruta):
                    p = {(r["sesion"], r["ventana"]): r[col] for r in leer(ruta)}
                    fila.append(sum(p[(v["sesion"], v["ventana"])] == "1" for v in vs))
                else:
                    fila.append("-")
            filas.append(fila)
    escribir_csv(os.path.join(d_tab, "por_escenario.csv"), cab, filas)
    md += tabla_md(cab, filas) + [""]

    # ---- estabilidad de IF
    md += ["## 5. Isolation Forest: configuración elegida y estabilidad", ""]
    cab = ["modelo", "hiperparámetros", "umbral", "F1 prueba (10 semillas)", "recall incidente (10 semillas)"]
    filas = []
    for ruta in sorted(glob.glob(os.path.join(args.results, "t5", "*_config.json"))):
        c = json.load(open(ruta, encoding="utf-8"))
        e = c["estabilidad_prueba"]
        filas.append([f"{c['fuente']}_{c['variante']}", ", ".join(f"{k}={v}" for k, v in c["hiperparametros"].items()),
                      f"{c['umbral']:.4f}",
                      f"{statistics.mean(e['f1_ventana']):.3f} ± {statistics.pstdev(e['f1_ventana']):.3f}",
                      f"{statistics.mean(e['recall_incidente']):.2f} ± {statistics.pstdev(e['recall_incidente']):.2f}"])
    md += tabla_md(cab, filas) + [""]

    # ---- T7: cronología, latencias, recursos
    # la corrida más reciente que tenga cronología (las cortadas a mano no la tienen)
    vivos = [args.vivo] if args.vivo else sorted(v for v in glob.glob(os.path.join(args.results, "t7", "vivo_*"))
                                                 if os.path.exists(os.path.join(v, "cronologia.csv")))
    md += ["## 6. Prueba en vivo (T7)", ""]
    if not vivos:
        md += ["Sin resultados de la T7 todavía.", ""]
    else:
        vivo = vivos[-1]
        md += [f"Datos: `{vivo}`.", ""]
        ruta_c = os.path.join(vivo, "cronologia.csv")
        if os.path.exists(ruta_c):
            crono = leer(ruta_c)
            cab = ["sesión", "detector", "primer evento", "indexado", "fin de ventana", "consulta", "ALERTA",
                   "espera", "procesamiento"]
            filas = [[c["sesion"] + " " + c["escenario"], c["detector"], c["primer_evento_s"], c["indexacion_s"],
                      c.get("fin_ventana_s", "-"), c.get("consulta_s", "-"), c.get("alerta_s", "**no**"),
                      c.get("espera_s", "-"), c.get("procesamiento_s", "-")] for c in crono]
            md += ["Segundos desde el inicio real del incidente (t = 0):", ""] + tabla_md(cab, filas) + [""]
            escribir_csv(os.path.join(d_tab, "cronologia_vivo.csv"), cab, filas)
            det = [c for c in crono if c.get("detectado") == "True"]
            if det:
                fig, ax = plt.subplots(figsize=(8, 0.6 + 0.55 * len(det)))
                hitos = [("primer_evento_s", "primer evento", "o", "#4C78A8"), ("indexacion_s", "indexado", "s", "#F58518"),
                         ("fin_ventana_s", "fin de ventana", "|", "#54A24B"), ("consulta_s", "consulta", "^", "#B279A2"),
                         ("alerta_s", "alerta", "*", "#E45756")]
                for i, c in enumerate(det):
                    ax.plot([0, float(c["alerta_s"])], [i, i], color="#BBBBBB", lw=2, zorder=1)
                    for campo, nombre, mk, color in hitos:
                        ax.scatter(float(c[campo]), i, marker=mk, s=70 if campo != "consulta_s" else 40, zorder=2,
                                   color=color, label=nombre if i == 0 else None)
                ax.set_yticks(range(len(det)), [f"{c['sesion']} {c['escenario']} ({c['detector']})" for c in det],
                              fontsize=8)
                ax.axvline(0, color="black", lw=1)
                ax.set_xlabel("segundos desde el inicio real del incidente")
                ax.legend(fontsize=7, ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.25 + 0.05 * (6 - len(det))))
                fig.tight_layout()
                fig.savefig(os.path.join(d_fig, "cronologia_vivo.png"), dpi=150)
                plt.close(fig)
                md += ["![Cronología](figuras/cronologia_vivo.png)", ""]
        ruta_l = os.path.join(vivo, "latencias.csv")
        if os.path.exists(ruta_l):
            lat = leer(ruta_l)
            cab = ["fuente", "tramo", "n", "mediana (s)", "p95 (s)", "máximo (s)"]
            filas, datos_box, etiquetas = [], [], []
            for fuente in ("auditd", "apache"):
                for tramo in ("lectura_s", "envio_s", "indexacion_s", "total_s"):
                    v = sorted(float(r[tramo]) for r in lat if r["fuente"] == fuente)
                    if v:
                        filas.append([fuente, tramo[:-2], len(v), f"{statistics.median(v):.3f}",
                                      f"{v[int(0.95 * (len(v) - 1))]:.3f}", f"{v[-1]:.3f}"])
                        datos_box.append(v)
                        etiquetas.append(f"{fuente}\n{tramo[:-2]}")
            md += ["Latencia de ingesta (todos los eventos de la prueba en vivo):", ""] + tabla_md(cab, filas) + [""]
            escribir_csv(os.path.join(d_tab, "latencia_ingesta.csv"), cab, filas)
            fig, ax = plt.subplots(figsize=(9, 3.2))
            ax.boxplot(datos_box, showfliers=True)
            ax.set_xticks(range(1, len(etiquetas) + 1), etiquetas, fontsize=7)
            ax.set_ylabel("segundos")
            ax.set_title("Latencia de ingesta por tramo", fontsize=10)
            fig.tight_layout()
            fig.savefig(os.path.join(d_fig, "latencia_ingesta.png"), dpi=150)
            plt.close(fig)
            md += ["![Latencia de ingesta](figuras/latencia_ingesta.png)", ""]
        ruta_r = os.path.join(vivo, "recursos.csv")
        if os.path.exists(ruta_r):
            rec = leer(ruta_r)
            series = defaultdict(lambda: ([], [], []))
            for r in rec:
                s = series[r["componente"]]
                s[0].append(datetime.fromisoformat(r["hora"].replace("Z", "+00:00")))
                s[1].append(float(r["cpu_pct"]) if r["cpu_pct"] else None)
                s[2].append(float(r["mem_mib"]) if r["mem_mib"] else None)
            cab = ["componente", "CPU media (%)", "CPU máx. (%)", "memoria media (MiB)", "memoria máx. (MiB)"]
            filas = []
            for comp_, (_, cpu, mem) in sorted(series.items()):
                c = [x for x in cpu if x is not None]
                m = [x for x in mem if x is not None]
                filas.append([comp_, f"{statistics.mean(c):.1f}" if c else "-", f"{max(c):.1f}" if c else "-",
                              f"{statistics.mean(m):.0f}" if m else "-", f"{max(m):.0f}" if m else "-"])
            md += ["CPU (% de un núcleo; `vm_total` = % de toda la VM de 4 núcleos) y memoria:", ""]
            md += tabla_md(cab, filas) + [""]
            escribir_csv(os.path.join(d_tab, "recursos.csv"), cab, filas)
            fig, ax = plt.subplots(figsize=(9, 3.2))
            # solo los componentes del sistema (no los contenedores de cada sesión), con colores fijos
            nombres = {"docker:sor2-e3-es01-1": "Elasticsearch", "docker:sor2-e3-logstash-1": "Logstash",
                       "docker:sor2-e3-kibana-1": "Kibana", "filebeat": "Filebeat", "auditd": "auditd",
                       "apache2": "Apache", "detector": "detector", "vm_total": "VM total (4 núcleos)"}
            colores = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860", "#DA8BC3", "#333333"]
            for (comp_, etiqueta), color in zip(nombres.items(), colores):
                if comp_ in series:
                    t, cpu, _ = series[comp_]
                    ax.plot(t, [x if x is not None else float("nan") for x in cpu], label=etiqueta, lw=1,
                            color=color, ls="--" if comp_ == "vm_total" else "-")
            ax.set_ylabel("CPU (% de un núcleo)")
            ax.set_xlabel("hora (UTC)")
            ax.legend(fontsize=7, ncol=4)
            ax.set_title("CPU durante la prueba en vivo", fontsize=10)
            fig.autofmt_xdate()
            fig.tight_layout()
            fig.savefig(os.path.join(d_fig, "recursos_cpu.png"), dpi=150)
            plt.close(fig)
            md += ["![CPU](figuras/recursos_cpu.png)", ""]
        txts = sorted(glob.glob(os.path.join(vivo, "cronologia_*.txt")))
        if txts:
            lineas = open(txts[-1], encoding="utf-8").read().splitlines()
            try:
                i = next(k for k, l in enumerate(lineas) if l.startswith("== Completitud"))
                j = next(k for k in range(i + 1, len(lineas)) if lineas[k].startswith("=="))
                md += ["Completitud (eventos que llegaron después de la consulta del detector):", "", "```"]
                md += lineas[i + 1:j] + ["```", ""]
            except StopIteration:
                pass

    # ---- pérdidas y parseo
    md += ["## 7. Eventos perdidos y mal parseados", ""]
    lost = [(s["sesion"], s["audit_lost_antes"], s["audit_lost_despues"]) for s in man.values()
            if s["audit_lost_antes"] != s["audit_lost_despues"]]
    md += [f"- auditd (`auditctl -s`, contador `lost` del núcleo antes y después de cada sesión): "
           + ("sin cambios en las 40 sesiones." if not lost else
              "cambió en " + ", ".join(f"{s} ({a}→{b})" for s, a, b in lost))]
    recs = sorted(glob.glob(os.path.join(args.results, "t8", "recuentos_*.txt")))
    if recs:
        lineas = open(recs[-1], encoding="utf-8").read().splitlines()
        i = next((k for k, l in enumerate(lineas) if l.startswith("===== Resumen")), None)
        md += [f"- Logs originales vs. Elasticsearch después del lote (`{recs[-1]}`):", "", "```"]
        md += (lineas[i + 1:i + 6] if i is not None else lineas[:12]) + ["```", ""]
    else:
        md += ["- Falta correr `validar_ingesta.py --salida results/t8` después del lote (guía 08).", ""]

    with open(os.path.join(args.salida, "evaluacion.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nListo: {args.salida}/evaluacion.md, {d_tab}/ y {d_fig}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
