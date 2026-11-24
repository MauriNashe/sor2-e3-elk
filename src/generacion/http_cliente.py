#!/usr/bin/env python3
"""Cliente HTTP del laboratorio (escenarios B2 e I2, fuente Apache) y generador del sitio de prueba.

Corre dentro de un contenedor python:3.12-alpine conectado a la red Docker `labnet`, con una IP propia,
así Apache registra cada cliente por separado. Solo usa la biblioteca estándar.

Modos:
  benigno      Navegación habitual: página + recursos (CSS, JS, imágenes), tiempos de lectura, ráfagas
               de navegación rápida y 404 normales (favicon inexistente, enlaces rotos, errores de tipeo).
  exploracion  Exploración anómala de rutas: recorre una lista de rutas típicas de escáneres
               (paneles de administración, respaldos, archivos de configuración) a una tasa fija.
  --generar-sitio DIR   Escribe el sitio de prueba en DIR (lo usa scripts/t3_setup.sh). Así el sitio y el
                        cliente comparten una sola definición de páginas y recursos.

Ambos modos usan los mismos User-Agent de navegador, para que el agente no delate al atacante.
Imprime al final un resumen JSON con la hora real de inicio y fin (UTC) y los códigos obtenidos.
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------- definición del sitio
NOTICIAS = [f"/noticias/n{i:02d}.html" for i in range(1, 13)]
DOCS = [f"/docs/d{i:02d}.html" for i in range(1, 16)]
PAGINAS = ["/", "/index.html", "/nosotros.html", "/contacto.html", "/servicios.html"] + NOTICIAS + DOCS
IMAGENES = [f"/img/f{i:02d}.svg" for i in range(1, 11)]
RECURSOS_COMUNES = ["/css/estilo.css", "/js/app.js", "/img/logo.svg"]
# 404 "normales": el sitio no tiene favicon y algunas páginas tienen enlaces rotos o se tipean mal.
ROTOS = ["/favicon.ico", "/img/f11.svg", "/img/banner.png", "/docs/d16.html", "/noticias/n13.html",
         "/contacto.htm", "/nosotros", "/css/estilo.min.css", "/apple-touch-icon.png"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

# Rutas típicas de exploración automatizada. Casi todas responden 404; algunas 403 (.ht*, server-status).
RUTAS_EXPLORACION = [
    "admin", "admin/", "administrator", "admin.php", "admin/login.php", "login", "login.php", "wp-login.php",
    "wp-admin/", "wp-content/", "wp-includes/", "xmlrpc.php", "phpmyadmin/", "pma/", "mysql/", "dbadmin/",
    ".env", ".env.bak", ".git/HEAD", ".git/config", ".svn/entries", ".htaccess", ".htpasswd", ".DS_Store",
    "config.php", "config.php.bak", "configuration.php", "settings.py", "web.config", "config.json",
    "backup/", "backup.zip", "backup.tar.gz", "backup.sql", "db.sql", "dump.sql", "database.sql", "site.zip",
    "old/", "test/", "test.php", "info.php", "phpinfo.php", "server-status", "server-info", "cgi-bin/",
    "cgi-bin/test.cgi", "shell.php", "cmd.php", "upload/", "uploads/", "files/", "private/", "secret/",
    "api/", "api/v1/", "api/v1/users", "graphql", "console/", "manager/html", "jenkins/", "solr/",
    "actuator/health", "actuator/env", "debug/", "logs/", "log/", "error.log", "access.log", "tmp/",
    "install.php", "setup.php", "readme.html", "license.txt", "robots.txt", "sitemap.xml", "crossdomain.xml",
    ".well-known/security.txt", "vendor/", "node_modules/", "composer.json", "package.json", "Dockerfile",
    "docker-compose.yml", ".aws/credentials", ".ssh/id_rsa", "id_rsa", "users.txt", "passwords.txt",
]

LONG_TEXTO = ("Contenido de prueba del laboratorio de Sistemas Operativos y Redes II. "
              "No contiene datos reales. ") * 8


def recursos_de(pagina):
    """Recursos que pide un navegador al cargar la página (determinísticos por página)."""
    h = sum(ord(c) for c in pagina)
    return RECURSOS_COMUNES + [IMAGENES[h % len(IMAGENES)], IMAGENES[(h * 7 + 3) % len(IMAGENES)]]


def generar_sitio(destino):
    for sub in ("noticias", "docs", "css", "js", "img"):
        os.makedirs(os.path.join(destino, sub), exist_ok=True)
    enlaces = "".join(f'<li><a href="{p}">{p}</a></li>' for p in PAGINAS[1:])
    for pagina in PAGINAS[1:]:
        recursos = recursos_de(pagina)
        imgs = "".join(f'<img src="{r}" alt="">' for r in recursos if r.startswith("/img/"))
        html = (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{pagina}</title>'
                f'<link rel="stylesheet" href="/css/estilo.css"><script src="/js/app.js"></script></head>'
                f'<body><h1>Sitio de prueba — {pagina}</h1>{imgs}<p>{LONG_TEXTO}</p><ul>{enlaces}</ul></body></html>')
        with open(os.path.join(destino, pagina.lstrip("/")), "w", encoding="utf-8") as f:
            f.write(html)
    with open(os.path.join(destino, "css/estilo.css"), "w") as f:
        f.write("body{font-family:sans-serif;margin:2em}img{width:64px}" * 20)
    with open(os.path.join(destino, "js/app.js"), "w") as f:
        f.write("document.addEventListener('DOMContentLoaded',()=>{});\n" * 20)
    for img in IMAGENES + ["/img/logo.svg"]:
        with open(os.path.join(destino, img.lstrip("/")), "w") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
                    f'<rect width="64" height="64" fill="#{(sum(map(ord, img)) * 9973) % 0xFFFFFF:06x}"/></svg>')
    print(f"Sitio generado en {destino}: {len(PAGINAS) - 1} páginas, {len(IMAGENES) + 3} recursos")


# ---------------------------------------------------------------- cliente
def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Cliente:
    def __init__(self, objetivo, rng):
        self.objetivo = objetivo.rstrip("/")
        self.ua = rng.choice(USER_AGENTS)
        self.codigos = {}
        self.peticiones = 0
        self.fallos_red = 0

    def get(self, ruta):
        req = urllib.request.Request(self.objetivo + ruta, headers={"User-Agent": self.ua})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                r.read()
                codigo = r.status
        except urllib.error.HTTPError as e:
            codigo = e.code
        except (urllib.error.URLError, OSError):
            self.fallos_red += 1
            return None
        self.peticiones += 1
        self.codigos[str(codigo)] = self.codigos.get(str(codigo), 0) + 1
        return codigo


def visita(cli, rng, p404):
    pagina = rng.choice(PAGINAS)
    cli.get(pagina)
    for r in recursos_de(pagina):
        cli.get(r)
    if rng.random() < 0.3:
        cli.get("/favicon.ico")            # los navegadores lo piden aunque no exista
    if rng.random() < p404:
        cli.get(rng.choice(ROTOS))         # enlace roto o error de tipeo


def benigno(args, rng, cli):
    fin = time.monotonic() + args.duracion
    rafagas = sorted(rng.uniform(5, max(6, args.duracion - 20)) for _ in range(args.rafagas))
    t0 = time.monotonic()
    while time.monotonic() < fin:
        if rafagas and time.monotonic() - t0 >= rafagas[0]:
            rafagas.pop(0)
            for _ in range(rng.randint(5, 15)):    # navegación rápida: varias páginas seguidas
                visita(cli, rng, args.p404)
                time.sleep(rng.uniform(0.1, 0.5))
            continue
        visita(cli, rng, args.p404)
        time.sleep(min(rng.expovariate(args.tasa), max(0.0, fin - time.monotonic())))


def exploracion(args, rng, cli):
    fin = time.monotonic() + args.duracion
    rutas = RUTAS_EXPLORACION[:]
    rng.shuffle(rutas)
    i = 0
    while time.monotonic() < fin:
        ruta = rutas[i % len(rutas)]
        if i >= len(rutas):                 # segunda vuelta: variantes con extensiones
            ruta = ruta.rstrip("/") + rng.choice([".bak", ".old", ".zip", "~", ".php"])
        cli.get("/" + ruta)
        i += 1
        time.sleep(min(rng.expovariate(args.tasa), max(0.0, fin - time.monotonic())))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--generar-sitio", metavar="DIR")
    p.add_argument("--modo", choices=["benigno", "exploracion"])
    p.add_argument("--duracion", type=float)
    p.add_argument("--semilla", type=int)
    p.add_argument("--tasa", type=float, default=0.4, help="visitas (benigno) o peticiones (exploracion) por segundo")
    p.add_argument("--rafagas", type=int, default=0)
    p.add_argument("--p404", type=float, default=0.05, help="probabilidad de pedir un recurso roto por visita")
    p.add_argument("--objetivo", default="http://172.30.0.1")
    args = p.parse_args()

    if args.generar_sitio:
        generar_sitio(args.generar_sitio)
        return 0
    if not args.modo or args.duracion is None or args.semilla is None:
        p.error("--modo, --duracion y --semilla son obligatorios")

    rng = random.Random(args.semilla)
    cli = Cliente(args.objetivo, rng)
    resumen = {"modo": args.modo, "semilla": args.semilla, "inicio_real": ahora()}
    try:
        (benigno if args.modo == "benigno" else exploracion)(args, rng, cli)
    finally:
        resumen.update(fin_real=ahora(), peticiones=cli.peticiones, codigos=cli.codigos,
                       fallos_red=cli.fallos_red, user_agent=cli.ua)
        print(json.dumps(resumen), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
