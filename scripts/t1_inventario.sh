#!/usr/bin/env bash
# Inventario de recursos y versiones del laboratorio (Tarea 1). Se ejecuta en la VM, desde la raíz del repo:
#     bash scripts/t1_inventario.sh
# Salida: results/t1/inventario_<fecha>.txt  -> base de la tabla de recursos del informe.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
set -a; source "$REPO_DIR/.env"; set +a
OUT="$REPO_DIR/results/t1/inventario_$(date +%Y%m%d_%H%M%S).txt"
exec > >(tee "$OUT") 2>&1

sec() { echo; echo "===== $1 ====="; }

echo "Inventario del laboratorio — $(date -Is)"

sec "Sistema operativo y kernel";  lsb_release -ds; uname -srmo
sec "CPU";                         lscpu | grep -E '^(Model name|CPU\(s\)|Thread|Core|Socket|Hypervisor)'
sec "Memoria";                     free -h
sec "Disco";                       df -h / /var/lib/docker 2>/dev/null
sec "Reloj / NTP";                 timedatectl; chronyc tracking 2>/dev/null | grep -E 'Reference|System time|Last offset'

sec "Versiones de servicios monitoreados"
echo "auditd:  $(auditctl -v 2>/dev/null || dpkg-query -W -f='${Version}' auditd)"
echo "apache2: $(apache2 -v | head -1)"
echo "filebeat: $(filebeat version 2>/dev/null || echo 'no instalado')"

sec "Docker"
docker version --format 'Docker Engine {{.Server.Version}}'
docker compose version

sec "Stack Elastic (STACK_VERSION=$STACK_VERSION)"
docker compose -f "$REPO_DIR/docker-compose.yml" ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
curl -s -u "elastic:$ELASTIC_PASSWORD" http://127.0.0.1:9200/_nodes/jvm \
  | jq -r '.nodes[] | "ES \(.version) | heap max: \(.jvm.mem.heap_max_in_bytes/1073741824) GB | JVM \(.jvm.version)"'

sec "Límites y consumo de los contenedores"
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'

sec "Reglas auditd cargadas"
auditctl -l 2>/dev/null || echo "(requiere sudo: sudo auditctl -l)"

sec "Firewall"
ufw status 2>/dev/null || echo "(requiere sudo: sudo ufw status verbose)"

echo; echo "Guardado en $OUT"
