#!/usr/bin/env python3
"""Diagnóstico de la diferencia ES vs. logs en los eventos del incidente I1 (T4).

ventanas.py cuenta los SYSCALL con clave lab_protegido en las 6 ventanas de la sesión (180 s, cualquier uid);
lote.py (T3) contó en audit.log solo los del uid de labuser dentro de [inicio_incidente, fin_incidente].
Este script lista, para cada sesión I1, los registros de Elasticsearch que caen fuera de ese criterio y, si se
corre con sudo, busca la línea original en audit.log por su número de serie.

Uso (en la VM, desde la raíz del repo):
    sudo python3 src/extraccion/diag_incidente.py --manifiesto data/lote/manifiesto.csv
"""
import argparse
import csv
import glob
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validar_ingesta import ES_Cliente, leer_env, obtener  # noqa: E402
from ventanas import N_VENTANAS, UID_LAB, VENTANA_S, desde_iso, iso, q_rango  # noqa: E402

CAMPOS = ["@timestamp", "auditd.log.sequence", "auditd.log.syscall", "auditd.log.success", "user.id",
          "process.executable", "process.pid", "process.parent.pid", "auditd.log.name"]


def linea_original(serie):
    """Líneas de audit.log con ese número de serie (requiere sudo)."""
    marca = f":{serie}):"
    res = []
    for p in sorted(glob.glob("/var/log/audit/audit.log*")):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                res += [ln.rstrip() for ln in f if marca in ln]
        except PermissionError:
            return ["(sin permiso para leer audit.log: correr con sudo)"]
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifiesto", default="data/lote/manifiesto.csv")
    ap.add_argument("--solo-denegados", action="store_true", help="omitir la parte de las sesiones I1")
    args = ap.parse_args()
    env = leer_env(".env")
    es = ES_Cliente("lab_analyst", env["ANALYST_PASSWORD"])
    with open(args.manifiesto, newline="", encoding="utf-8") as f:
        sesiones = [s for s in csv.DictReader(f) if s["escenario"] == "I1" and s["estado"] == "ok"]
    if args.solo_denegados:
        sesiones = []

    for s in sesiones:
        t0 = desde_iso(s["inicio_sesion"])
        i0, i1 = desde_iso(s["inicio_incidente"]), desde_iso(s["fin_incidente"])
        docs = es.todos("lab-auditd-*", q_rango(t0, t0 + timedelta(seconds=VENTANA_S * N_VENTANAS),
                                                {"term": {"event.action": "syscall"}},
                                                {"term": {"auditd.log.key": "lab_protegido"}}), CAMPOS)
        docs.sort(key=lambda d: d["@timestamp"])
        dentro = [d for d in docs if i0 <= desde_iso(d["@timestamp"]) <= i1 and str(obtener(d, "user.id")) == UID_LAB]
        series = [obtener(d, "auditd.log.sequence") for d in docs]
        dup = len(series) - len(set(series))
        print(f"{s['sesion']} ES={len(docs)} dentro_del_criterio_T3={len(dentro)} manifiesto={s['evid_incidente']} "
              f"series_duplicadas={dup}  incidente {iso(i0)} – {iso(i1)}")
        for d in docs:
            t = desde_iso(d["@timestamp"])
            uid = str(obtener(d, "user.id"))
            if d in dentro:
                continue
            motivo = []
            if t < i0:
                motivo.append(f"{(i0 - t).total_seconds():.3f} s ANTES del inicio")
            if t > i1:
                motivo.append(f"{(t - i1).total_seconds():.3f} s DESPUÉS del fin")
            if uid != UID_LAB:
                motivo.append(f"uid={uid}")
            serie = obtener(d, "auditd.log.sequence")
            print(f"   fuera: {d['@timestamp']} serie={serie} syscall={obtener(d, 'auditd.log.syscall')} "
                  f"exito={obtener(d, 'auditd.log.success')} exe={obtener(d, 'process.executable')} "
                  f"pid={obtener(d, 'process.pid')} ppid={obtener(d, 'process.parent.pid')} -> {', '.join(motivo)}")
            for ln in linea_original(serie):
                print(f"      {ln[:400]}")
        if dup:
            print("   (hay números de serie repetidos en ES: documentos duplicados)")

    # --- De dónde salen los accesos denegados de fondo (primera sesión B1 y primera I1)
    with open(args.manifiesto, newline="", encoding="utf-8") as f:
        todas = [s for s in csv.DictReader(f) if s["estado"] == "ok"]
    for esc in ("B1", "I1"):
        s = next(x for x in todas if x["escenario"] == esc)
        t0 = desde_iso(s["inicio_sesion"])
        rango = (t0, t0 + timedelta(seconds=VENTANA_S * N_VENTANAS))
        sysc = es.todos("lab-auditd-*", q_rango(*rango, {"term": {"event.action": "syscall"}},
                                               {"term": {"auditd.log.success": "no"}}),
                        CAMPOS + ["auditd.log.key", "process.exit_code", "process.name"])
        paths = es.todos("lab-auditd-*", q_rango(*rango, {"term": {"event.action": "path"}}),
                         ["auditd.log.sequence", "auditd.log.name"])
        nombres = {}
        for p in paths:
            nombres.setdefault(obtener(p, "auditd.log.sequence"), []).append(obtener(p, "auditd.log.name"))
        grupos, archivos, ejemplos = {}, {}, {}
        for d in sysc:
            k = (str(obtener(d, "user.id")), obtener(d, "process.executable"), str(obtener(d, "auditd.log.syscall")),
                 obtener(d, "auditd.log.key"), str(obtener(d, "process.exit_code")))
            grupos[k] = grupos.get(k, 0) + 1
            ejemplos.setdefault(k, []).append(obtener(d, "auditd.log.sequence"))
            for n in nombres.get(obtener(d, "auditd.log.sequence"), []):
                archivos[n] = archivos.get(n, 0) + 1
        print(f"\n== Denegados en {s['sesion']} {esc} (180 s): {len(sysc)} SYSCALL con success=no")
        print("   cantidad  uid   syscall  clave           ret    ejecutable")
        for k, n in sorted(grupos.items(), key=lambda x: -x[1])[:12]:
            print(f"   {n:8d}  {k[0]:5s} {k[2]:8s} {str(k[3]):15s} {k[4]:6s} {k[1]}")
        print("   Archivos más frecuentes en esos SYSCALL (registros PATH):")
        for n, c in sorted(archivos.items(), key=lambda x: -x[1])[:12]:
            print(f"   {c:8d}  {n}")
        if esc == "B1":
            print("   Ejemplos crudos de audit.log (2 por grupo, 3 grupos más frecuentes):")
            for k, _ in sorted(grupos.items(), key=lambda x: -x[1])[:3]:
                print(f"   -- {k[1]} syscall={k[2]} ret={k[4]}")
                for serie in ejemplos[k][:2]:
                    for ln in linea_original(serie):
                        if "type=PROCTITLE" not in ln:
                            print(f"      {ln[:260]}")
        # Archivos de los denegados por permiso (EACCES/EPERM), agrupados por prefijo
        prefijos = {}
        for d in sysc:
            if str(obtener(d, "process.exit_code")) in ("-13", "-1"):
                for n in nombres.get(obtener(d, "auditd.log.sequence"), []):
                    p = "/".join(str(n).split("/")[:2]) if str(n).startswith("/") else f"(relativo) {n}"
                    prefijos[p] = prefijos.get(p, 0) + 1
        print("   Denegados por permiso (ret -13/-1) según el primer tramo de la ruta:")
        for p, c in sorted(prefijos.items(), key=lambda x: -x[1])[:10]:
            print(f"   {c:8d}  {p}")


if __name__ == "__main__":
    main()
