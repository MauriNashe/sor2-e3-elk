#!/usr/bin/env python3
"""Cronología y evaluación de la prueba en vivo (T7). Se corre DESPUÉS de detector_vivo.py:

    python3 src/deteccion/cronologia.py --vivo results/t7/vivo_<fecha> --manifiesto data/vivo/manifiesto.csv

Qué calcula (todo con el reloj de la VM: generadores, agentes, Elasticsearch y detector comparten reloj):
  1. Cronología de cada incidente: inicio real → primer evento registrado → lectura de Filebeat → recepción en
     Logstash → indexación → fin de la ventana alertada → consulta del detector → emisión de la alerta.
  2. Latencia de ingesta de todos los eventos del período, por tramo (lectura, envío, indexación) y por fuente.
  3. Completitud: cada ventana se vuelve a calcular ahora, cuando ya llegó todo, y se compara con lo que vio el
     detector en vivo. La diferencia son eventos que llegaron después de la consulta (la espera fue corta).
  4. Métricas en vivo de cada detector sobre las ventanas de las sesiones (mismas definiciones que T5/T6) y alertas
     fuera de las sesiones.
  5. CPU y memoria por componente (recursos.csv).
Solo biblioteca estándar.
"""
import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in ("extraccion", "evaluacion"):
    sys.path.insert(0, os.path.join(RAIZ, "src", sub))
import ventanas as V  # noqa: E402
import metricas  # noqa: E402
from validar_ingesta import ES_Cliente, leer_env, obtener  # noqa: E402

CAMPOS_LAT = ["lab.filebeat_read", "lab.logstash_received", "lab.es_ingested"]
CONJUNTOS = {"auditd": {"reglas_completo": ["regla_A1", "regla_A2"], "reglas_generico": ["regla_A1"]},
             "apache": {"reglas_completo": ["regla_W1", "regla_W2"]}}
PRINCIPAL = {"auditd": ("IF_auditd_completo", "reglas_completo"), "apache": ("IF_apache_completo", "reglas_completo")}


def leer_csv(ruta):
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def seg(a, b):
    return round((b - a).total_seconds(), 3) if a and b else None


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))] if v else None


def f3(x):
    return "-" if x is None else f"{x:.1f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vivo", required=True, help="directorio results/t7/vivo_<fecha>")
    ap.add_argument("--manifiesto", default="data/vivo/manifiesto.csv")
    args = ap.parse_args()

    with open(os.path.join(args.vivo, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    vivo = leer_csv(os.path.join(args.vivo, "ventanas.csv"))
    sesiones = [s for s in leer_csv(args.manifiesto) if s["estado"] == "ok"]
    env = leer_env(".env")
    es = ES_Cliente("lab_analyst", env["ANALYST_PASSWORD"])
    rep = [f"T7 — Prueba en vivo: {args.vivo}",
           f"Inicio {meta['inicio']}, {meta['minutos']} min, ventanas de {meta['ventana_s']} s, espera {meta['espera_s']} s",
           "Reloj (chronyc tracking): " + ("; ".join(meta.get("reloj", [])) or "sin datos"),
           "Todas las marcas salen del reloj de la VM: no hay desfase entre equipos que corregir.", ""]

    # ---- ventanas recalculadas ahora (offline) para las sesiones de la prueba
    serie_sys, serie_path, serie_web, (t0, t1) = V.traer(es, sesiones)
    offline = {}
    for s in sesiones:
        # Las sesiones arrancaron alineadas al reloj (lote.py --alinear 30) con unos milisegundos de retraso: se
        # redondea el inicio al múltiplo de 30 s más cercano para recalcular EXACTAMENTE las mismas ventanas que el
        # detector (si no, una línea de Apache del segundo justo en el borde cambia de ventana).
        t = V.desde_iso(s["inicio_sesion"]).timestamp()
        s = {**s, "inicio_sesion": V.iso(datetime.fromtimestamp(round(t / 30) * 30, timezone.utc))}
        for f in V.ventanas_sesion(s, serie_sys, serie_path, serie_web):
            offline[(s["fuente"], f["inicio"][:19])] = (s, f)      # clave al segundo: el detector alinea al reloj

    def buscar(fuente, inicio):
        dt = V.desde_iso(inicio)
        for d in (0, -1, 1):
            k = (fuente, V.iso(dt + timedelta(seconds=d))[:19])
            if k in offline:
                return offline[k]
        return None, None

    # ---- 4. métricas en vivo y alertas fuera de sesión
    detectores = defaultdict(list)
    for v in vivo:
        for k in v:
            if (k.startswith("IF_") or k.startswith("regla_")) and not k.endswith("_puntaje") and v[k] != "":
                if k not in detectores[v["fuente"]]:
                    detectores[v["fuente"]].append(k)
    rep.append("== Métricas en vivo (ventanas de las sesiones; mismas definiciones que T5/T6)")
    filas_eval = defaultdict(list)          # fuente -> [(fila offline con etiqueta, fila vivo)]
    fuera = defaultdict(lambda: defaultdict(int))
    for v in vivo:
        s, f = buscar(v["fuente"], v["ventana_inicio"])
        if f is None:
            for det in detectores[v["fuente"]]:
                fuera[v["fuente"]][det] += int(v[det])
            continue
        filas_eval[v["fuente"]].append((f, v))
    for fuente, pares in filas_eval.items():
        offl = [f for f, _ in pares]
        rep.append(f"  {fuente}: {len(pares)} ventanas de sesión "
                   f"({sum(1 for f in offl if f['etiqueta'])} con incidente, {sum(1 for f in offl if f['ambigua'])} ambiguas)")
        dets = detectores[fuente] + list(CONJUNTOS[fuente])
        for det in dets:
            if det in CONJUNTOS[fuente]:
                al = [any(int(v[c]) for c in CONJUNTOS[fuente][det] if c in v) for _, v in pares]
            else:
                al = [bool(int(v[det])) for _, v in pares]
            r = metricas.resumen(offl, al)
            vv = r["ventana"]
            rep.append(f"    {det:<32} TP={vv['tp']} FP={vv['fp']} FN={vv['fn']} TN={vv['tn']}  "
                       f"incidentes {r['incidentes_detectados']}/{r['incidentes']}  "
                       f"falsas alarmas/h {r['falsas_alarmas_hora']:.1f}")
        if fuente in fuera:
            txt = ", ".join(f"{d}={n}" for d, n in fuera[fuente].items() if n) or "ninguna"
            rep.append(f"    Alertas en ventanas fuera de las sesiones de {fuente} (pausas u otra fuente activa): {txt}")
    rep.append("")

    # ---- 1. cronología por incidente
    rep.append("== Cronología de cada incidente (segundos; t=0 es el inicio real del incidente)")
    crono = []
    for s in [s for s in sesiones if s["tipo"] == "incidente"]:
        i0, i1 = V.desde_iso(s["inicio_incidente"]), V.desde_iso(s["fin_incidente"])
        if s["fuente"] == "auditd":
            docs = es.todos("lab-auditd-*", V.q_rango(i0 - timedelta(seconds=2), i1 + timedelta(seconds=2),
                                                      {"term": {"event.action": "syscall"}},
                                                      {"term": {"auditd.log.key": "lab_protegido"}}),
                            ["@timestamp"] + CAMPOS_LAT)
        else:
            docs = es.todos("lab-apache-*", V.q_rango(i0 - timedelta(seconds=2), i1 + timedelta(seconds=2),
                                                      {"term": {"event.dataset": "apache.access"}},
                                                      {"term": {"source.ip": s["ip_atacante"]}}),
                            ["@timestamp"] + CAMPOS_LAT)
        if not docs:
            rep.append(f"  {s['sesion']} {s['escenario']}: sin eventos del incidente en Elasticsearch")
            continue
        primero = min(docs, key=lambda d: (d["@timestamp"], obtener(d, "lab.es_ingested") or ""))
        tg = V.desde_iso(primero["@timestamp"])
        fb, ls, ei = (V.desde_iso(obtener(primero, c) or "") for c in CAMPOS_LAT)
        for familia in PRINCIPAL[s["fuente"]]:
            alertadas = []
            for f, v in filas_eval[s["fuente"]]:
                if f["sesion"] != s["sesion"] or not (f["etiqueta"] or f["ambigua"]):
                    continue
                al = (any(int(v[c]) for c in CONJUNTOS[s["fuente"]][familia]) if familia in CONJUNTOS[s["fuente"]]
                      else bool(int(v[familia])))
                if al:
                    alertadas.append(v)
            fila = {"sesion": s["sesion"], "escenario": s["escenario"], "detector": familia,
                    "inicio_incidente": s["inicio_incidente"], "primer_evento": V.iso(tg),
                    "primer_evento_s": seg(i0, tg), "lectura_filebeat_s": seg(i0, fb), "recepcion_logstash_s": seg(i0, ls),
                    "indexacion_s": seg(i0, ei), "ingesta_primer_evento_s": seg(tg, ei)}
            if alertadas:
                v = min(alertadas, key=lambda x: x["ventana_fin"])
                fv, tc, ta = (V.desde_iso(v[c]) for c in ("ventana_fin", "t_consulta", "t_alerta"))
                ui = V.desde_iso(v.get("ultimo_indexado") or "")
                fila.update(detectado=True, ventana_alertada=v["ventana_inicio"], fin_ventana_s=seg(i0, fv),
                            consulta_s=seg(i0, tc), alerta_s=seg(i0, ta), espera_s=seg(fv, tc),
                            procesamiento_s=seg(tc, ta), margen_ultimo_indexado_s=seg(ui, tc))
            else:
                fila.update(detectado=False)
            crono.append(fila)
            if fila["detectado"]:
                rep.append(f"  {s['sesion']} {s['escenario']} [{familia}]: primer evento {f3(fila['primer_evento_s'])} → "
                           f"Filebeat {f3(fila['lectura_filebeat_s'])} → Logstash {f3(fila['recepcion_logstash_s'])} → "
                           f"indexado {f3(fila['indexacion_s'])} | fin de ventana {f3(fila['fin_ventana_s'])} → consulta "
                           f"{f3(fila['consulta_s'])} → ALERTA {f3(fila['alerta_s'])}  "
                           f"(espera {f3(fila['espera_s'])}, procesamiento {fila['procesamiento_s']:.2f}, "
                           f"el último evento de la ventana se indexó {f3(fila['margen_ultimo_indexado_s'])} s antes de la consulta)")
            else:
                rep.append(f"  {s['sesion']} {s['escenario']} [{familia}]: primer evento {f3(fila['primer_evento_s'])}, "
                           f"indexado {f3(fila['indexacion_s'])} | NO detectado en vivo")
    if crono:
        with open(os.path.join(args.vivo, "cronologia.csv"), "w", newline="", encoding="utf-8") as f:
            campos = list(dict.fromkeys(k for c in crono for k in c))
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(crono)
    rep.append("  La ingesta corre en paralelo con la acumulación de la ventana: la alerta no puede salir antes del fin de")
    rep.append("  la ventana + la espera, y la espera solo alcanza si el último evento ya estaba indexado al consultar.")
    rep.append("")

    # ---- 2. latencia de ingesta de todos los eventos del período
    rep.append("== Latencia de ingesta de todos los eventos de la prueba (s): mediana / p95 / máximo")
    ini = V.desde_iso(meta["inicio"])
    fin_p = ini + timedelta(minutes=float(meta["minutos"]))
    fh_lat = open(os.path.join(args.vivo, "latencias.csv"), "w", newline="", encoding="utf-8")
    w_lat = csv.writer(fh_lat)
    w_lat.writerow(["fuente", "generacion", "lectura_s", "envio_s", "indexacion_s", "total_s"])
    for fuente, indice, filtro in (("auditd", "lab-auditd-*", {"term": {"event.action": "syscall"}}),
                                   ("apache", "lab-apache-*", {"term": {"event.dataset": "apache.access"}})):
        tramos = defaultdict(list)
        for d in es.todos(indice, V.q_rango(ini, fin_p, filtro), ["@timestamp"] + CAMPOS_LAT):
            t = V.desde_iso(d["@timestamp"])
            fb, ls, ei = (V.desde_iso(obtener(d, c) or "") for c in CAMPOS_LAT)
            if fb and ls and ei:
                w_lat.writerow([fuente, d["@timestamp"], round((fb - t).total_seconds(), 3),
                                round((ls - fb).total_seconds(), 3), round((ei - ls).total_seconds(), 3),
                                round((ei - t).total_seconds(), 3)])
                tramos["lectura (generación→Filebeat)"].append((fb - t).total_seconds())
                tramos["envío (Filebeat→Logstash)"].append((ls - fb).total_seconds())
                tramos["indexación (Logstash→ES)"].append((ei - ls).total_seconds())
                tramos["total (generación→indexado)"].append((ei - t).total_seconds())
        n = len(tramos["total (generación→indexado)"])
        rep.append(f"  {fuente} ({n} eventos):")
        for k, v in tramos.items():
            rep.append(f"    {k:<32} {statistics.median(v):7.3f} / {pct(v, 95):7.3f} / {max(v):7.3f}")
    fh_lat.close()
    rep.append("  (Apache registra al segundo: su tramo de lectura incluye hasta 1 s de redondeo.)")
    rep.append("")

    # ---- 3. completitud
    rep.append("== Completitud: lo que vio el detector en vivo vs. lo que hay ahora en Elasticsearch")
    for fuente, campo in (("auditd", "aud_eventos"), ("apache", "web_peticiones")):
        pares = filas_eval.get(fuente, [])
        tarde = [(int(f[campo]) - int(v[campo]), f, v) for f, v in pares]
        con = [t for t in tarde if t[0] > 0]
        tot_off = sum(int(f[campo]) for f, _ in pares)
        rep.append(f"  {fuente}: {len(con)}/{len(pares)} ventanas con eventos que llegaron después de la consulta; "
                   f"{sum(t[0] for t in con)} de {tot_off} eventos ({100 * sum(t[0] for t in con) / tot_off if tot_off else 0:.2f} %)")
        for d, f, v in con[:10]:
            rep.append(f"    {f['sesion']} v{f['ventana']}: en vivo {v[campo]}, ahora {f[campo]} (+{d})")
    rep.append("")

    # ---- 5. recursos
    rep.append("== CPU (% de un núcleo; la VM tiene 4) y memoria (MiB) durante la prueba: media / máximo")
    rec = defaultdict(lambda: ([], []))
    ruta_rec = os.path.join(args.vivo, "recursos.csv")
    if os.path.exists(ruta_rec):
        for r in leer_csv(ruta_rec):
            if r["cpu_pct"] != "":
                rec[r["componente"]][0].append(float(r["cpu_pct"]))
            if r["mem_mib"] != "":
                rec[r["componente"]][1].append(float(r["mem_mib"]))
        for comp, (cpu, mem) in sorted(rec.items()):
            c = f"{statistics.mean(cpu):6.1f} / {max(cpu):6.1f}" if cpu else "      - /      -"
            m = f"{statistics.mean(mem):8.1f} / {max(mem):8.1f}" if mem else ""
            rep.append(f"  {comp:<40} CPU {c}   mem {m}")
        rep.append("  vm_total es el % de toda la VM (4 núcleos = 100 %); el resto, % de un núcleo.")
    out = os.path.join(args.vivo, f"cronologia_{datetime.now():%Y%m%d_%H%M%S}.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print("\n".join(rep))
    print(f"\nReporte: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
