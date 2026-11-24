#!/usr/bin/env python3
"""Generador de actividad Linux del usuario de prueba `labuser` (escenarios B1 e I1, fuente auditd).

Se ejecuta COMO labuser (el orquestador lo lanza con `sudo -u labuser`), así las reglas de auditd
filtradas por uid lo registran. Solo usa la biblioteca estándar.

Modos:
  benigno    Actividad habitual: comandos (cada uno es un execve -> clave lab_exec), escritura de archivos
             propios, ráfagas de comandos seguidos y, opcionalmente, algunos errores normales de permisos
             sobre archivos del sistema (-> clave lab_acceso_denegado).
  intrusion  Intentos repetidos de leer, escribir o cambiar permisos del archivo protegido de prueba
             (-> clave lab_protegido, success=no).

Imprime al final un resumen JSON con la hora real de inicio y fin (UTC) y lo que hizo.
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

PROTEGIDO = "/srv/lab/protegido/secreto.txt"
# Archivos del sistema que un usuario normal no puede leer: errores de permisos "normales".
ERRORES_NORMALES = [["cat", "/etc/shadow"], ["ls", "/root"], ["cat", "/etc/sudoers"]]


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def correr(cmd):
    """Ejecuta un comando sin mostrar salida. Devuelve True si terminó con código 0."""
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def comandos_benignos(trabajo):
    return [
        ["ls", "-la", trabajo],
        ["cat", f"{trabajo}/notas.txt"],
        ["grep", "-ri", "informe", trabajo],
        ["find", trabajo, "-name", "*.txt"],
        ["wc", "-l", f"{trabajo}/datos.csv"],
        ["sort", f"{trabajo}/datos.csv"],
        ["head", "-n", "5", f"{trabajo}/datos.csv"],
        ["tail", "-n", "5", f"{trabajo}/diario.txt"],
        ["date"], ["id"], ["uname", "-a"], ["df", "-h"], ["uptime"],
        ["ps", "-u", "labuser"],
        ["python3", "-c", "print(sum(range(10000)))"],
        ["tar", "-czf", "/tmp/labuser_respaldo.tgz", "-C", trabajo, "."],
        ["cp", f"{trabajo}/notas.txt", "/tmp/labuser_notas.bak"],
        ["rm", "-f", "/tmp/labuser_notas.bak"],
        ["du", "-sh", trabajo],
        ["stat", f"{trabajo}/datos.csv"],
    ]


def benigno(args, rng, resumen):
    trabajo = args.trabajo
    cmds = comandos_benignos(trabajo)
    fin = time.monotonic() + args.duracion
    # Momentos (en segundos desde el inicio) de las ráfagas y de los errores normales.
    rafagas = sorted(rng.uniform(5, max(6, args.duracion - 25)) for _ in range(args.rafagas))
    errores = sorted(rng.uniform(5, max(6, args.duracion - 5)) for _ in range(args.errores))
    t0 = time.monotonic()
    while time.monotonic() < fin:
        trans = time.monotonic() - t0
        if rafagas and trans >= rafagas[0]:
            rafagas.pop(0)
            n = rng.randint(10, 25)
            for _ in range(n):
                correr(rng.choice(cmds))
                time.sleep(rng.uniform(0.05, 0.3))
            resumen["rafagas"] += 1
            resumen["comandos"] += n
            continue
        if errores and trans >= errores[0]:
            errores.pop(0)
            correr(rng.choice(ERRORES_NORMALES))
            resumen["errores_normales"] += 1
            continue
        accion = rng.random()
        if accion < 0.85:
            correr(rng.choice(cmds))
            resumen["comandos"] += 1
        else:
            # Escritura en archivos propios (sin execve).
            with open(f"{trabajo}/diario.txt", "a", encoding="utf-8") as f:
                f.write(f"{ahora()} nota de trabajo {rng.randint(1, 9999)}\n")
            resumen["escrituras"] += 1
        # Tiempo de "pensar" entre acciones: exponencial con la tasa indicada.
        time.sleep(min(rng.expovariate(args.tasa), max(0.0, fin - time.monotonic())))


def intrusion(args, rng, resumen):
    fin = time.monotonic() + args.duracion
    while time.monotonic() < fin:
        intento = rng.choice(["leer", "leer", "escribir", "chmod", "cat", "cp"])
        try:
            if intento == "leer":
                open(PROTEGIDO, "r").close()
            elif intento == "escribir":
                open(PROTEGIDO, "a").close()
            elif intento == "chmod":
                os.chmod(PROTEGIDO, 0o644)
            elif intento == "cat":
                correr(["cat", PROTEGIDO])
            elif intento == "cp":
                correr(["cp", PROTEGIDO, "/tmp/labuser_copia.txt"])
            if intento in ("leer", "escribir", "chmod"):
                resumen["accesos_exitosos"] += 1   # no debería ocurrir: el archivo es root 600
        except PermissionError:
            pass
        resumen["intentos"] += 1
        resumen["por_tipo"][intento] = resumen["por_tipo"].get(intento, 0) + 1
        time.sleep(min(rng.expovariate(args.tasa), max(0.0, fin - time.monotonic())))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modo", choices=["benigno", "intrusion"], required=True)
    p.add_argument("--duracion", type=float, required=True, help="segundos")
    p.add_argument("--semilla", type=int, required=True)
    p.add_argument("--tasa", type=float, default=0.6, help="acciones por segundo (promedio)")
    p.add_argument("--rafagas", type=int, default=0, help="cantidad de ráfagas de comandos (benigno)")
    p.add_argument("--errores", type=int, default=0, help="cantidad de errores normales de permisos (benigno)")
    p.add_argument("--trabajo", default="/home/labuser/trabajo", help="directorio de trabajo de labuser")
    args = p.parse_args()

    rng = random.Random(args.semilla)
    resumen = {"modo": args.modo, "semilla": args.semilla, "uid": os.getuid(), "inicio_real": ahora(),
               "comandos": 0, "escrituras": 0, "rafagas": 0, "errores_normales": 0,
               "intentos": 0, "accesos_exitosos": 0, "por_tipo": {}}
    try:
        (benigno if args.modo == "benigno" else intrusion)(args, rng, resumen)
    finally:
        resumen["fin_real"] = ahora()
        print(json.dumps(resumen), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
