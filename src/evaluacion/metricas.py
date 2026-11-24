"""Métricas comunes a Isolation Forest (T5) y a las reglas (T6), para comparar ambos con el mismo código.

Entrada: filas de un dataset de ventanas (dicts con los metadatos de src/extraccion/ventanas.py) y una lista de
alertas booleanas, una por fila. Solo biblioteca estándar.

Definiciones (fijadas antes de ver resultados de prueba):
  - Unidad por ventana: ventana de 30 s. Positiva si etiqueta = 1. Las ventanas ambiguas (solapan el incidente sin
    contener eventos suyos) no cuentan en precisión, recall ni F1 por ventana.
  - Incidente detectado: al menos una alerta en una ventana de esa sesión que contenga eventos del incidente o se
    solape con su intervalo (etiqueta = 1 o ambigua = 1). No hay tolerancia posterior: una alerta después del
    incidente no lo detecta.
  - Tiempo hasta la primera alerta: fin de la primera ventana alertada del incidente − inicio real del incidente.
    La ventana recién se puede evaluar cuando termina, así que ese es el primer momento posible de la alerta
    (sin contar la latencia de ingesta, que se mide en la T7).
  - Falsas alarmas por hora: alertas en ventanas negativas (etiqueta = 0, no ambiguas) dividido por las horas
    observadas (cantidad de ventanas × 30 s).
"""
from datetime import datetime

VENTANA_S = 30


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _ent(v):
    return int(float(v)) if v not in ("", None) else 0


def por_ventana(filas, alertas):
    tp = fp = fn = tn = 0
    for f, a in zip(filas, alertas):
        if _ent(f["ambigua"]):
            continue
        y = _ent(f["etiqueta"])
        if y and a:
            tp += 1
        elif y:
            fn += 1
        elif a:
            fp += 1
        else:
            tn += 1
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec, "f1": f1,
            "fpr": fp / (fp + tn) if fp + tn else 0.0}


def por_incidente(filas, alertas):
    """Una entrada por sesión de incidente: detectado, ventanas alertadas y segundos hasta la primera alerta."""
    sesiones = {}
    for f, a in zip(filas, alertas):
        if not f.get("inicio_incidente"):
            continue
        s = sesiones.setdefault(f["sesion"], {"sesion": f["sesion"], "escenario": f["escenario"],
                                              "inicio_incidente": f["inicio_incidente"], "detectado": False,
                                              "ventanas_incidente": 0, "ventanas_alertadas": 0, "t_primera_alerta_s": None})
        en_incidente = _ent(f["etiqueta"]) or _ent(f["ambigua"])
        if not en_incidente:
            continue
        s["ventanas_incidente"] += 1
        if a:
            s["ventanas_alertadas"] += 1
            t = (_dt(f["fin"]) - _dt(f["inicio_incidente"])).total_seconds()
            if s["t_primera_alerta_s"] is None or t < s["t_primera_alerta_s"]:
                s["t_primera_alerta_s"] = round(t, 1)
            s["detectado"] = True
    return sorted(sesiones.values(), key=lambda s: s["sesion"])


def falsas_alarmas_hora(filas, alertas):
    fp = sum(1 for f, a in zip(filas, alertas) if a and not _ent(f["etiqueta"]) and not _ent(f["ambigua"]))
    horas = len(filas) * VENTANA_S / 3600
    return fp / horas if horas else 0.0, fp, horas


def resumen(filas, alertas):
    v = por_ventana(filas, alertas)
    inc = por_incidente(filas, alertas)
    fah, fp, horas = falsas_alarmas_hora(filas, alertas)
    det = [i for i in inc if i["detectado"]]
    tiempos = sorted(i["t_primera_alerta_s"] for i in det)
    return {
        "ventana": v,
        "incidentes": len(inc), "incidentes_detectados": len(det),
        "recall_incidente": len(det) / len(inc) if inc else 0.0,
        "t_primera_alerta_mediana_s": tiempos[len(tiempos) // 2] if tiempos else None,
        "t_primera_alerta_max_s": tiempos[-1] if tiempos else None,
        "falsas_alarmas_hora": fah, "horas_observadas": horas,
        "detalle_incidentes": inc,
    }


def texto(r, sangria="  "):
    v = r["ventana"]
    t_med = "-" if r["t_primera_alerta_mediana_s"] is None else f"{r['t_primera_alerta_mediana_s']:.1f} s"
    t_max = "-" if r["t_primera_alerta_max_s"] is None else f"{r['t_primera_alerta_max_s']:.1f} s"
    return [
        f"{sangria}Por ventana (30 s): TP={v['tp']} FP={v['fp']} FN={v['fn']} TN={v['tn']}  "
        f"precisión={v['precision']:.3f} recall={v['recall']:.3f} F1={v['f1']:.3f}",
        f"{sangria}Por incidente: {r['incidentes_detectados']}/{r['incidentes']} detectados "
        f"(recall {r['recall_incidente']:.2f}); primera alerta: mediana {t_med}, máximo {t_max}",
        f"{sangria}Falsas alarmas: {r['falsas_alarmas_hora']:.1f} por hora ({v['fp']} en {r['horas_observadas']:.2f} h)",
    ]
