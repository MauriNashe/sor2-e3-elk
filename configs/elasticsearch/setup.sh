#!/usr/bin/env bash
# Inicialización de seguridad de Elasticsearch. Lo ejecuta el servicio "setup" de docker-compose.
# Es idempotente: se puede volver a correr (docker compose up setup) sin romper nada.
#
# Usuarios del laboratorio (mínimo privilegio):
#   elastic           superusuario, solo administración (Kibana UI, setup, filebeat setup)
#   kibana_system     usuario interno de Kibana (built-in, acá solo se le fija la contraseña)
#   logstash_internal rol logstash_writer: SOLO crea documentos en lab-*; no lee ni borra
#   lab_analyst       rol lab_analyst: lee lab-* y sus estadísticas (monitor, para _cat/indices);
#                     escribe solo en lab-alertas* (detector, T7)
set -euo pipefail

ES="http://es01:9200"
AUTH="elastic:${ELASTIC_PASSWORD}"

# Las contraseñas se interpolan en JSON: exigir alfanuméricas para no romper el cuerpo.
for v in ELASTIC_PASSWORD KIBANA_PASSWORD LOGSTASH_INTERNAL_PASSWORD ANALYST_PASSWORD; do
  val="${!v:-}"
  if [ -z "$val" ]; then echo "[setup] ERROR: falta $v en .env"; exit 1; fi
  case "$val" in *[!A-Za-z0-9]*) echo "[setup] ERROR: $v debe ser solo letras y números"; exit 1;; esac
  if [ "${#val}" -lt 12 ]; then echo "[setup] ERROR: $v debe tener al menos 12 caracteres"; exit 1; fi
done

echo "[setup] Esperando a Elasticsearch..."
until [ "$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" "$ES")" = "200" ]; do sleep 5; done

# api MÉTODO RUTA JSON  -> falla (exit 1) si la respuesta no es 2xx
api() {
  local code
  code=$(curl -s -o /tmp/resp.json -w '%{http_code}' -u "$AUTH" -X "$1" "$ES$2" \
         -H 'Content-Type: application/json' -d "$3")
  if [ "${code:0:1}" != "2" ]; then
    echo "[setup] ERROR $1 $2 -> HTTP $code"; cat /tmp/resp.json; echo; exit 1
  fi
  echo "[setup] OK    $1 $2 -> HTTP $code"
}

api POST /_security/user/kibana_system/_password \
  "{\"password\":\"${KIBANA_PASSWORD}\"}"

api PUT /_security/role/logstash_writer '{
  "cluster": ["monitor"],
  "indices": [
    { "names": ["lab-*"], "privileges": ["create_index", "create_doc", "auto_configure"] }
  ]
}'

api POST /_security/user/logstash_internal \
  "{\"password\":\"${LOGSTASH_INTERNAL_PASSWORD}\",\"roles\":[\"logstash_writer\"],\"full_name\":\"Logstash - solo escritura en lab-*\"}"

api PUT /_security/role/lab_analyst '{
  "cluster": ["monitor"],
  "indices": [
    { "names": ["lab-*"],        "privileges": ["read", "view_index_metadata", "monitor"] },
    { "names": ["lab-alertas*"], "privileges": ["create_index", "create_doc", "auto_configure", "read", "view_index_metadata"] }
  ]
}'

api POST /_security/user/lab_analyst \
  "{\"password\":\"${ANALYST_PASSWORD}\",\"roles\":[\"lab_analyst\"],\"full_name\":\"Scripts de analisis y detectores\"}"

echo "[setup] Listo."
