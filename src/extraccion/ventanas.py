#!/usr/bin/env python3
"""Ventanas de observación y características (T4).

Consulta Elasticsearch (usuario de solo lectura lab_analyst) y arma, para cada sesión "ok" del manifiesto de la T3,
ventanas de 30 s con características numéricas. Genera un dataset POR FUENTE (no se mezclan auditd y Apache):

    data/procesado/ventanas_auditd.csv      sesiones B1 e I1
    data/procesado/ventanas_apache.csv      sesiones B2 e I2
    data/procesado/diccionario_caracteristicas.md
    results/t4/validacion_<fecha>.txt       contraste de cada ventana con consultas directas (_count) a Elasticsearch

Uso (en la VM, desde la raíz del repo; no necesita sudo):
    python3 src/extraccion/ventanas.py --manifiesto data/lote/manifiesto.csv

Decisiones (detalle en el diccionario y en la bitácora):
  - Ventanas de 30 s alineadas al INICIO DE CADA SESIÓN: [inicio + 30k, inicio + 30(k+1)), k = 0..5. Una ventana
    nunca mezcla dos sesiones (la pausa entre sesiones es de 20 s) ni dos conjuntos (entrenamiento/validación/prueba).
    Lo que llega después de los 180 s (procesos que tardan en cerrar) queda fuera.
  - auditd: se usan los registros SYSCALL (un SYSCALL = un evento del núcleo) y los PATH solo para saber qué archivo
    tocó cada evento. Se excluyen los registros de programas (sudo/PAM: USER_*, CRED_*): en el laboratorio los produce
    sobre todo el orquestador al lanzar los generadores con sudo, y marcarían el arranque del incidente por cómo se
    lanzó y no por lo que hizo.
  - Apache: solo access.log (event.dataset = apache.access). Resolución de 1 s.
  - Etiqueta de cada ventana (criterio fijado antes de entrenar):
      etiqueta = 1  si la ventana contiene al menos un evento del incidente (auditd: SYSCALL con clave
                    lab_protegido; Apache: línea de la IP atacante), aunque el solape con el incidente sea parcial;
      ambigua  = 1  si se solapa con el intervalo real del incidente pero no contiene ningún evento suyo (solape de
                    décimas de segundo en el borde). Se informa aparte y no cuenta en las métricas por ventana;
      etiqueta = 0  en el resto.
  - Las columnas de metadatos (sesión, escenario, conjunto, tiempos, etiqueta) NO son características: los modelos
    usan solo las columnas listadas en CARACT_AUDITD / CARACT_APACHE.
"""
import argparse
import bisect
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validar_ingesta import ES_Cliente, leer_env, obtener  # noqa: E402

VENTANA_S = 30
N_VENTANAS = 6                         # 180 s por sesión
UID_LAB = "1001"                       # labuser
RET_DENEGADO = {"-13", "-1"}           # EACCES, EPERM (process.exit_code del SYSCALL)
TOL_RELOJ_AUDIT = 0.05                 # s: auditd fecha con un reloj de grano grueso (unos ms de atraso posible)

# Números de llamada al sistema en x86_64 (ausyscall --dump)
SYSC_APERTURA = {"2", "85", "76", "77", "257", "437"}             # open, creat, truncate, ftruncate, openat, openat2
SYSC_PERMISOS = {"90", "91", "92", "93", "94", "260", "268", "452"}  # chmod, fchmod, chown, fchown, lchown,
                                                                    # fchownat, fchmodat, fchmodat2

# ------------------------------------------------------------------ diccionario de características
CARACT_AUDITD = [
    ("aud_eventos", "Eventos del núcleo (registros SYSCALL) en la ventana", "volumen"),
    ("aud_exec", "Ejecuciones de programas del usuario de prueba (clave lab_exec)", "regla"),
    ("aud_clave_denegado", "Aperturas denegadas del usuario de prueba fuera del archivo vigilado (clave lab_acceso_denegado)", "regla"),
    ("aud_clave_protegido", "Accesos al archivo vigilado (clave lab_protegido). Específica del escenario: se puede "
                            "excluir en un análisis de ablación", "regla"),
    ("aud_sin_clave", "Eventos sin clave de nuestras reglas (actividad del sistema, p. ej. cron)", "regla"),
    ("aud_fallidos", "Eventos con resultado fallido de cualquier tipo (success = no). Incluye los execve que fallan con "
                     "ENOENT al buscar un programa en cada carpeta del PATH", "resultado"),
    ("aud_denegados", "Denegaciones de permiso (EACCES o EPERM) sobre archivos reales, sin contar /proc", "resultado"),
    ("aud_denegados_proc", "Denegaciones de permiso sobre /proc (p. ej. ps intentando leer /proc/<pid>/environ de "
                           "procesos de otros usuarios): ruido benigno de las herramientas de listado de procesos", "resultado"),
    ("aud_frac_denegados", "Proporción de denegaciones (aud_denegados / aud_eventos; 0 si no hay eventos)", "resultado"),
    ("aud_op_apertura", "Llamadas de apertura o truncado (open, openat, creat, truncate…)", "operación"),
    ("aud_op_permisos", "Llamadas de cambio de permisos o dueño (chmod, fchmodat, chown…)", "operación"),
    ("aud_procesos_distintos", "Ejecutables distintos (process.executable)", "diversidad"),
    ("aud_pids_distintos", "Procesos distintos (process.pid)", "diversidad"),
    ("aud_archivos_distintos", "Archivos distintos en los registros PATH de la ventana", "diversidad"),
    ("aud_archivos_denegados_distintos", "Archivos distintos involucrados en denegaciones de permiso (sin /proc)", "diversidad"),
    ("aud_max_por_segundo", "Máximo de eventos en un mismo segundo (ráfagas)", "ritmo"),
    ("aud_segundos_activos", "Segundos de la ventana con al menos un evento (actividad sostenida vs. ráfaga)", "ritmo"),
]
CARACT_APACHE = [
    ("web_peticiones", "Peticiones HTTP en la ventana", "volumen"),
    ("web_4xx", "Respuestas 4xx", "resultado"),
    ("web_404", "Respuestas 404", "resultado"),
    ("web_5xx", "Respuestas 5xx", "resultado"),
    ("web_frac_4xx", "Proporción de respuestas 4xx (0 si no hay peticiones)", "resultado"),
    ("web_rutas_distintas", "Rutas distintas pedidas (url.original)", "diversidad"),
    ("web_rutas_4xx_distintas", "Rutas distintas que dieron 4xx", "diversidad"),
    ("web_clientes", "Clientes distintos (source.ip)", "clientes"),
    ("web_max_pet_cliente", "Peticiones del cliente más activo", "clientes"),
    ("web_max_4xx_cliente", "Respuestas 4xx del cliente con más 4xx", "clientes"),
    ("web_max_rutas_cliente", "Rutas distintas del cliente con más rutas distintas", "clientes"),
    ("web_bytes_medio", "Tamaño medio de respuesta en bytes (0 si no hay peticiones)", "volumen"),
    ("web_max_por_segundo", "Máximo de peticiones en un mismo segundo (ráfagas)", "ritmo"),
    ("web_segundos_activos", "Segundos de la ventana con al menos una petición", "ritmo"),
]
NOMBRES_AUDITD = [c[0] for c in CARACT_AUDITD]
NOMBRES_APACHE = [c[0] for c in CARACT_APACHE]
META = ["sesion", "orden", "escenario", "conjunto", "ventana", "inicio", "fin",
        "inicio_incidente", "fin_incidente", "incidente_solape_s", "incidente_eventos", "etiqueta", "ambigua"]


# ------------------------------------------------------------------ utilidades
def desde_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def solape(a0, a1, b0, b1):
    if not (b0 and b1):
        return 0.0
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds())


class Serie:
    """Documentos ordenados por tiempo, para recortar ventanas con búsqueda binaria."""

    def __init__(self, docs):
        self.docs = sorted(docs, key=lambda d: d["t"])
        self.ts = [d["t"] for d in self.docs]

    def entre(self, a, b):
        return self.docs[bisect.bisect_left(self.ts, a):bisect.bisect_left(self.ts, b)]


# ------------------------------------------------------------------ normalización de documentos
def doc_auditd(src):
    return {
        "t": desde_iso(src["@timestamp"]),
        "tipo": obtener(src, "event.action"),
        "serie": obtener(src, "auditd.log.sequence"),
        "clave": obtener(src, "auditd.log.key"),
        "exito": obtener(src, "auditd.log.success"),
        "ret": str(obtener(src, "process.exit_code")),
        "syscall": str(obtener(src, "auditd.log.syscall") or ""),
        "exe": obtener(src, "process.executable"),
        "pid": obtener(src, "process.pid"),
        "uid": str(obtener(src, "user.id") or ""),
        "archivo": obtener(src, "auditd.log.name"),
    }


def doc_apache(src):
    cod = obtener(src, "http.response.status_code")
    return {
        "t": desde_iso(src["@timestamp"]),
        "ip": obtener(src, "source.ip"),
        "ruta": obtener(src, "url.original"),
        "codigo": int(cod) if cod is not None else 0,
        "bytes": int(obtener(src, "http.response.body.bytes") or 0),
    }


# ------------------------------------------------------------------ características (se reutilizan en la T7)
def por_segundo(docs):
    c = Counter(int(d["t"].timestamp()) for d in docs)
    return (max(c.values()) if c else 0), len(c)


def caract_auditd(syscalls, paths):
    """syscalls: registros SYSCALL de la ventana; paths: registros PATH de la ventana."""
    n = len(syscalls)
    claves = Counter(d["clave"] for d in syscalls)
    fallidos = [d for d in syscalls if d["exito"] == "no"]
    # archivo de cada evento: PATH con el mismo (segundo exacto, serie); un evento puede tener varios PATH
    archivos_de = defaultdict(set)
    for p in paths:
        if p["archivo"]:
            archivos_de[(p["t"], p["serie"])].add(p["archivo"])
    # Denegación de permiso = EACCES (-13) o EPERM (-1). Las de /proc se separan: son de ps y similares.
    denegados, denegados_proc, arch_denegados = [], [], set()
    for d in syscalls:
        if d.get("ret") in RET_DENEGADO:
            arch = archivos_de.get((d["t"], d["serie"]), set())
            if arch and all(a.startswith("/proc/") for a in arch):
                denegados_proc.append(d)
            else:
                denegados.append(d)
                arch_denegados |= arch
    max_s, seg = por_segundo(syscalls)
    return {
        "aud_eventos": n,
        "aud_exec": claves.get("lab_exec", 0),
        "aud_clave_denegado": claves.get("lab_acceso_denegado", 0),
        "aud_clave_protegido": claves.get("lab_protegido", 0),
        "aud_sin_clave": sum(v for k, v in claves.items() if not k),
        "aud_fallidos": len(fallidos),
        "aud_denegados": len(denegados),
        "aud_denegados_proc": len(denegados_proc),
        "aud_frac_denegados": round(len(denegados) / n, 4) if n else 0.0,
        "aud_op_apertura": sum(1 for d in syscalls if d["syscall"] in SYSC_APERTURA),
        "aud_op_permisos": sum(1 for d in syscalls if d["syscall"] in SYSC_PERMISOS),
        "aud_procesos_distintos": len({d["exe"] for d in syscalls if d["exe"]}),
        "aud_pids_distintos": len({d["pid"] for d in syscalls if d["pid"] is not None}),
        "aud_archivos_distintos": len({p["archivo"] for p in paths if p["archivo"]}),
        "aud_archivos_denegados_distintos": len(arch_denegados),
        "aud_max_por_segundo": max_s,
        "aud_segundos_activos": seg,
    }


def caract_apache(lineas):
    n = len(lineas)
    err = [d for d in lineas if 400 <= d["codigo"] < 500]
    pet, e4, rutas = Counter(), Counter(), defaultdict(set)
    for d in lineas:
        pet[d["ip"]] += 1
        rutas[d["ip"]].add(d["ruta"])
    for d in err:
        e4[d["ip"]] += 1
    max_s, seg = por_segundo(lineas)
    return {
        "web_peticiones": n,
        "web_4xx": len(err),
        "web_404": sum(1 for d in lineas if d["codigo"] == 404),
        "web_5xx": sum(1 for d in lineas if d["codigo"] >= 500),
        "web_frac_4xx": round(len(err) / n, 4) if n else 0.0,
        "web_rutas_distintas": len({d["ruta"] for d in lineas}),
        "web_rutas_4xx_distintas": len({d["ruta"] for d in err}),
        "web_clientes": len(pet),
        "web_max_pet_cliente": max(pet.values()) if pet else 0,
        "web_max_4xx_cliente": max(e4.values()) if e4 else 0,
        "web_max_rutas_cliente": max(len(v) for v in rutas.values()) if rutas else 0,
        "web_bytes_medio": round(sum(d["bytes"] for d in lineas) / n, 1) if n else 0.0,
        "web_max_por_segundo": max_s,
        "web_segundos_activos": seg,
    }


# ------------------------------------------------------------------ ventanas de una sesión
def ventanas_sesion(s, serie_sys, serie_path, serie_web):
    t0 = desde_iso(s["inicio_sesion"])
    i0, i1 = desde_iso(s.get("inicio_incidente")), desde_iso(s.get("fin_incidente"))
    filas = []
    for k in range(N_VENTANAS):
        a, b = t0 + timedelta(seconds=VENTANA_S * k), t0 + timedelta(seconds=VENTANA_S * (k + 1))
        sol = solape(a, b, i0, i1)
        # Eventos del incidente (verdad de terreno, conocida por el diseño del escenario; no es una característica):
        # auditd: accesos al archivo protegido (ninguna sesión benigna lo toca: lo verifica la T3);
        # Apache: líneas de la IP atacante (Apache registra al segundo, así que una línea del primer instante del
        # incidente puede caer en la ventana anterior: por eso se cuentan en toda ventana, no solo donde hay solape).
        if s["fuente"] == "auditd":
            sys_v = serie_sys.entre(a, b)
            f = caract_auditd(sys_v, serie_path.entre(a, b))
            ev_inc = sum(1 for d in sys_v if d["clave"] == "lab_protegido") if s["tipo"] == "incidente" else 0
        else:
            web_v = serie_web.entre(a, b)
            f = caract_apache(web_v)
            ev_inc = sum(1 for d in web_v if d["ip"] == s["ip_atacante"]) if s["ip_atacante"] else 0
        fila = {"sesion": s["sesion"], "orden": s["orden"], "escenario": s["escenario"], "conjunto": s["conjunto"],
                "ventana": k, "inicio": iso(a), "fin": iso(b),
                "inicio_incidente": s.get("inicio_incidente", ""), "fin_incidente": s.get("fin_incidente", ""),
                "incidente_solape_s": round(sol, 3),
                "incidente_eventos": ev_inc, "etiqueta": 1 if ev_inc > 0 else 0,
                "ambigua": 1 if (sol > 0 and ev_inc == 0) else 0}
        fila.update(f)
        filas.append(fila)
    return filas


# ------------------------------------------------------------------ consultas
CAMPOS_AUDITD = ["@timestamp", "event.action", "auditd.log.sequence", "auditd.log.key", "auditd.log.success",
                 "process.exit_code", "auditd.log.syscall", "auditd.log.name", "process.executable", "process.pid", "user.id"]
CAMPOS_APACHE = ["@timestamp", "source.ip", "url.original", "http.response.status_code", "http.response.body.bytes"]


def q_rango(a, b, *filtros):
    return {"bool": {"filter": [{"range": {"@timestamp": {"gte": iso(a), "lt": iso(b)}}}, *filtros]}}


def traer(es, sesiones):
    """Trae de una vez todos los documentos del período del lote (una consulta por fuente)."""
    t_min = min(desde_iso(s["inicio_sesion"]) for s in sesiones)
    t_max = max(desde_iso(s["inicio_sesion"]) for s in sesiones) + timedelta(seconds=VENTANA_S * N_VENTANAS)
    aud = [doc_auditd(d) for d in es.todos(
        "lab-auditd-*", q_rango(t_min, t_max, {"terms": {"event.action": ["syscall", "path"]}}), CAMPOS_AUDITD)]
    web = [doc_apache(d) for d in es.todos(
        "lab-apache-*", q_rango(t_min, t_max, {"term": {"event.dataset": "apache.access"}}), CAMPOS_APACHE)]
    return (Serie([d for d in aud if d["tipo"] == "syscall"]), Serie([d for d in aud if d["tipo"] == "path"]),
            Serie(web), (t_min, t_max))


def validar(es, filas_aud, filas_web):
    """Recalcula con _count, ventana por ventana, los recuentos principales. Devuelve (líneas, diferencias)."""
    chequeos = [
        (filas_aud, "lab-auditd-*", "aud_eventos", [{"term": {"event.action": "syscall"}}]),
        (filas_aud, "lab-auditd-*", "aud_clave_protegido",
         [{"term": {"event.action": "syscall"}}, {"term": {"auditd.log.key": "lab_protegido"}}]),
        (filas_aud, "lab-auditd-*", "aud_fallidos",
         [{"term": {"event.action": "syscall"}}, {"term": {"auditd.log.success": "no"}}]),
        # denegaciones de permiso en total (las de /proc se separan después con los registros PATH)
        (filas_aud, "lab-auditd-*", "aud_denegados+aud_denegados_proc",
         [{"term": {"event.action": "syscall"}}, {"terms": {"process.exit_code": [-13, -1]}}]),
        (filas_web, "lab-apache-*", "web_peticiones", [{"term": {"event.dataset": "apache.access"}}]),
        (filas_web, "lab-apache-*", "web_4xx",
         [{"term": {"event.dataset": "apache.access"}}, {"range": {"http.response.status_code": {"gte": 400, "lt": 500}}}]),
    ]
    lineas, difs = [], []
    for filas, indice, campo, filtros in chequeos:
        iguales = 0
        for f in filas:
            n = es.req("POST", f"/{indice}/_count",
                       {"query": q_rango(desde_iso(f["inicio"]), desde_iso(f["fin"]), *filtros)})["count"]
            valor = sum(f[c] for c in campo.split("+"))
            if n == valor:
                iguales += 1
            else:
                difs.append(f"  {f['sesion']} v{f['ventana']} {campo}: dataset={valor} Elasticsearch={n}")
        lineas.append(f"  {campo:<34} {iguales}/{len(filas)} ventanas coinciden")
    return lineas, difs


# ------------------------------------------------------------------ salida
def escribir_csv(ruta, filas, caract):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=META + caract)
        w.writeheader()
        w.writerows(filas)


def escribir_diccionario(ruta):
    out = ["# Diccionario de características (T4)", "",
           "Generado por `src/extraccion/ventanas.py`. Cada fila de los datasets es una **ventana de 30 s** de una "
           "sesión; las ventanas se alinean al inicio de la sesión (6 por sesión).", "",
           "## Metadatos (no son variables predictoras)", "",
           "| Columna | Contenido |", "|---|---|",
           "| `sesion`, `orden`, `escenario`, `conjunto` | Sesión de la T3, su posición en el lote, escenario (B1, I1, B2, I2) y conjunto (entrenamiento, validacion, prueba) |",
           "| `ventana` | Índice de la ventana dentro de la sesión (0 a 5) |",
           "| `inicio`, `fin` | Límites de la ventana en UTC, intervalo [inicio, fin) |",
           "| `inicio_incidente`, `fin_incidente` | Intervalo real del incidente de la sesión (vacío en las benignas), informado por el generador |",
           "| `incidente_solape_s` | Segundos de la ventana que se solapan con el intervalo real del incidente |",
           "| `incidente_eventos` | Eventos del incidente en la ventana (auditd: SYSCALL con clave `lab_protegido`; Apache: líneas de la IP atacante) |",
           "| `etiqueta` | 1 si la ventana contiene al menos un evento del incidente, aunque el solape sea parcial; 0 en otro caso |",
           "| `ambigua` | 1 si hay solape pero ningún evento del incidente (borde del intervalo); se excluye de las métricas por ventana |",
           ""]
    for titulo, caract in (("auditd (`ventanas_auditd.csv`, sesiones B1 e I1)", CARACT_AUDITD),
                           ("Apache (`ventanas_apache.csv`, sesiones B2 e I2)", CARACT_APACHE)):
        out += [f"## {titulo}", "", "| Característica | Grupo | Descripción |", "|---|---|---|"]
        out += [f"| `{n}` | {g} | {d} |" for n, d, g in caract]
        out.append("")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def resumen(filas, nombre, campos_clave):
    out = [f"== {nombre}: {len(filas)} ventanas de {len({f['sesion'] for f in filas})} sesiones"]
    c = Counter((f["escenario"], f["conjunto"], "ambigua" if f["ambigua"] else f"etiqueta={f['etiqueta']}") for f in filas)
    for k in sorted(c):
        out.append(f"  {k[0]} {k[1]:<13} {k[2]:<10} {c[k]}")
    out.append("  Media de características por escenario y etiqueta:")
    grupos = defaultdict(list)
    for f in filas:
        grupos[(f["escenario"], f["etiqueta"])].append(f)
    out.append("    " + f"{'grupo':<10}" + "".join(f"{c[:20]:>22}" for c in campos_clave))
    for g in sorted(grupos):
        fs = grupos[g]
        out.append("    " + f"{g[0]} e={g[1]:<5}" + "".join(f"{sum(f[c] for f in fs) / len(fs):>22.2f}" for c in campos_clave))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifiesto", default="data/lote/manifiesto.csv")
    ap.add_argument("--salida", default="data/procesado")
    ap.add_argument("--resultados", default="results/t4")
    ap.add_argument("--sin-validar", action="store_true", help="no contrastar cada ventana con _count")
    args = ap.parse_args()

    with open(args.manifiesto, newline="", encoding="utf-8") as f:
        todas = list(csv.DictReader(f))
    sesiones = [s for s in todas if s["estado"] == "ok"]
    if not sesiones:
        sys.exit("El manifiesto no tiene sesiones ok.")
    env = leer_env(".env")
    es = ES_Cliente("lab_analyst", env["ANALYST_PASSWORD"])

    serie_sys, serie_path, serie_web, (t_min, t_max) = traer(es, sesiones)
    filas_aud, filas_web = [], []
    for s in sorted(sesiones, key=lambda s: int(s["orden"])):
        (filas_aud if s["fuente"] == "auditd" else filas_web).extend(
            ventanas_sesion(s, serie_sys, serie_path, serie_web))

    os.makedirs(args.salida, exist_ok=True)
    os.makedirs(args.resultados, exist_ok=True)
    escribir_csv(os.path.join(args.salida, "ventanas_auditd.csv"), filas_aud, NOMBRES_AUDITD)
    escribir_csv(os.path.join(args.salida, "ventanas_apache.csv"), filas_web, NOMBRES_APACHE)
    escribir_diccionario(os.path.join(args.salida, "diccionario_caracteristicas.md"))

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    rep = [f"T4 — ventanas y características ({sello})", f"Manifiesto: {args.manifiesto} "
           f"({len(sesiones)} sesiones ok de {len(todas)})",
           f"Período consultado: {iso(t_min)} – {iso(t_max)}",
           f"Documentos traídos: {len(serie_sys.docs)} SYSCALL, {len(serie_path.docs)} PATH, "
           f"{len(serie_web.docs)} líneas de access.log", ""]
    rep += resumen(filas_aud, "auditd", ["aud_eventos", "aud_fallidos", "aud_denegados_proc", "aud_denegados",
                                         "aud_clave_protegido", "aud_archivos_denegados_distintos"]) + [""]
    rep += resumen(filas_web, "apache", ["web_peticiones", "web_4xx", "web_rutas_4xx_distintas", "web_clientes",
                                         "web_max_4xx_cliente"]) + [""]

    # Contraste 1: eventos del incidente según Elasticsearch vs. evidencia en los logs originales (manifiesto T3)
    rep.append("== Eventos del incidente: Elasticsearch (suma de ventanas) vs. logs originales (manifiesto)")
    ok_inc = 0
    incid = [s for s in sesiones if s["tipo"] == "incidente"]
    explicadas = 0
    for s in incid:
        filas = filas_aud if s["fuente"] == "auditd" else filas_web
        n = sum(f["incidente_eventos"] for f in filas if f["sesion"] == s["sesion"])
        igual = str(n) == str(s["evid_incidente"])
        nota = "OK" if igual else "DIFIERE"
        if not igual and s["fuente"] == "auditd" and s["evid_incidente"]:
            # El manifiesto de la T3 se armó con el intervalo estricto [inicio, fin] del generador. auditd fecha con
            # un reloj de grano grueso (puede ir unos ms atrasado), y el primer intento puede figurar 1–4 ms ANTES.
            i0, i1 = desde_iso(s["inicio_incidente"]), desde_iso(s["fin_incidente"])
            tol = timedelta(seconds=TOL_RELOJ_AUDIT)
            borde = sum(1 for d in serie_sys.entre(i0 - tol, i0) + serie_sys.entre(i1 + timedelta(microseconds=1000),
                                                                                    i1 + tol)
                        if d["clave"] == "lab_protegido" and d["uid"] == UID_LAB)
            if borde and n == int(s["evid_incidente"]) + borde:
                igual, nota = True, f"OK (+{borde} a menos de {int(TOL_RELOJ_AUDIT * 1000)} ms del borde del intervalo)"
                explicadas += 1
        ok_inc += igual
        rep.append(f"  {s['sesion']} {s['escenario']} ES={n:<5} logs={s['evid_incidente']:<5} {nota}")
    rep.append(f"  {ok_inc}/{len(incid)} coinciden")
    if explicadas:
        rep.append(f"  En {explicadas} sesiones I1 el manifiesto cuenta 1 menos: el primer intento quedó fechado por "
                   f"auditd unos ms antes del inicio informado por el generador (reloj de grano grueso del núcleo). "
                   f"El registro es del incidente; vale el conteo de Elasticsearch.")
    rep.append("")

    # Contraste 2: cada ventana contra _count directo en Elasticsearch
    if not args.sin_validar:
        rep.append("== Ventanas vs. consultas _count directas a Elasticsearch")
        lineas, difs = validar(es, filas_aud, filas_web)
        rep += lineas
        rep += (["  Diferencias:"] + difs[:50]) if difs else ["  Sin diferencias."]
    ruta_rep = os.path.join(args.resultados, f"validacion_{sello}.txt")
    with open(ruta_rep, "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print("\n".join(rep))
    print(f"\nDatasets en {args.salida}/ ; reporte en {ruta_rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
