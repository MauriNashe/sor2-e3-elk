#!/usr/bin/env bash
# T2 — Ingesta: deja auditd y Apache llegando parseados a Elasticsearch.
# LEERLO ANTES DE EJECUTARLO. En la VM, desde la raíz del repo:
#     sudo bash scripts/t2_ingesta_setup.sh
#
# Hace:
#   1. auditd.conf: rotación ampliada (50 MB x 10 archivos) y formato RAW
#   2. Crea el archivo protegido de prueba /srv/lab/protegido/secreto.txt (root, 600)
#   3. Instala y carga las reglas configs/auditd/lab.rules
#   4. Instala configs/filebeat/filebeat.yml en /etc/filebeat
#   5. Elasticsearch: pipeline final "lab-ingested" y plantilla de índice "lab" (mapeo ECS de Filebeat)
#   6. Carga en Elasticsearch los ingest pipelines de los módulos auditd y apache
#   7. Arranca Filebeat y prueba la conexión con Logstash
# Es idempotente: se puede volver a correr.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecutar con sudo."; exit 1; }
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
set -a; source .env; set +a
ES="http://127.0.0.1:9200"
AUTH="elastic:${ELASTIC_PASSWORD}"

FB_VER="$(dpkg-query -W -f='${Version}' filebeat)"
[ "$FB_VER" = "$STACK_VERSION" ] || { echo "ERROR: Filebeat $FB_VER no coincide con STACK_VERSION=$STACK_VERSION"; exit 1; }

# api MÉTODO RUTA ARCHIVO_JSON -> falla si la respuesta no es 2xx
api() {
  local code
  code=$(curl -s -o /tmp/t2_resp.json -w '%{http_code}' -u "$AUTH" -X "$1" "$ES$2" \
         -H 'Content-Type: application/json' --data-binary "@$3")
  if [ "${code:0:1}" != "2" ]; then echo "ERROR $1 $2 -> HTTP $code"; cat /tmp/t2_resp.json; echo; exit 1; fi
  echo "OK    $1 $2 -> HTTP $code"
}

echo "== 1. auditd.conf"
CONF=/etc/audit/auditd.conf
[ -f "$CONF.orig" ] || cp "$CONF" "$CONF.orig"
setconf() {
  if grep -qE "^$1[[:space:]]*=" "$CONF"; then sed -i -E "s|^$1[[:space:]]*=.*|$1 = $2|" "$CONF"
  else echo "$1 = $2" >> "$CONF"; fi
}
setconf max_log_file 50
setconf num_logs 10
setconf max_log_file_action ROTATE
# RAW: el formato ENRICHED (defecto de Ubuntu) agrega valores traducidos tras un separador 0x1D que el
# módulo auditd de Filebeat no sabe parsear. NONE: sin "node=" (con HOSTNAME aplicado por SIGHUP salía
# "node=(null)"); el nombre de host lo aporta Filebeat en host.name.
setconf log_format RAW
setconf name_format NONE
kill -HUP "$(pidof auditd)"          # auditd relee su configuración con SIGHUP
grep -E '^(log_format|max_log_file|num_logs|max_log_file_action|name_format)[[:space:]]*=' "$CONF"

echo "== 2. Archivo protegido de prueba"
install -d -m 755 -o root -g root /srv/lab/protegido
[ -f /srv/lab/protegido/secreto.txt ] || \
  echo "Archivo protegido de prueba del laboratorio. No contiene datos reales." > /srv/lab/protegido/secreto.txt
chown root:root /srv/lab/protegido/secreto.txt
chmod 600 /srv/lab/protegido/secreto.txt
ls -l /srv/lab/protegido/secreto.txt

echo "== 3. Reglas de auditd"
install -m 640 -o root -g root configs/auditd/lab.rules /etc/audit/rules.d/lab.rules
augenrules --load
auditctl -l

echo "== 4. Configuración de Filebeat"
install -m 600 -o root -g root configs/filebeat/filebeat.yml /etc/filebeat/filebeat.yml
filebeat test config -c /etc/filebeat/filebeat.yml

echo "== 5. Elasticsearch: pipeline final y plantilla lab"
api PUT /_ingest/pipeline/lab-ingested configs/elasticsearch/pipeline_lab_ingested.json
filebeat export template -c /etc/filebeat/filebeat.yml -E setup.template.enabled=true > /tmp/fb_template.json
jq -e '.template.mappings' /tmp/fb_template.json > /dev/null \
  || { echo "ERROR: formato inesperado en la plantilla exportada por Filebeat"; exit 1; }
jq '.index_patterns = ["lab-auditd-*", "lab-apache-*", "lab-otros-*"]
    | del(.data_stream)
    | .priority = 200
    | del(.template.settings.index.lifecycle)
    | del(.template.settings["index.lifecycle.name"], .template.settings["index.lifecycle.rollover_alias"])
    | .template.settings.index.final_pipeline = "lab-ingested"
    | .template.settings.index.number_of_replicas = 0
    | .template.mappings.properties.lab = {"properties": {
        "filebeat_read":     {"type": "date"},
        "logstash_received": {"type": "date"},
        "es_ingested":       {"type": "date"}}}
    | ._meta = {"descripcion": "Mapeo ECS de Filebeat '"$STACK_VERSION"' adaptado al laboratorio (sin data stream ni ILM)"}' \
  /tmp/fb_template.json > /tmp/lab_template.json
api PUT /_index_template/lab /tmp/lab_template.json

echo "== 6. Pipelines de los módulos"
filebeat setup --pipelines --modules auditd,apache -c /etc/filebeat/filebeat.yml \
  -E output.logstash.enabled=false \
  -E 'output.elasticsearch.hosts=["http://127.0.0.1:9200"]' \
  -E output.elasticsearch.username=elastic \
  -E 'output.elasticsearch.password=${ELASTIC_PASSWORD}'
curl -s -u "$AUTH" "$ES/_ingest/pipeline/filebeat-${STACK_VERSION}-*" | jq -r 'keys[]'

echo "== 7. Arrancar Filebeat"
systemctl enable filebeat >/dev/null 2>&1
systemctl restart filebeat
sleep 5
systemctl is-active filebeat
filebeat test output -c /etc/filebeat/filebeat.yml

echo
echo "Listo. Siguiente paso: bash scripts/t2_verificar.sh (sin sudo)."
