#!/usr/bin/env python3
"""Detector de anomalías Isolation Forest (T5), uno por fuente.

    .venv/bin/python src/modelos/isolation_forest.py

Entrada: data/procesado/ventanas_auditd.csv y ventanas_apache.csv (T4).
Salida en results/t5/:
    resumen_<fecha>.txt                       búsqueda de hiperparámetros, umbral, métricas y estabilidad por semilla
    <fuente>_<variante>_config.json           características, hiperparámetros, umbral, semilla, versiones, hash de datos
    <fuente>_<variante>_predicciones.csv      puntaje y alerta de cada ventana (todos los conjuntos)
    modelos/<fuente>_<variante>.joblib        modelo entrenado + transformación + umbral (lo usa la T7)

Protocolo (división por sesiones completas, fijada en la T3 antes de generar datos):
  - Entrenamiento: solo ventanas de sesiones benignas del conjunto "entrenamiento". El modelo no ve incidentes.
  - Validación: se eligen los hiperparámetros (precisión promedio, AP) y el umbral (máximo F1 por ventana).
  - Prueba: se evalúa UNA vez con el modelo y el umbral ya fijados.
  - Variantes: auditd "completo" y "sin_clave_protegido" (ablación: sin la característica específica del escenario
    I1, para ver si el resto alcanza); Apache "completo".
  - Cada ventana se puntúa solo con sus propias características: no usa eventos posteriores a la ventana.
"""
import argparse
import csv
import hashlib
import itertools
import json
import os
import platform
import sys
from datetime import datetime

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "src", "extraccion"))
sys.path.insert(0, os.path.join(RAIZ, "src", "evaluacion"))
from ventanas import NOMBRES_APACHE, NOMBRES_AUDITD  # noqa: E402
import metricas  # noqa: E402

VARIANTES = {
    "auditd": {"completo": NOMBRES_AUDITD,
               "sin_clave_protegido": [c for c in NOMBRES_AUDITD if c != "aud_clave_protegido"]},
    "apache": {"completo": NOMBRES_APACHE},
}
# La primera combinación son los valores por defecto de scikit-learn: en caso de empate se prefiere la más simple.
GRILLA = {
    "transformacion": ["ninguna", "log1p"],
    "n_estimators": [100, 300],
    "max_samples": ["auto", 16, 8],
    "max_features": [1.0, 0.6],
}
N_SEMILLAS_ESTABILIDAD = 10


# ------------------------------------------------------------------ datos
def leer(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def matriz(filas, caract):
    return np.array([[float(f[c]) for c in caract] for f in filas], dtype=float)


def transformar(X, t):
    return np.log1p(X) if t == "log1p" else X


def y_de(filas):
    return np.array([int(f["etiqueta"]) for f in filas])


def no_ambiguas(filas):
    return np.array([f["ambigua"] in ("0", 0) for f in filas])


# ------------------------------------------------------------------ modelo
def entrenar(Xtr, cfg, semilla):
    m = IsolationForest(n_estimators=cfg["n_estimators"], max_samples=cfg["max_samples"],
                        max_features=cfg["max_features"], random_state=semilla, n_jobs=1)
    m.fit(transformar(Xtr, cfg["transformacion"]))
    return m


def puntaje(m, X, t):
    """Puntaje de anomalía: mayor = más anómalo (opuesto de score_samples)."""
    return -m.score_samples(transformar(X, t))


def umbral_max_f1(s, y):
    """Umbral que maximiza F1 en validación. Se ubica a mitad de camino entre el último puntaje alertado y el
    siguiente, para no quedar pegado a un valor observado. En empate, el que alerta menos ventanas."""
    orden = np.argsort(-s)
    s_ord, y_ord = s[orden], y[orden]
    mejor = (-1.0, 0)
    tp = 0
    for i in range(len(s_ord)):
        tp += y_ord[i]
        if i + 1 < len(s_ord) and s_ord[i + 1] == s_ord[i]:
            continue                                   # no cortar entre puntajes iguales
        prec, rec = tp / (i + 1), tp / max(1, y.sum())
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        if f1 > mejor[0] + 1e-12:
            mejor = (f1, i + 1)
    k = mejor[1]
    if k >= len(s_ord):
        return float(s_ord[-1]) - 1e-9
    return float((s_ord[k - 1] + s_ord[k]) / 2)


def explicar(x, med, escala, caract, n=3, crudo=None):
    """Las n características más alejadas de la mediana de entrenamiento (en unidades de dispersión robusta).

    x, med y escala están en el espacio en que trabaja el modelo (con log1p si corresponde); el valor que se muestra
    es el original de la ventana (crudo), para que se pueda leer."""
    z = (x - med) / escala
    v = x if crudo is None else crudo
    idx = np.argsort(-np.abs(z))[:n]
    return "; ".join(f"{caract[i]}={v[i]:g} (z={z[i]:+.1f})" for i in idx if abs(z[i]) >= 1)


# ------------------------------------------------------------------ una fuente y variante
def correr(fuente, variante, caract, filas, ruta_datos, args, rep):
    tr = [f for f in filas if f["conjunto"] == "entrenamiento"]
    va = [f for f in filas if f["conjunto"] == "validacion"]
    pr = [f for f in filas if f["conjunto"] == "prueba"]
    assert all(f["etiqueta"] == "0" for f in tr), "hay ventanas de incidente en entrenamiento"
    Xtr, Xva, Xpr = matriz(tr, caract), matriz(va, caract), matriz(pr, caract)
    yva, mva = y_de(va), no_ambiguas(va)

    rep += [f"=== {fuente} / {variante}: {len(caract)} características",
            f"  Ventanas: entrenamiento {len(tr)} ({len({f['sesion'] for f in tr})} sesiones), "
            f"validación {len(va)} ({int(yva.sum())} positivas, {int((~mva).sum())} ambiguas), "
            f"prueba {len(pr)} ({int(y_de(pr).sum())} positivas, {int((~no_ambiguas(pr)).sum())} ambiguas)"]

    # 1) hiperparámetros en validación
    claves = list(GRILLA)
    resultados = []
    for i, valores in enumerate(itertools.product(*GRILLA.values())):
        cfg = dict(zip(claves, valores))
        m = entrenar(Xtr, cfg, args.semilla)
        s = puntaje(m, Xva, cfg["transformacion"])[mva]
        resultados.append({**cfg, "ap": average_precision_score(yva[mva], s), "roc_auc": roc_auc_score(yva[mva], s),
                           "orden": i})
    resultados.sort(key=lambda r: (-round(r["ap"], 6), -round(r["roc_auc"], 6), r["orden"]))
    cfg = {k: resultados[0][k] for k in claves}
    rep.append("  Búsqueda en validación (mejores 5 de %d; criterio: AP, luego ROC-AUC, luego la más simple):"
               % len(resultados))
    for r in resultados[:5]:
        rep.append(f"    AP={r['ap']:.3f} ROC-AUC={r['roc_auc']:.3f}  " + " ".join(f"{k}={r[k]}" for k in claves))
    rep.append(f"  Elegida: {cfg}")

    # 2) modelo final y umbral en validación
    m = entrenar(Xtr, cfg, args.semilla)
    s_tr, s_va, s_pr = (puntaje(m, X, cfg["transformacion"]) for X in (Xtr, Xva, Xpr))
    umbral = umbral_max_f1(s_va[mva], yva[mva])
    rep.append(f"  Umbral (máximo F1 en validación): {umbral:.4f}   "
               f"[puntajes de entrenamiento: mediana {np.median(s_tr):.4f}, máximo {s_tr.max():.4f}]")

    # 3) evaluación
    for nombre, fs, s in (("Validación", va, s_va), ("Prueba", pr, s_pr)):
        r = metricas.resumen(fs, list(s >= umbral))
        rep.append(f"  {nombre}:")
        rep += metricas.texto(r, "    ")
        if nombre == "Prueba":
            res_prueba = r
            for inc in r["detalle_incidentes"]:
                rep.append(f"      {inc['sesion']} {inc['escenario']}: "
                           f"{'detectado' if inc['detectado'] else 'NO detectado'}, "
                           f"{inc['ventanas_alertadas']}/{inc['ventanas_incidente']} ventanas, "
                           f"primera alerta {inc['t_primera_alerta_s']} s")
    # umbral alternativo sin usar incidentes: el puntaje más alto visto en entrenamiento
    r_alt = metricas.resumen(pr, list(s_pr > s_tr.max()))
    rep.append("  Comparación — umbral sin etiquetas (máximo de entrenamiento), en prueba:")
    rep += metricas.texto(r_alt, "    ")

    # 4) estabilidad frente a la semilla (misma configuración; umbral recalculado en validación cada vez)
    f1s, recs, fahs = [], [], []
    for k in range(1, N_SEMILLAS_ESTABILIDAD + 1):
        mk = entrenar(Xtr, cfg, args.semilla + k)
        u = umbral_max_f1(puntaje(mk, Xva, cfg["transformacion"])[mva], yva[mva])
        r = metricas.resumen(pr, list(puntaje(mk, Xpr, cfg["transformacion"]) >= u))
        f1s.append(r["ventana"]["f1"]); recs.append(r["recall_incidente"]); fahs.append(r["falsas_alarmas_hora"])
    rep.append(f"  Estabilidad en prueba con {N_SEMILLAS_ESTABILIDAD} semillas: F1 por ventana "
               f"{np.mean(f1s):.3f} ± {np.std(f1s):.3f}; recall por incidente {np.mean(recs):.2f} ± {np.std(recs):.2f}; "
               f"falsas alarmas/h {np.mean(fahs):.1f} ± {np.std(fahs):.1f}")
    rep.append("")

    # 5) guardar
    base = f"{fuente}_{variante}"
    Xtr_t = transformar(Xtr, cfg["transformacion"])
    med = np.median(Xtr_t, axis=0)
    escala = np.percentile(Xtr_t, 75, axis=0) - np.percentile(Xtr_t, 25, axis=0)
    escala = np.where(escala > 0, escala, np.maximum(np.std(Xtr_t, axis=0), 1.0))
    os.makedirs(os.path.join(args.salida, "modelos"), exist_ok=True)
    joblib.dump({"modelo": m, "caracteristicas": caract, "transformacion": cfg["transformacion"], "umbral": umbral,
                 "mediana": med, "escala": escala, "fuente": fuente, "variante": variante},
                os.path.join(args.salida, "modelos", base + ".joblib"))
    with open(os.path.join(args.salida, base + "_predicciones.csv"), "w", newline="", encoding="utf-8") as f:
        campos = ["sesion", "escenario", "conjunto", "ventana", "inicio", "fin", "inicio_incidente", "etiqueta",
                  "ambigua", "puntaje", "alerta", "explicacion"]
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for fs, X, s in ((tr, Xtr, s_tr), (va, Xva, s_va), (pr, Xpr, s_pr)):
            Xt = transformar(X, cfg["transformacion"])
            for fila, x, xc, sc in zip(fs, Xt, X, s):
                al = sc >= umbral
                w.writerow({**{c: fila[c] for c in campos[:9]}, "puntaje": round(float(sc), 5), "alerta": int(al),
                            "explicacion": explicar(x, med, escala, caract, crudo=xc) if al else ""})
    with open(os.path.join(args.salida, base + "_config.json"), "w", encoding="utf-8") as f:
        json.dump({"fuente": fuente, "variante": variante, "fecha": datetime.now().isoformat(timespec="seconds"),
                   "datos": {"archivo": ruta_datos, "sha256": sha256(ruta_datos)},
                   "caracteristicas": caract, "hiperparametros": cfg, "semilla": args.semilla, "umbral": umbral,
                   "criterio_umbral": "máximo F1 por ventana en validación", "grilla": GRILLA,
                   "busqueda": resultados, "metricas_prueba": {k: v for k, v in res_prueba.items()},
                   "estabilidad_prueba": {"f1_ventana": f1s, "recall_incidente": recs, "falsas_alarmas_hora": fahs},
                   "versiones": {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                                 "numpy": np.__version__}},
                  f, indent=2, ensure_ascii=False, default=float)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", default="data/procesado")
    ap.add_argument("--salida", default="results/t5")
    ap.add_argument("--semilla", type=int, default=20261120)
    args = ap.parse_args()

    os.makedirs(args.salida, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    rep = [f"T5 — Isolation Forest ({sello})",
           f"Python {platform.python_version()}, scikit-learn {sklearn.__version__}, numpy {np.__version__}; "
           f"semilla {args.semilla}", ""]
    for fuente, variantes in VARIANTES.items():
        ruta = os.path.join(args.datos, f"ventanas_{fuente}.csv")
        filas = leer(ruta)
        for variante, caract in variantes.items():
            correr(fuente, variante, caract, filas, ruta, args, rep)
    ruta_rep = os.path.join(args.salida, f"resumen_{sello}.txt")
    with open(ruta_rep, "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print("\n".join(rep))
    print(f"Resultados en {args.salida}/ ; resumen en {ruta_rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
