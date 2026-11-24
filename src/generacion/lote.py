#!/usr/bin/env python3
"""Orquestador de sesiones etiquetadas (T3). Corre en la VM, como root:

    sudo python3 src/generacion/lote.py --salida data/piloto --sesiones 1     # piloto: 1 por escenario
    sudo python3 src/generacion/lote.py --salida data/lote   --sesiones 10    # lote completo: 40 sesiones

Escenarios (consigna E3):
  B1  auditd  actividad Linux legítima del usuario de prueba (con ráfagas y algunos errores normales)
  B2  apache  actividad HTTP legítima con 404 normales (1 a 3 clientes, con ráfagas)
  I1  auditd  actividad legítima + intentos de acceso sin permiso al archivo protegido (regla lab_protegido)
  I2  apache  actividad legítima + exploración anómala de rutas desde otro cliente

Reproducible y reanudable:
  - La primera vez crea <salida>/plan.json con el orden (aleatorio, con semilla), los parámetros de cada
    sesión y el conjunto asignado (entrenamiento/validación/prueba). Las corridas siguientes reutilizan ese plan.
  - <salida>/manifiesto.csv tiene una fila por sesión. Al volver a correr el mismo comando se saltean las
    sesiones con estado "ok" y se repiten solo las que fallaron o no se hicieron.
  - Cada sesión se verifica contra los LOGS ORIGINALES (audit.log y access.log): si un incidente no dejó
    evidencia, o una sesión benigna quedó contaminada, la sesión queda como "fallo".
"""
import argparse
import csv
import json
import os
import random
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

GEN = "/opt/lab/gen"                       # copia de src/generacion legible por labuser y por los contenedores
IMAGEN = "python:3.12-alpine"
RED = "labnet"                             # red Docker 172.30.0.0/24; el anfitrión es 172.30.0.1
OBJETIVO = "http://172.30.0.1"
AUDIT_LOG = "/var/log/audit/audit.log"
ACCESS_LOG = "/var/log/apache2/access.log"
TOL_RELOJ_AUDIT = 0.05   # s; ver evidencia_auditd
DURACION = 180                             # segundos por sesión
PAUSA = 20                                 # segundos de separación entre sesiones

ESCENARIOS = {
    "B1": {"fuente": "auditd", "tipo": "benigno"},
    "B2": {"fuente": "apache", "tipo": "benigno"},
    "I1": {"fuente": "auditd", "tipo": "incidente"},
    "I2": {"fuente": "apache", "tipo": "incidente"},
}

COLUMNAS = ["sesion", "orden", "escenario", "fuente", "tipo", "conjunto", "semilla", "estado",
            "inicio_sesion", "fin_sesion", "inicio_incidente", "fin_incidente",
            "parametros", "ips_clientes", "ip_atacante",
            "evid_sesion", "evid_incidente", "evid_detalle",
            "audit_lost_antes", "audit_lost_despues", "nota"]


# ================================================================ utilidades
def utc_ahora():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z") if dt else ""


def desde_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def audit_lost():
    try:
        out = subprocess.run(["auditctl", "-s"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"^lost (\d+)", out, re.M)
        return int(m.group(1)) if m else ""
    except OSError:
        return ""


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ================================================================ plan
def asignar_conjuntos(n, tipo, rng):
    """Benignas: 60 % entrenamiento, 20 % validación, 20 % prueba. Incidentes: mitad validación, mitad prueba
    (el modelo se entrena solo con actividad legítima)."""
    if tipo == "benigno":
        n_val = n_pru = max(1, round(n * 0.2)) if n >= 3 else 0
        conj = ["validacion"] * n_val + ["prueba"] * n_pru
        conj += ["entrenamiento"] * (n - len(conj))
    else:
        conj = ["validacion"] * (n - n // 2) + ["prueba"] * (n // 2)
    rng.shuffle(conj)
    return conj


def parametros(esc, rng):
    if esc == "B1":
        return {"tasa": round(rng.uniform(0.3, 1.0), 2), "rafagas": rng.randint(0, 3), "errores": rng.randint(0, 3)}
    if esc == "I1":
        return {"tasa": round(rng.uniform(0.3, 1.0), 2), "rafagas": rng.randint(0, 2), "errores": rng.randint(0, 2),
                "inc_inicio": round(rng.uniform(45, 105), 1), "inc_duracion": round(rng.uniform(30, 60), 1),
                "inc_tasa": round(rng.uniform(0.3, 3.0), 2)}
    if esc == "B2":
        return {"clientes": rng.randint(1, 3), "tasa": round(rng.uniform(0.15, 0.6), 2),
                "rafagas": rng.randint(0, 3), "p404": round(rng.uniform(0.02, 0.10), 3)}
    if esc == "I2":
        return {"clientes": rng.randint(1, 3), "tasa": round(rng.uniform(0.15, 0.6), 2),
                "rafagas": rng.randint(0, 2), "p404": round(rng.uniform(0.02, 0.10), 3),
                "inc_inicio": round(rng.uniform(45, 105), 1), "inc_duracion": round(rng.uniform(30, 60), 1),
                "inc_tasa": round(rng.uniform(1.0, 8.0), 2)}
    raise ValueError(esc)


def crear_plan(n, semilla):
    rng = random.Random(semilla)
    sesiones = []
    for esc, info in ESCENARIOS.items():
        for conj in asignar_conjuntos(n, info["tipo"], rng):
            sesiones.append({"escenario": esc, "fuente": info["fuente"], "tipo": info["tipo"], "conjunto": conj,
                             "semilla": rng.randint(1, 10**9), "parametros": parametros(esc, rng)})
    rng.shuffle(sesiones)                    # orden aleatorio: evita confundir deriva temporal con escenario
    ips = list(range(10, 251))
    for i, s in enumerate(sesiones, 1):
        s["sesion"] = f"S{i:02d}"
        s["orden"] = i
        if s["fuente"] == "apache":          # IPs distintas al azar: la IP no identifica el escenario
            elegidas = rng.sample(ips, s["parametros"]["clientes"] + (1 if s["tipo"] == "incidente" else 0))
            s["ips_clientes"] = [f"172.30.0.{x}" for x in elegidas[:s["parametros"]["clientes"]]]
            s["ip_atacante"] = f"172.30.0.{elegidas[-1]}" if s["tipo"] == "incidente" else ""
        else:
            s["ips_clientes"], s["ip_atacante"] = [], ""
    return {"creado": iso(utc_ahora()), "semilla": semilla, "sesiones_por_escenario": n,
            "duracion_s": DURACION, "pausa_s": PAUSA, "sesiones": sesiones}


# ================================================================ manifiesto
def leer_manifiesto(ruta):
    if not os.path.exists(ruta):
        return {}
    with open(ruta, newline="", encoding="utf-8") as f:
        return {r["sesion"]: r for r in csv.DictReader(f)}


def escribir_manifiesto(ruta, filas):
    tmp = ruta + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        for k in sorted(filas, key=lambda s: int(filas[s]["orden"])):
            w.writerow({c: filas[k].get(c, "") for c in COLUMNAS})
    os.replace(tmp, ruta)


# ================================================================ evidencia en los logs originales
RE_AUDIT = re.compile(r'type=SYSCALL msg=audit\((\d+\.\d+):(\d+)\):.*?\buid=(\d+)\b.*?\bkey=(\S+)')
RE_ACCESS = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(?:\S+) (\S+)[^"]*" (\d{3}) ')


def lineas(path):
    """Líneas del log activo y del rotado más reciente (por si rotó durante la sesión)."""
    for p in (path + ".1", path):
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                yield from f


def evidencia_auditd(t0, t1, uid_lab):
    """Registros SYSCALL de labuser en [t0, t1] por clave de regla, con el rango de números de serie."""
    claves, series = {}, []
    # auditd fecha con un reloj de grano grueso del núcleo, que puede ir unos ms atrasado respecto del de Python:
    # en el lote, el primer intento del incidente figuró 1 ms ANTES del inicio informado por el generador.
    a, b = t0.timestamp() - TOL_RELOJ_AUDIT, t1.timestamp() + TOL_RELOJ_AUDIT
    for ln in lineas(AUDIT_LOG):
        m = RE_AUDIT.search(ln)
        if not m or int(m.group(3)) != uid_lab:
            continue
        ts = float(m.group(1))
        if a <= ts <= b:
            k = m.group(4).strip('"')
            claves[k] = claves.get(k, 0) + 1
            series.append(int(m.group(2)))
    return {"por_clave": claves, "serie_min": min(series) if series else None,
            "serie_max": max(series) if series else None}


def evidencia_apache(t0, t1):
    """Líneas de access.log en [t0 - 1 s, t1 + 1 s] (Apache registra al segundo), por IP y por código."""
    por_ip, por_codigo = {}, {}
    a, b = t0 - timedelta(seconds=1), t1 + timedelta(seconds=1)
    for ln in lineas(ACCESS_LOG):
        m = RE_ACCESS.match(ln)
        if not m:
            continue
        ts = datetime.strptime(m.group(2), "%d/%b/%Y:%H:%M:%S %z")
        if a <= ts <= b:
            ip, cod = m.group(1), m.group(4)
            por_ip[ip] = por_ip.get(ip, 0) + 1
            por_codigo[cod] = por_codigo.get(cod, 0) + 1
    return {"por_ip": por_ip, "por_codigo": por_codigo}


# ================================================================ ejecución de una sesión
def lanzar_linux(modo, duracion, semilla, extra):
    cmd = ["sudo", "-u", "labuser", "python3", f"{GEN}/linux_actividad.py", "--modo", modo,
           "--duracion", str(duracion), "--semilla", str(semilla)] + extra
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def lanzar_http(ip, nombre, modo, duracion, semilla, extra):
    cmd = ["docker", "run", "--rm", "--name", nombre, "--network", RED, "--ip", ip,
           "-v", f"{GEN}:/gen:ro", IMAGEN, "python", "/gen/http_cliente.py", "--modo", modo,
           "--duracion", str(duracion), "--semilla", str(semilla), "--objetivo", OBJETIVO] + extra
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def resultado(proc, timeout):
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        err = (err or "") + " [cortado por tiempo]"
    try:
        res = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        res = {}
    return proc.returncode, res, err.strip()[-300:]


def correr_sesion(s, uid_lab):
    p = s["parametros"]
    sem = s["semilla"]
    fila = {k: s[k] for k in ("sesion", "orden", "escenario", "fuente", "tipo", "conjunto", "semilla")}
    fila.update(parametros=json.dumps(p), ips_clientes=json.dumps(s["ips_clientes"]), ip_atacante=s["ip_atacante"],
                audit_lost_antes=audit_lost())
    procs, notas = [], []
    inc = None
    t_ini = utc_ahora()

    # --- actividad legítima de fondo (toda la sesión)
    if s["fuente"] == "auditd":
        procs.append(("fondo", lanzar_linux("benigno", DURACION, sem, [
            "--tasa", str(p["tasa"]), "--rafagas", str(p["rafagas"]), "--errores", str(p["errores"])])))
    else:
        for j, ip in enumerate(s["ips_clientes"]):
            procs.append((f"cliente{j}", lanzar_http(ip, f"lab-{s['sesion']}-c{j}", "benigno", DURACION, sem + j, [
                "--tasa", str(p["tasa"]), "--rafagas", str(p["rafagas"]), "--p404", str(p["p404"])])))

    # --- incidente (ventana dentro de la sesión)
    if s["tipo"] == "incidente":
        espera = p["inc_inicio"] - (utc_ahora() - t_ini).total_seconds()
        time.sleep(max(0.0, espera))
        if s["fuente"] == "auditd":
            inc = lanzar_linux("intrusion", p["inc_duracion"], sem + 1000, ["--tasa", str(p["inc_tasa"])])
        else:
            inc = lanzar_http(s["ip_atacante"], f"lab-{s['sesion']}-atk", "exploracion", p["inc_duracion"],
                              sem + 1000, ["--tasa", str(p["inc_tasa"])])

    # --- esperar a que termine todo
    resumenes = {}
    inc_res = {}
    if inc:
        rc, inc_res, err = resultado(inc, timeout=p["inc_duracion"] + 120)
        if rc != 0:
            notas.append(f"incidente rc={rc} {err}")
    for nombre, pr in procs:
        rc, res, err = resultado(pr, timeout=DURACION + 120)
        resumenes[nombre] = res
        if rc != 0:
            notas.append(f"{nombre} rc={rc} {err}")
    t_fin = utc_ahora()

    fila.update(inicio_sesion=iso(t_ini), fin_sesion=iso(t_fin), audit_lost_despues=audit_lost())
    if inc_res:
        fila.update(inicio_incidente=inc_res.get("inicio_real", ""), fin_incidente=inc_res.get("fin_real", ""))

    # --- verificación contra los logs originales
    ok = True
    if s["tipo"] == "incidente" and not (fila.get("inicio_incidente") and fila.get("fin_incidente")):
        notas.append("el generador del incidente no informó su inicio y fin")
        fila["evid_detalle"] = json.dumps({"generadores": resumenes, "incidente": inc_res})
        fila["estado"], fila["nota"] = "fallo", " | ".join(notas)
        return fila
    if s["fuente"] == "auditd":
        ev = evidencia_auditd(t_ini, t_fin, uid_lab)
        fila["evid_sesion"] = sum(ev["por_clave"].values())
        if s["tipo"] == "incidente":
            ev_inc = evidencia_auditd(desde_iso(fila["inicio_incidente"]), desde_iso(fila["fin_incidente"]), uid_lab)
            fila["evid_incidente"] = ev_inc["por_clave"].get("lab_protegido", 0)
            if fila["evid_incidente"] == 0:
                ok = False; notas.append("el incidente no dejó registros lab_protegido en audit.log")
        elif ev["por_clave"].get("lab_protegido", 0) > 0:
            ok = False; notas.append("sesión benigna contaminada: hay registros lab_protegido")
        if ev["por_clave"].get("lab_exec", 0) == 0:
            ok = False; notas.append("sin actividad de fondo (lab_exec = 0)")
    else:
        ev = evidencia_apache(t_ini, t_fin)
        fila["evid_sesion"] = sum(ev["por_ip"].values())
        if s["tipo"] == "incidente":
            ev_inc = evidencia_apache(desde_iso(fila["inicio_incidente"]), desde_iso(fila["fin_incidente"]))
            fila["evid_incidente"] = ev_inc["por_ip"].get(s["ip_atacante"], 0)
            if fila["evid_incidente"] == 0:
                ok = False; notas.append("la exploración no dejó líneas del atacante en access.log")
        if not any(ev["por_ip"].get(ip, 0) for ip in s["ips_clientes"]):
            ok = False; notas.append("sin actividad de fondo de los clientes en access.log")
    fila["evid_detalle"] = json.dumps({"sesion": ev, "generadores": resumenes, "incidente": inc_res})
    if notas:
        ok = False
    fila["estado"] = "ok" if ok else "fallo"
    fila["nota"] = " | ".join(notas)
    return fila


# ================================================================ principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", required=True, help="directorio del plan y el manifiesto (p. ej. data/lote)")
    ap.add_argument("--sesiones", type=int, default=10, help="sesiones por escenario (solo al crear el plan)")
    ap.add_argument("--semilla", type=int, default=20261120, help="semilla del plan (solo al crear el plan)")
    ap.add_argument("--solo", help="ejecutar solo estas sesiones, separadas por comas (p. ej. S03,S17)")
    ap.add_argument("--alinear", type=int, default=0, metavar="S",
                    help="empezar cada sesión en un múltiplo exacto de S segundos del reloj (prueba en vivo, T7: así "
                         "las ventanas del detector, alineadas al reloj, coinciden con las de la sesión)")
    args = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit("Ejecutar con sudo (necesita sudo -u labuser, docker y leer los logs).")
    os.makedirs(args.salida, exist_ok=True)
    ruta_plan = os.path.join(args.salida, "plan.json")
    ruta_man = os.path.join(args.salida, "manifiesto.csv")

    if os.path.exists(ruta_plan):
        with open(ruta_plan, encoding="utf-8") as f:
            plan = json.load(f)
        log(f"Plan existente: {ruta_plan} ({len(plan['sesiones'])} sesiones)")
    else:
        plan = crear_plan(args.sesiones, args.semilla)
        with open(ruta_plan, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
        log(f"Plan nuevo: {ruta_plan} ({len(plan['sesiones'])} sesiones, semilla {args.semilla})")

    uid_lab = int(subprocess.run(["id", "-u", "labuser"], capture_output=True, text=True).stdout.strip())
    filas = leer_manifiesto(ruta_man)
    pendientes = [s for s in plan["sesiones"] if filas.get(s["sesion"], {}).get("estado") != "ok"]
    if args.solo:
        elegidas = set(args.solo.split(","))
        pendientes = [s for s in pendientes if s["sesion"] in elegidas]
    minutos = len(pendientes) * (DURACION + PAUSA) / 60
    log(f"Pendientes: {len(pendientes)} de {len(plan['sesiones'])} (≈ {minutos:.0f} min)")

    def cortar(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, cortar)

    try:
        for i, s in enumerate(pendientes, 1):
            if args.alinear:
                espera = args.alinear - (time.time() % args.alinear)
                time.sleep(espera if espera >= 1 else espera + args.alinear)
            log(f"({i}/{len(pendientes)}) {s['sesion']} {s['escenario']} [{s['conjunto']}] {json.dumps(s['parametros'])}")
            fila = correr_sesion(s, uid_lab)
            filas[s["sesion"]] = fila
            escribir_manifiesto(ruta_man, filas)
            log(f"   -> {fila['estado'].upper()}  evidencia sesión={fila['evid_sesion']} "
                f"incidente={fila.get('evid_incidente', '')} lost={fila['audit_lost_antes']}->{fila['audit_lost_despues']} "
                f"{fila['nota']}")
            if i < len(pendientes):
                time.sleep(PAUSA)
    except KeyboardInterrupt:
        log("Interrumpido: se detienen los generadores. Volver a correr el mismo comando para continuar.")
        subprocess.run("docker ps -q --filter name=lab-S | xargs -r docker kill", shell=True)
        subprocess.run(["pkill", "-u", "labuser", "-f", "linux_actividad.py"])
    finally:
        uid, gid = int(os.environ.get("SUDO_UID", 0)), int(os.environ.get("SUDO_GID", 0))
        for p in (args.salida, ruta_plan, ruta_man):
            if os.path.exists(p) and uid:
                os.chown(p, uid, gid)

    filas = leer_manifiesto(ruta_man)
    ok = sum(1 for r in filas.values() if r["estado"] == "ok")
    log(f"Resumen: {ok} ok / {len(plan['sesiones'])} sesiones. Manifiesto: {ruta_man}")
    for esc in ESCENARIOS:
        n = sum(1 for r in filas.values() if r["escenario"] == esc and r["estado"] == "ok")
        log(f"   {esc}: {n} ok")
    return 0 if ok == len(plan["sesiones"]) else 1


if __name__ == "__main__":
    sys.exit(main())
