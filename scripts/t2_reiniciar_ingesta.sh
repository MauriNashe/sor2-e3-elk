#!/usr/bin/env bash
# Reinicia la ingesta desde cero: deja los índices de logs vacíos y Filebeat leyendo desde el principio.
# Se usa después de cambiar el parseo (T2) y antes del lote de sesiones (T3), para partir de datos limpios.
# LEERLO ANTES DE EJECUTARLO: BORRA los índices lab-auditd-*, lab-apache-* y lab-otros-*.
# En la VM, desde la raíz del repo:
#     sudo bash scripts/t2_reiniciar_ingesta.sh
#
# Hace:
#   1. Detiene Filebeat
#   2. Rota audit.log (el archivo activo queda vacío; el anterior pasa a audit.log.1 y no se vuelve a leer)
#   3. Borra los índices de logs del laboratorio (no toca lab-test ni lab-alertas*)
#   4. Vacía el registro de posiciones de Filebeat
#   5. Arranca Filebeat: vuelve a leer audit.log (vacío) y access.log/error.log desde el principio
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecutar con sudo."; exit 1; }
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
set -a; source .env; set +a
ES="http://127.0.0.1:9200"
AUTH="elastic:${ELASTIC_PASSWORD}"

echo "== 1. Detener Filebeat"
systemctl stop filebeat
systemctl is-active filebeat || true

echo "== 2. Rotar audit.log"
kill -USR1 "$(pidof auditd)"        # SIGUSR1: auditd rota sus logs
sleep 2
ls -l /var/log/audit/

echo "== 3. Borrar índices de logs"
# Elasticsearch no permite borrar con comodines (action.destructive_requires_name): se borra por nombre.
for idx in $(curl -s -u "$AUTH" "$ES/_cat/indices/lab-auditd-*,lab-apache-*,lab-otros-*?h=index&expand_wildcards=open"); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" -X DELETE "$ES/$idx")
  echo "  DELETE $idx -> HTTP $code"
done

echo "== 4. Vaciar el registro de Filebeat"
rm -rf /var/lib/filebeat/registry
echo "  /var/lib/filebeat/registry eliminado"

echo "== 5. Arrancar Filebeat"
systemctl start filebeat
sleep 5
systemctl is-active filebeat

echo
echo "Listo. Esperar ~20 s y correr: bash scripts/t2_verificar.sh"
