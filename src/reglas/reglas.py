#!/usr/bin/env python3
"""Baseline por reglas con umbrales explícitos (T6) y comparación con Isolation Forest (T5).

    python3 src/reglas/reglas.py

Usa los MISMOS datasets de ventanas (T4), la MISMA división por sesiones y las MISMAS métricas
(src/evaluacion/metricas.py) que Isolation Forest. Solo biblioteca estándar.

Reglas (cada una es un umbral sobre una característica de la ventana de 30 s):
  auditd
    A1  accesos denegados        aud_denegados >= k                  genérica: no sabe qué archivo se protege
                                 (EACCES/EPERM sin /proc: ver la definición en ventanas.py)
    A2  archivo vigilado         aud_clave_protegido >= 1            de firma: cualquier acceso al archivo sensible.
                                                                     Umbral fijo en 1 por definición, no se ajusta
  Apache
    W1  frecuencia de 4xx        web_4xx >= k
    W2  proporción de 4xx        web_frac_4xx >= p  y  web_peticiones >= 10   (con menos de 10 peticiones la
                                                                     proporción es muy inestable; mínimo fijado a priori)
    W3  4xx de un mismo cliente  web_max_4xx_cliente >= k            informativa: concentración por cliente
Conjuntos de reglas que se comparan con Isolation Forest:
    auditd "completo"            A1 o A2      <->  IF auditd_completo
    auditd "generico"            A1           <->  IF auditd_sin_clave_protegido (ninguno de los dos usa la clave)
    apache "completo"            W1 o W2      <->  IF apache_completo  (las dos reglas que nombra la consigna)

Ajuste de umbrales, SIN usar prueba: para cada regla se prueban los valores observados en entrenamiento y validación,
y se elige el que da máximo F1 por ventana en validación (mismo criterio que el umbral de Isolation Forest). Si varios
umbrales empatan, se toma el punto medio del rango empatado (redondeado hacia arriba en los recuentos), para dejar
margen hacia los dos lados. Como referencia se
informa también el umbral "sin etiquetas": el valor más alto visto en entrenamiento (benigno) + 1 (o + 0,01).

Salida en results/t6/: reglas_<fecha>.txt, umbrales.json (los usa la T7), predicciones_<fuente>.csv y
comparacion_prueba.csv (tabla ML vs. reglas en las mismas ventanas de prueba).
"""
import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "src", "evaluacion"))
import metricas  # noqa: E402

MIN_PETICIONES_W2 = 10

REGLAS = {
    "auditd": {
        "A1": {"nombre": "accesos denegados", "campo": "aud_denegados", "ajustable": True},
        "A2": {"nombre": "archivo vigilado", "campo": "aud_clave_protegido", "ajustable": False, "umbral": 1},
    },
    "apache": {
        "W1": {"nombre": "frecuencia de 4xx", "campo": "web_4xx", "ajustable": True},
        "W2": {"nombre": "proporción de 4xx", "campo": "web_frac_4xx", "ajustable": True,
               "condicion": ("web_peticiones", MIN_PETICIONES_W2)},
        "W3": {"nombre": "4xx de un mismo cliente", "campo": "web_max_4xx_cliente", "ajustable": True},
    },
}
CONJUNTOS = {
    "auditd": {"completo": ["A1", "A2"], "generico": ["A1"]},
    "apache": {"completo": ["W1", "W2"]},
}
PAREJA_IF = {("auditd", "completo"): "auditd_completo", ("auditd", "generico"): "auditd_sin_clave_protegido",
             ("apache", "completo"): "apache_completo"}


def leer(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def aplicar(regla, filas, umbral):
    out = []
    for f in filas:
        ok = float(f[regla["campo"]]) >= umbral
        if ok and "condicion" in regla:
            c, minimo = regla["condicion"]
            ok = float(f[c]) >= minimo
        out.append(ok)
    return out


def ajustar(regla, tr, va):
    """Umbral con máximo F1 por ventana en validación; en empate, el del medio del rango empatado."""
    candidatos = sorted({float(f[regla["campo"]]) for f in tr + va} | {float("inf")})
    evals = []
    for u in candidatos:
        r = metricas.por_ventana(va, aplicar(regla, va, u))
        evals.append((u, r["f1"]))
    mejor = max(f1 for _, f1 in evals)
    empatados = [u for u, f1 in evals if abs(f1 - mejor) < 1e-12 and u != float("inf")]
    if not empatados:
        return float("inf"), mejor, []
    lo, hi = min(empatados), max(empatados)
    if regla["campo"].startswith("web_frac"):
        return round((lo + hi) / 2, 4), mejor, empatados
    return float(math.ceil((lo + hi) / 2)), mejor, empatados       # recuentos: umbral entero


def sin_etiquetas(regla, tr):
    m = max(float(f[regla["campo"]]) for f in tr)
    return m + (0.01 if regla["campo"].startswith("web_frac") else 1)


def fmt(u):
    return "nunca" if u == float("inf") else (f"{u:g}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", default="data/procesado")
    ap.add_argument("--t5", default="results/t5", help="predicciones de Isolation Forest para la comparación")
    ap.add_argument("--salida", default="results/t6")
    args = ap.parse_args()
    os.makedirs(args.salida, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    rep = [f"T6 — Baseline por reglas ({sello})", ""]
    umbrales, comparacion, comp_sin = {}, [], []

    for fuente, reglas in REGLAS.items():
        filas = leer(os.path.join(args.datos, f"ventanas_{fuente}.csv"))
        tr = [f for f in filas if f["conjunto"] == "entrenamiento"]
        va = [f for f in filas if f["conjunto"] == "validacion"]
        pr = [f for f in filas if f["conjunto"] == "prueba"]
        rep.append(f"=== {fuente}: entrenamiento {len(tr)}, validación {len(va)}, prueba {len(pr)} ventanas")
        alertas = {}                          # regla -> lista de alertas sobre TODAS las filas
        for cod, regla in reglas.items():
            ref = sin_etiquetas(regla, tr)
            if regla["ajustable"]:
                u, f1v, emp = ajustar(regla, tr, va)
                origen = (f"máximo F1 en validación ({f1v:.3f}); empatan {len(emp)} valores entre "
                          f"{fmt(min(emp)) if emp else '-'} y {fmt(max(emp)) if emp else '-'}")
            else:
                u, origen = regla["umbral"], "fijo por definición"
            umbrales[cod] = {"fuente": fuente, "nombre": regla["nombre"], "campo": regla["campo"], "umbral": u,
                             "condicion": regla.get("condicion"), "criterio": origen, "umbral_sin_etiquetas": ref}
            cond = f" y {regla['condicion'][0]} >= {regla['condicion'][1]}" if "condicion" in regla else ""
            rep.append(f"  {cod} {regla['nombre']}: {regla['campo']} >= {fmt(u)}{cond}")
            rep.append(f"     criterio: {origen}")
            rep.append(f"     referencia sin etiquetas (máximo de entrenamiento + 1 paso): {fmt(ref)}")
            alertas[cod] = aplicar(regla, filas, u)
            for nombre, conj, fs in (("validación", "validacion", va), ("prueba", "prueba", pr)):
                idx = [i for i, f in enumerate(filas) if f["conjunto"] == conj]
                r = metricas.resumen(fs, [alertas[cod][i] for i in idx])
                rep.append(f"     {nombre}:")
                rep += metricas.texto(r, "       ")
        # conjuntos de reglas y comparación con Isolation Forest, en prueba
        idx_pr = [i for i, f in enumerate(filas) if f["conjunto"] == "prueba"]
        for nombre_conj, cods in CONJUNTOS[fuente].items():
            al = [any(alertas[c][i] for c in cods) for i in range(len(filas))]
            alertas[f"reglas_{nombre_conj}"] = al
            r_reg = metricas.resumen(pr, [al[i] for i in idx_pr])
            rep.append(f"  Reglas '{nombre_conj}' ({' o '.join(cods)}) — prueba:")
            rep += metricas.texto(r_reg, "     ")
            comparacion.append(fila_comp(fuente, f"reglas_{nombre_conj}", r_reg))
            # Isolation Forest sobre las mismas ventanas
            ruta_if = os.path.join(args.t5, f"{PAREJA_IF[(fuente, nombre_conj)]}_predicciones.csv")
            if not os.path.exists(ruta_if):
                rep.append(f"  (sin {ruta_if}: correr primero la T5 para comparar)")
                continue
            pred_if = {(p["sesion"], p["ventana"]): p["alerta"] == "1" for p in leer(ruta_if)}
            al_if = [pred_if[(f["sesion"], f["ventana"])] for f in pr]
            r_if = metricas.resumen(pr, al_if)
            # Contraste SIN etiquetas: reglas con umbral = máximo de entrenamiento + 1 paso (A2 queda fijo en 1);
            # IF con umbral = puntaje máximo de entrenamiento (mismo criterio que la T5: alerta si lo supera)
            u_ref = {c: umbrales[c]["umbral_sin_etiquetas"] if reglas[c]["ajustable"] else umbrales[c]["umbral"]
                     for c in cods}
            al_ref = [any(aplicar(reglas[c], [f], u_ref[c])[0] for c in cods) for f in pr]
            preds = leer(ruta_if)
            max_tr = max(float(p["puntaje"]) for p in preds if p["conjunto"] == "entrenamiento")
            sc_if = {(p["sesion"], p["ventana"]): float(p["puntaje"]) for p in preds}
            al_if_ref = [sc_if[(f["sesion"], f["ventana"])] > max_tr for f in pr]
            comp_sin.append(fila_comp(fuente, f"reglas_{nombre_conj}", metricas.resumen(pr, al_ref)))
            comp_sin.append(fila_comp(fuente, f"IF_{PAREJA_IF[(fuente, nombre_conj)]}", metricas.resumen(pr, al_if_ref)))
            rep.append(f"  Isolation Forest '{PAREJA_IF[(fuente, nombre_conj)]}' — mismas ventanas de prueba:")
            rep += metricas.texto(r_if, "     ")
            comparacion.append(fila_comp(fuente, f"IF_{PAREJA_IF[(fuente, nombre_conj)]}", r_if))
            rep.append("  Incidente por incidente (prueba): primera alerta en segundos desde el inicio real")
            rep.append(f"     {'sesión':<8}{'reglas':>12}{'IF':>12}")
            det_if = {d["sesion"]: d for d in r_if["detalle_incidentes"]}
            for d in r_reg["detalle_incidentes"]:
                e = det_if.get(d["sesion"], {})
                rep.append(f"     {d['sesion'] + ' ' + d['escenario']:<8}"
                           f"{(str(d['t_primera_alerta_s']) + ' s') if d['detectado'] else 'no':>12}"
                           f"{(str(e.get('t_primera_alerta_s')) + ' s') if e.get('detectado') else 'no':>12}")
            # falsos positivos de cada uno, por ventana
            fp_reg = [f"{f['sesion']}/v{f['ventana']}" for f, a in zip(pr, [al[i] for i in idx_pr])
                      if a and f["etiqueta"] == "0" and f["ambigua"] == "0"]
            fp_if = [f"{f['sesion']}/v{f['ventana']}" for f, a in zip(pr, al_if)
                     if a and f["etiqueta"] == "0" and f["ambigua"] == "0"]
            rep.append(f"  Falsos positivos en prueba — reglas: {', '.join(fp_reg) or 'ninguno'}; "
                       f"IF: {', '.join(fp_if) or 'ninguno'}")
        rep.append("")
        # predicciones por ventana
        with open(os.path.join(args.salida, f"predicciones_{fuente}.csv"), "w", newline="", encoding="utf-8") as fh:
            meta = ["sesion", "escenario", "conjunto", "ventana", "inicio", "fin", "inicio_incidente", "etiqueta", "ambigua"]
            w = csv.DictWriter(fh, fieldnames=meta + list(alertas))
            w.writeheader()
            for i, f in enumerate(filas):
                w.writerow({**{c: f[c] for c in meta}, **{k: int(v[i]) for k, v in alertas.items()}})

    with open(os.path.join(args.salida, "umbrales.json"), "w", encoding="utf-8") as f:
        json.dump({"fecha": sello, "reglas": umbrales, "conjuntos": CONJUNTOS}, f, indent=2, ensure_ascii=False,
                  default=lambda x: None if x == float("inf") else x)
    with open(os.path.join(args.salida, "comparacion_prueba.csv"), "w", newline="", encoding="utf-8") as f:
        if comparacion:
            w = csv.DictWriter(f, fieldnames=list(comparacion[0]))
            w.writeheader()
            w.writerows(comparacion)
    with open(os.path.join(args.salida, "comparacion_sin_etiquetas.csv"), "w", newline="", encoding="utf-8") as f:
        if comp_sin:
            w = csv.DictWriter(f, fieldnames=list(comp_sin[0]))
            w.writeheader()
            w.writerows(comp_sin)
    for titulo, filas_c in ((["=== Tabla comparativa en prueba (mismas ventanas; unidad por ventana = 30 s)",
                              "    umbrales calibrados con máximo F1 en las etiquetas de validación"], comparacion),
                            (["=== Misma tabla SIN etiquetas: reglas con máximo de entrenamiento + 1 paso (A2 fijo en 1);",
                              "    IF con alerta si supera el puntaje máximo de entrenamiento"], comp_sin)):
        rep += titulo
        rep.append(f"  {'fuente':<8}{'detector':<36}{'prec':>6}{'rec':>6}{'F1':>6}{'inc':>7}{'t_med':>8}{'FA/h':>7}")
        for c in filas_c:
            rep.append(f"  {c['fuente']:<8}{c['detector']:<36}{c['precision']:>6.2f}{c['recall']:>6.2f}{c['f1']:>6.2f}"
                       f"{c['incidentes']:>7}{(str(c['t_mediana_s']) if c['t_mediana_s'] is not None else '-'):>8}"
                       f"{c['falsas_alarmas_hora']:>7.1f}")
        rep.append("")
    ruta = os.path.join(args.salida, f"reglas_{sello}.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print("\n".join(rep))
    print(f"\nResultados en {args.salida}/ ; reporte en {ruta}")
    return 0


def fila_comp(fuente, detector, r):
    v = r["ventana"]
    return {"fuente": fuente, "detector": detector, "tp": v["tp"], "fp": v["fp"], "fn": v["fn"], "tn": v["tn"],
            "precision": round(v["precision"], 4), "recall": round(v["recall"], 4), "f1": round(v["f1"], 4),
            "incidentes": f"{r['incidentes_detectados']}/{r['incidentes']}",
            "t_mediana_s": r["t_primera_alerta_mediana_s"], "t_max_s": r["t_primera_alerta_max_s"],
            "falsas_alarmas_hora": round(r["falsas_alarmas_hora"], 2)}


if __name__ == "__main__":
    sys.exit(main())
