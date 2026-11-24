#!/usr/bin/env python3
"""Detector en vivo (T7): cada 30 s consulta Elasticsearch, arma la ventana que acaba de cerrar, aplica Isolation
Forest (T5) y las reglas (T6), y registra alertas con todas sus marcas de tiempo.

    .venv/bin/python src/deteccion/detector_vivo.py --minutos 20

Funcionamiento:
  - Ventanas de 30 s ALINEADAS AL RELOJ ([hh:mm:00, hh:mm:30), [hh:mm:30, hh:mm+1:00), …): en operación el detector
    no sabe cuándo empieza una "sesión". Para la prueba, lote.py --alinear 30 hace coincidir las sesiones con ellas.
  - La ventana [a, b) se procesa recién en b + ESPERA: hay que dar tiempo a que los eventos lleguen a Elasticsearch
    (T2: ~13–19 s de ingesta más hasta 5 s de refresco del índice). Lo que llegue después de la consulta se pierde
    para esa ventana; cronologia.py mide cuántos eventos llegaron tarde.
  - Usa SOLO eventos de la ventana: nada posterior a su fin entra en la decisión.
  - Marcas de tiempo de cada ventana: fin de la ventana, inicio de la consulta, emisión de la alerta; y de los
    eventos: generación (@timestamp), lectura de Filebeat, recepción en Logstash e indexación en Elasticsearch.
  - Las alertas se escriben en results/t7/vivo_<fecha>/alertas.jsonl y en el índice lab-alertas-AAAA.MM.DD
    (Kibana, T8). Un hilo aparte registra CPU y memoria del stack, de los agentes y del propio detector.
"""
import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import joblib
import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in ("extraccion", "modelos"):
    sys.path.insert(0, os.path.join(RAIZ, "src", sub))
import ventanas as V  # noqa: E402
from validar_ingesta import ES_Cliente, leer_env, obtener  # noqa: E402
from isolation_forest import explicar, transformar  # noqa: E402

VENTANA = 30
MODELOS = {"auditd": ["auditd_completo", "auditd_sin_clave_protegido"], "apache": ["apache_completo"]}
CAMPOS_LAT = ["lab.filebeat_read", "lab.logstash_received", "lab.es_ingested"]


def ahora():
    return datetime.now(timezone.utc)


def iso(dt):
    return V.iso(dt)


# ------------------------------------------------------------------ latencias de ingesta de los eventos
def latencias(fuentes):
    """fuentes: _source crudos. Devuelve estadísticas en segundos de cada tramo y el último indexado."""
    tramos = {"lectura": [], "envio": [], "indexacion": [], "total": []}
    ultimo_idx = None
    for s in fuentes:
        t = V.desde_iso(s["@timestamp"])
        fb, ls, es = (V.desde_iso(obtener(s, c) or "") for c in CAMPOS_LAT)
        if not (fb and ls and es):
            continue
        tramos["lectura"].append((fb - t).total_seconds())
        tramos["envio"].append((ls - fb).total_seconds())
        tramos["indexacion"].append((es - ls).total_seconds())
        tramos["total"].append((es - t).total_seconds())
        ultimo_idx = es if ultimo_idx is None or es > ultimo_idx else ultimo_idx
    out = {}
    for k, v in tramos.items():
        out[f"lat_{k}_med"] = round(statistics.median(v), 3) if v else ""
        out[f"lat_{k}_max"] = round(max(v), 3) if v else ""
    out["ultimo_indexado"] = iso(ultimo_idx) if ultimo_idx else ""
    return out


# ------------------------------------------------------------------ CPU y memoria
class Recursos(threading.Thread):
    """Cada INTERVALO s: CPU (% de un núcleo) y RSS de auditd, filebeat, apache2 y el detector (por /proc), y de los
    contenedores del stack (docker stats). También CPU total de la VM y memoria disponible."""
    INTERVALO = 10
    PROCESOS = ["auditd", "filebeat", "apache2"]

    def __init__(self, ruta):
        super().__init__(daemon=True)
        self.ruta, self.fin = ruta, threading.Event()
        self.hz = os.sysconf("SC_CLK_TCK")

    @staticmethod
    def pids(nombre):
        r = subprocess.run(["pgrep", "-x", nombre], capture_output=True, text=True)
        return [int(p) for p in r.stdout.split()]

    def ticks_rss(self, pids):
        t = rss = 0
        for p in pids:
            try:
                with open(f"/proc/{p}/stat") as f:
                    campos = f.read().rsplit(")", 1)[1].split()
                t += int(campos[11]) + int(campos[12])          # utime + stime
                with open(f"/proc/{p}/status") as f:
                    for ln in f:
                        if ln.startswith("VmRSS:"):
                            rss += int(ln.split()[1])
            except OSError:
                pass
        return t, rss / 1024                                      # MiB

    @staticmethod
    def cpu_total():
        with open("/proc/stat") as f:
            v = [int(x) for x in f.readline().split()[1:]]
        return sum(v), v[3] + v[4]                                # total, idle + iowait

    @staticmethod
    def mem_disponible():
        with open("/proc/meminfo") as f:
            for ln in f:
                if ln.startswith("MemAvailable:"):
                    return int(ln.split()[1]) / 1024
        return 0

    @staticmethod
    def docker():
        try:
            r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}};{{.CPUPerc}};{{.MemUsage}}"],
                               capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return {}
        out = {}
        for ln in r.stdout.splitlines():           # p. ej. "es01;12.34%;2.1GiB / 3GiB"
            try:
                nombre, cpu, mem = ln.split(";")
                usado = mem.split("/")[0].strip()
                num = float(usado.rstrip("kKMGiB"))
                factor = {"G": 1024, "M": 1, "K": 1 / 1024, "k": 1 / 1024}.get(usado.rstrip("iB")[-1], 1 / 1024 ** 2)
                out[nombre] = (float(cpu.rstrip("%")), round(num * factor, 1))
            except (ValueError, IndexError):
                continue
        return out

    def run(self):
        grupos = {n: self.pids(n) for n in self.PROCESOS}
        grupos["detector"] = [os.getpid()]
        prev = {n: self.ticks_rss(p)[0] for n, p in grupos.items()}
        prev_tot = self.cpu_total()
        t_prev = time.monotonic()
        with open(self.ruta, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["hora", "componente", "cpu_pct", "mem_mib"])
            while not self.fin.wait(self.INTERVALO):
                dt = time.monotonic() - t_prev
                t_prev = time.monotonic()
                h = iso(ahora())
                for n, p in grupos.items():
                    t, rss = self.ticks_rss(p)
                    w.writerow([h, n, round(100 * (t - prev[n]) / self.hz / dt, 2), round(rss, 1)])
                    prev[n] = t
                tot = self.cpu_total()
                d_tot, d_idle = tot[0] - prev_tot[0], tot[1] - prev_tot[1]
                prev_tot = tot
                w.writerow([h, "vm_total", round(100 * (1 - d_idle / d_tot), 2) if d_tot else "", ""])
                w.writerow([h, "vm_mem_disponible", "", round(self.mem_disponible(), 1)])
                for nombre, (cpu, mem) in self.docker().items():
                    w.writerow([h, f"docker:{nombre}", cpu, mem])
                f.flush()


# ------------------------------------------------------------------ detección
def cargar_modelos(dir_modelos):
    return {fuente: {n: joblib.load(os.path.join(dir_modelos, n + ".joblib")) for n in nombres}
            for fuente, nombres in MODELOS.items()}


def aplicar_reglas(umbrales, fuente, f):
    out = {}
    for cod, r in umbrales["reglas"].items():
        if r["fuente"] != fuente:
            continue
        u = r["umbral"]
        ok = u is not None and float(f[r["campo"]]) >= u
        if ok and r.get("condicion"):
            c, minimo = r["condicion"]
            ok = float(f[c]) >= minimo
        out[f"regla_{cod}"] = ok
    return out


def procesar(es, a, b, modelos, umbrales):
    """Arma la ventana [a, b), calcula características y decisiones. Devuelve filas (una por fuente) y alertas."""
    t_consulta = ahora()
    crudo_aud = es.todos("lab-auditd-*", V.q_rango(a, b, {"terms": {"event.action": ["syscall", "path"]}}),
                         V.CAMPOS_AUDITD + CAMPOS_LAT)
    crudo_web = es.todos("lab-apache-*", V.q_rango(a, b, {"term": {"event.dataset": "apache.access"}}),
                         V.CAMPOS_APACHE + CAMPOS_LAT)
    aud = [V.doc_auditd(d) for d in crudo_aud]
    caract = {
        "auditd": V.caract_auditd([d for d in aud if d["tipo"] == "syscall"], [d for d in aud if d["tipo"] == "path"]),
        "apache": V.caract_apache([V.doc_apache(d) for d in crudo_web]),
    }
    lat = {"auditd": latencias([d for d in crudo_aud if obtener(d, "event.action") == "syscall"]),
           "apache": latencias(crudo_web)}
    filas, alertas = [], []
    decisiones = {}
    for fuente, f in caract.items():
        dec = {}
        for nombre, m in modelos[fuente].items():
            x = np.array([[float(f[c]) for c in m["caracteristicas"]]])
            s = float(-m["modelo"].score_samples(transformar(x, m["transformacion"]))[0])
            dec[f"IF_{nombre}"] = (s >= m["umbral"], round(s, 5), float(m["umbral"]),
                                   explicar(transformar(x, m["transformacion"])[0], m["mediana"], m["escala"],
                                            m["caracteristicas"], crudo=x[0]))
        for k, v in aplicar_reglas(umbrales, fuente, f).items():
            u = umbrales["reglas"][k.removeprefix("regla_")]["umbral"]
            # float: si el primer documento del índice trae un entero, el mapeo dinámico lo fija como long
            dec[k] = (v, None, float(u) if u is not None else None, "")
        decisiones[fuente] = dec
    t_alerta = ahora()                                    # decisión tomada: momento de emisión
    for fuente, f in caract.items():
        fila = {"fuente": fuente, "ventana_inicio": iso(a), "ventana_fin": iso(b), "t_consulta": iso(t_consulta),
                "t_alerta": iso(t_alerta), "espera_s": round((t_consulta - b).total_seconds(), 3),
                "procesamiento_s": round((t_alerta - t_consulta).total_seconds(), 3), **lat[fuente], **f}
        for det, (al, s, u, expl) in decisiones[fuente].items():
            fila[det] = int(al)
            if s is not None:
                fila[det + "_puntaje"] = s
            if al:
                alertas.append({"@timestamp": iso(t_alerta), "event": {"kind": "alert", "module": "lab_detector"},
                                "lab": {"fuente": fuente, "detector": det, "ventana_inicio": iso(a),
                                        "ventana_fin": iso(b), "t_consulta": iso(t_consulta), "t_alerta": iso(t_alerta),
                                        "puntaje": s, "umbral": u, "explicacion": expl,
                                        "espera_s": fila["espera_s"], "procesamiento_s": fila["procesamiento_s"],
                                        "eventos": f.get("aud_eventos", f.get("web_peticiones"))}})
        filas.append(fila)
    return filas, alertas


def chrony():
    try:
        r = subprocess.run(["chronyc", "tracking"], capture_output=True, text=True, timeout=10).stdout
        return [ln.strip() for ln in r.splitlines() if ln.startswith(("System time", "Leap status", "Reference ID"))]
    except (OSError, subprocess.TimeoutExpired):
        return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutos", type=float, default=20, help="duración de la prueba")
    ap.add_argument("--espera", type=float, default=30, help="segundos que se espera tras el fin de cada ventana")
    ap.add_argument("--modelos", default="results/t5/modelos")
    ap.add_argument("--umbrales", default="results/t6/umbrales.json")
    ap.add_argument("--salida", default="results/t7")
    ap.add_argument("--sin-indice", action="store_true", help="no escribir las alertas en lab-alertas-*")
    args = ap.parse_args()

    modelos = cargar_modelos(args.modelos)
    with open(args.umbrales, encoding="utf-8") as f:
        umbrales = json.load(f)
    env = leer_env(".env")
    es = ES_Cliente("lab_analyst", env["ANALYST_PASSWORD"])

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_out = os.path.join(args.salida, f"vivo_{sello}")
    os.makedirs(dir_out, exist_ok=True)
    inicio = ahora()
    fin = inicio + timedelta(minutes=args.minutos)
    with open(os.path.join(dir_out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"inicio": iso(inicio), "minutos": args.minutos, "espera_s": args.espera, "ventana_s": VENTANA,
                   "modelos": {k: {n: {"umbral": m["umbral"], "transformacion": m["transformacion"]}
                                   for n, m in v.items()} for k, v in modelos.items()},
                   "umbrales_reglas": {k: r["umbral"] for k, r in umbrales["reglas"].items()},
                   "reloj": chrony()}, f, indent=2, ensure_ascii=False)
    rec = Recursos(os.path.join(dir_out, "recursos.csv"))
    rec.start()

    # primera ventana completa: el próximo múltiplo de 30 s
    a = datetime.fromtimestamp((int(time.time()) // VENTANA + 1) * VENTANA, timezone.utc)
    print(f"[{datetime.now():%H:%M:%S}] Detector en marcha hasta {fin.astimezone():%H:%M:%S}; ventanas de {VENTANA} s, "
          f"espera {args.espera:g} s. Primera ventana: {a.astimezone():%H:%M:%S}. Salida: {dir_out}", flush=True)
    ruta_v = os.path.join(dir_out, "ventanas.csv")
    escritor, fh_v = None, open(ruta_v, "w", newline="", encoding="utf-8")
    fh_a = open(os.path.join(dir_out, "alertas.jsonl"), "w", encoding="utf-8")
    try:
        while True:
            b = a + timedelta(seconds=VENTANA)
            if b > fin:
                break
            time.sleep(max(0.0, (b + timedelta(seconds=args.espera) - ahora()).total_seconds()))
            filas, alertas = procesar(es, a, b, modelos, umbrales)
            for fila in filas:
                if escritor is None:
                    campos = list(filas[0]) + [c for c in filas[1] if c not in filas[0]]
                    escritor = csv.DictWriter(fh_v, fieldnames=campos)
                    escritor.writeheader()
                escritor.writerow(fila)
            fh_v.flush()
            for al in alertas:
                fh_a.write(json.dumps(al, ensure_ascii=False) + "\n")
                if not args.sin_indice:
                    try:
                        es.req("POST", f"/lab-alertas-{b:%Y.%m.%d}/_doc", al)
                    except Exception as e:              # la alerta queda igual en alertas.jsonl
                        print(f"   (no se pudo indexar la alerta: {e})", flush=True)
            fh_a.flush()
            resumen = "  ".join(f"{f['fuente']}: {f.get('aud_eventos', f.get('web_peticiones'))} ev" for f in filas)
            dets = sorted({al["lab"]["detector"] for al in alertas})
            print(f"[{datetime.now():%H:%M:%S}] ventana {a.astimezone():%H:%M:%S}-{b.astimezone():%H:%M:%S}  {resumen}  "
                  f"proc {filas[0]['procesamiento_s']:.2f} s  " + (f"ALERTA: {', '.join(dets)}" if dets else "sin alertas"),
                  flush=True)
            a = b
    except KeyboardInterrupt:
        print("Interrumpido.")
    finally:
        rec.fin.set()
        rec.join(timeout=30)
        fh_v.close()
        fh_a.close()
    print(f"Listo. Resultados en {dir_out}. Siguiente: src/deteccion/cronologia.py --vivo {dir_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
