#!/usr/bin/env python3
"""Validación de la ingesta (T2): compara los logs ORIGINALES con lo indexado en Elasticsearch.

Para cada archivo (audit.log, access.log, error.log) trae de Elasticsearch todos los documentos que
vinieron de ese archivo (campo log.file.path) y compara, línea por línea, el texto original
(event.original) con las líneas del archivo:
  - líneas del archivo que no están en Elasticsearch  -> eventos perdidos
  - documentos que no están en el archivo            -> duplicados o líneas de un archivo ya rotado
  - documentos con error.message                     -> eventos mal parseados
En auditd además desglosa por tipo de registro (type=...). Por último guarda un ejemplo de documento
de cada tipo de registro de auditd, con todos sus campos, para la tabla de campos del informe.

Uso (en la VM, desde la raíz del repo; sudo para poder leer los logs):
    sudo python3 src/extraccion/validar_ingesta.py
Salida: results/t2/recuentos_<fecha>.txt y results/t2/ejemplos_campos_<fecha>.json
Solo usa la biblioteca estándar.
"""
import argparse
import base64
import collections
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

ES = "http://127.0.0.1:9200"
FUENTES = [
    ("auditd", "lab-auditd-*", "/var/log/audit/audit.log"),
    ("apache-access", "lab-apache-*", "/var/log/apache2/access.log"),
    ("apache-error", "lab-apache-*", "/var/log/apache2/error.log"),
]
RE_TIPO = re.compile(r"\btype=(\S+)")
RE_T_AUDIT = re.compile(r"msg=audit\((\d+\.\d+):\d+\)")
RE_T_ACCESS = re.compile(r"\[(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4})\]")
OMITIR = ("agent", "ecs", "input", "@version", "_tmp")


def leer_env(ruta):
    env = {}
    with open(ruta, encoding="utf-8") as f:
        for ln in f:
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.strip().split("=", 1)
                env[k] = v
    return env


class ES_Cliente:
    def __init__(self, usuario, clave):
        self.auth = "Basic " + base64.b64encode(f"{usuario}:{clave}".encode()).decode()

    def req(self, metodo, ruta, cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        r = urllib.request.Request(ES + ruta, data=datos, method=metodo,
                                   headers={"Authorization": self.auth, "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read() or b"{}")

    def todos(self, indice, consulta, campos):
        """Todos los documentos que cumplen la consulta (scroll), solo con los campos pedidos."""
        res = self.req("POST", f"/{indice}/_search?scroll=2m",
                       {"size": 5000, "query": consulta, "_source": campos})
        docs = []
        while res["hits"]["hits"]:
            docs += [h["_source"] for h in res["hits"]["hits"]]
            res = self.req("POST", "/_search/scroll", {"scroll": "2m", "scroll_id": res["_scroll_id"]})
        try:
            self.req("DELETE", "/_search/scroll", {"scroll_id": res["_scroll_id"]})
        except Exception:
            pass
        return docs


def obtener(d, ruta):
    for p in ruta.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def aplanar(d, prefijo=""):
    out = {}
    for k, v in d.items():
        clave = f"{prefijo}{k}"
        if isinstance(v, dict):
            out.update(aplanar(v, clave + "."))
        else:
            out[clave] = v
    return out


def epoch_linea(fuente, ln):
    """Hora de generación de una línea (para excluir las más recientes, que pueden no haberse indexado)."""
    if fuente == "auditd":
        m = RE_T_AUDIT.search(ln)
        return float(m.group(1)) if m else None      # con milisegundos, como @timestamp
    if fuente == "apache-access":
        m = RE_T_ACCESS.search(ln)
        return int(datetime.strptime(m.group(1), "%d/%b/%Y:%H:%M:%S %z").timestamp()) if m else None
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--margen", type=int, default=90,
                    help="ignorar líneas generadas en los últimos N segundos (todavía en tránsito)")
    ap.add_argument("--salida", default="results/t2")
    ap.add_argument("--detalle", action="store_true",
                    help="guardar TODAS las líneas faltantes y los documentos con error en detalle_<fecha>.txt")
    args = ap.parse_args()

    env = leer_env(".env")
    es = ES_Cliente("lab_analyst", env["ANALYST_PASSWORD"])
    os.makedirs(args.salida, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    limite = time.time() - args.margen
    informe = [f"Validación de la ingesta — {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
               f"(se ignoran las líneas de los últimos {args.margen} s)", ""]
    resumen = []
    detalle = []

    for fuente, indice, archivo in FUENTES:
        informe.append(f"===== {fuente}: {archivo}  <->  {indice}")
        if not os.path.exists(archivo):
            informe += ["  (el archivo no existe)", ""]
            continue
        docs = es.todos(indice, {"term": {"log.file.path": archivo}},
                        ["event.original", "event.action", "auditd.log.record_type", "error.message", "@timestamp"])
        # Si el archivo rotó después de la ingesta (p. ej. logrotate de Apache a medianoche), las líneas ya
        # ingeridas están en archivo.1: se comparan también, desde el primer documento que tiene Elasticsearch.
        t0 = min((datetime.fromisoformat(d["@timestamp"].replace("Z", "+00:00")).timestamp()
                  for d in docs if d.get("@timestamp")), default=None)
        del_rotado = []
        if t0 is not None and os.path.exists(archivo + ".1"):
            with open(archivo + ".1", encoding="utf-8", errors="replace") as f:
                for ln in f:
                    ln = ln.rstrip("\n")
                    t = epoch_linea(fuente, ln) if ln.strip() else None
                    # Apache registra al segundo: se compara contra el segundo del primer documento
                    if t is not None and t >= (t0 if fuente == "auditd" else int(t0)):
                        del_rotado.append(ln)
        with open(archivo, encoding="utf-8", errors="replace") as f:
            crudas = del_rotado + [ln.rstrip("\n") for ln in f if ln.strip()]
        recientes = 0
        filtradas = []
        for ln in crudas:
            t = epoch_linea(fuente, ln)
            if t is not None and t > limite:
                recientes += 1
            else:
                filtradas.append(ln)
        originales = [d.get("event", {}).get("original") for d in docs]
        en_es = collections.Counter(o for o in originales if o is not None)
        en_log = collections.Counter(filtradas)
        perdidas = en_log - en_es
        sobrantes = en_es - en_log
        # Las líneas recientes (excluidas por el margen) que ya están indexadas no son sobrantes.
        recientes_set = collections.Counter(ln for ln in crudas if ln not in en_log)
        sobrantes = sobrantes - recientes_set
        # Documentos que vienen del archivo antes de rotarlo (archivo.1): no son duplicados.
        rotadas = collections.Counter()
        if os.path.exists(archivo + ".1"):
            with open(archivo + ".1", encoding="utf-8", errors="replace") as f:
                rotadas = collections.Counter(ln.rstrip("\n") for ln in f if ln.strip())
            rotadas = rotadas - collections.Counter(del_rotado)   # las ya incluidas en la comparación
        de_rotado = sobrantes & rotadas
        sobrantes = sobrantes - rotadas
        errores = sum(1 for d in docs if obtener(d, "error.message"))
        errores_sin_original = sum(1 for d in docs if obtener(d, "error.message") and obtener(d, "event.original") is None)
        sin_original = sum(1 for o in originales if o is None)
        informe += [
            f"  líneas en el archivo:            {len(crudas)}  (comparadas: {len(filtradas)}, recientes excluidas: {recientes}; "
            f"{len(del_rotado)} de {os.path.basename(archivo)}.1 posteriores al primer documento de ES)",
            f"  documentos en Elasticsearch:     {len(docs)}  (sin event.original: {sin_original})",
            f"  líneas que faltan en ES:         {sum(perdidas.values())}",
            f"  documentos de líneas ya rotadas: {sum(de_rotado.values())}  (están en {os.path.basename(archivo)}.1)",
            f"  documentos de más en ES:         {sum(sobrantes.values())}  (duplicados o sin origen en el log)",
            f"  documentos con error de parseo:  {errores}  (sin event.original: {errores_sin_original}; esas líneas "
            f"llegaron, pero figuran también como faltantes porque no se puede comparar su texto)",
        ]
        if fuente == "auditd":
            # Mismo conjunto de líneas en los dos lados: sin las recientes ni las de un archivo rotado.
            comparables_es = en_es - recientes_set - de_rotado
            t_log = collections.Counter(RE_TIPO.search(ln).group(1) for ln in filtradas if RE_TIPO.search(ln))
            t_es = collections.Counter(RE_TIPO.search(o).group(1) for o in comparables_es.elements() if RE_TIPO.search(o))
            informe.append("  por tipo de registro (log / ES):")
            for tipo in sorted(set(t_log) | set(t_es)):
                marca = "" if t_log[tipo] == t_es[tipo] else "   <-- difiere"
                informe.append(f"    {tipo:<16} {t_log[tipo]:>7} / {t_es[tipo]:<7}{marca}")
        if args.detalle:
            def hora(ln):
                t = epoch_linea(fuente, ln)
                return datetime.fromtimestamp(t, timezone.utc).isoformat() if t is not None else "?"
            detalle.append(f"===== {fuente}: {sum(perdidas.values())} líneas que faltan en ES")
            detalle += [f"  [{hora(ln)}] {ln[:600]}" for ln in sorted(perdidas.elements(), key=hora)]
            con_error = [d for d in docs if obtener(d, "error.message")]
            detalle.append(f"===== {fuente}: {len(con_error)} documentos con error de parseo")
            for d in sorted(con_error, key=lambda d: d.get("@timestamp", "")):
                detalle.append(f"  [{d.get('@timestamp')}] error: {str(obtener(d, 'error.message'))[:300]}")
                detalle.append(f"      original: {str(obtener(d, 'event.original'))[:600]}")
            detalle.append("")
        for nombre, cont in (("que faltan en ES", perdidas), ("que sobran en ES", sobrantes)):
            if cont:
                informe.append(f"  ejemplos de líneas {nombre}:")
                informe += [f"    {ln[:200]}" for ln in list(cont.elements())[:3]]
        informe.append("")
        resumen.append(f"{fuente}: {len(filtradas)} líneas / {len(docs)} docs / faltan {sum(perdidas.values())} "
                       f"/ de archivo rotado {sum(de_rotado.values())} / de más {sum(sobrantes.values())} / errores {errores}")

    # Ejemplo de documento por tipo de registro de auditd (tabla de campos)
    ejemplos = {}
    acciones = es.req("POST", "/lab-auditd-*/_search",
                      {"size": 0, "aggs": {"a": {"terms": {"field": "event.action", "size": 50}}}})
    for b in acciones["aggregations"]["a"]["buckets"]:
        r = es.req("POST", "/lab-auditd-*/_search",
                   {"size": 1, "sort": [{"@timestamp": "desc"}], "query": {"term": {"event.action": b["key"]}}})
        if r["hits"]["hits"]:
            src = {k: v for k, v in r["hits"]["hits"][0]["_source"].items() if k not in OMITIR}
            ejemplos[b["key"]] = {"documentos": b["doc_count"], "campos": aplanar(src)}
    r = es.req("POST", "/lab-apache-*/_search", {"size": 1, "sort": [{"@timestamp": "desc"}],
                                                  "query": {"term": {"event.dataset": "apache.access"}}})
    if r["hits"]["hits"]:
        ejemplos["apache.access"] = {"campos": aplanar({k: v for k, v in r["hits"]["hits"][0]["_source"].items()
                                                         if k not in OMITIR})}
    # error.log: un ejemplo por nivel de severidad (la tabla de campos del informe cubre access y error)
    niveles = es.req("POST", "/lab-apache-*/_search",
                     {"size": 0, "query": {"term": {"event.dataset": "apache.error"}},
                      "aggs": {"n": {"terms": {"field": "log.level", "size": 10}}}})
    for b in niveles.get("aggregations", {}).get("n", {}).get("buckets", []) or [{"key": None, "doc_count": 0}]:
        filtro = [{"term": {"event.dataset": "apache.error"}}]
        if b["key"] is not None:
            filtro.append({"term": {"log.level": b["key"]}})
        r = es.req("POST", "/lab-apache-*/_search", {"size": 1, "sort": [{"@timestamp": "desc"}],
                                                      "query": {"bool": {"filter": filtro}}})
        if r["hits"]["hits"]:
            ejemplos[f"apache.error.{b['key']}"] = {
                "documentos": b["doc_count"],
                "campos": aplanar({k: v for k, v in r["hits"]["hits"][0]["_source"].items() if k not in OMITIR})}

    informe += ["===== Resumen"] + [f"  {x}" for x in resumen]
    informe += ["", f"Tipos de registro de auditd con ejemplo guardado: {', '.join(sorted(ejemplos))}"]
    ruta_txt = os.path.join(args.salida, f"recuentos_{sello}.txt")
    ruta_json = os.path.join(args.salida, f"ejemplos_campos_{sello}.json")
    if args.detalle:
        ruta_det = os.path.join(args.salida, f"detalle_{sello}.txt")
        with open(ruta_det, "w", encoding="utf-8") as f:
            f.write("\n".join(detalle) + "\n")
        print(f"Detalle: {ruta_det}")
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(informe) + "\n")
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(ejemplos, f, indent=2, ensure_ascii=False)
    uid, gid = int(os.environ.get("SUDO_UID", 0)), int(os.environ.get("SUDO_GID", 0))
    if uid:
        for p in (args.salida, ruta_txt, ruta_json):
            os.chown(p, uid, gid)
    print("\n".join(informe))
    print(f"\nGuardado: {ruta_txt}\n          {ruta_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
