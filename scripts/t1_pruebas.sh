#!/usr/bin/env bash
# Pruebas de la Tarea 1: seguridad, indexación y consulta. Se ejecuta en la VM, desde la raíz del repo:
#     bash scripts/t1_pruebas.sh
# La salida completa queda en results/t1/pruebas_<fecha>.txt (sin contraseñas).
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
set -a; source "$REPO_DIR/.env"; set +a
ES="http://127.0.0.1:9200"
OUT="$REPO_DIR/results/t1/pruebas_$(date +%Y%m%d_%H%M%S).txt"
PASS=0; FAIL=0

exec > >(tee "$OUT") 2>&1

check() {  # check "descripción" esperado obtenido
  if [ "$2" = "$3" ]; then echo "  [OK]    $1 (esperado $2, obtenido $3)"; PASS=$((PASS+1))
  else                     echo "  [FALLA] $1 (esperado $2, obtenido $3)"; FAIL=$((FAIL+1)); fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "=== Pruebas T1 — $(date -Is) — host $(hostname) ==="
echo

echo "[1] Acceso sin credenciales debe ser rechazado"
check "GET / sin auth" 401 "$(code "$ES/")"

echo "[2] Acceso con credenciales"
check "GET / con elastic" 200 "$(code -u "elastic:$ELASTIC_PASSWORD" "$ES/")"
curl -s -u "elastic:$ELASTIC_PASSWORD" "$ES/" | jq '{cluster_name, version: .version.number}'

echo "[3] Indexar documento de prueba en lab-test"
curl -s -u "elastic:$ELASTIC_PASSWORD" -X PUT "$ES/lab-test/_doc/1?refresh=true" \
  -H 'Content-Type: application/json' \
  -d "{\"@timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"mensaje\":\"documento de prueba T1\",\"origen\":\"t1_pruebas.sh\"}" \
  | jq '{_index, _id, result}'

echo "[4] Buscar el documento"
HITS=$(curl -s -u "elastic:$ELASTIC_PASSWORD" "$ES/lab-test/_search?q=origen:t1_pruebas.sh" | jq '.hits.total.value')
check "documentos encontrados en lab-test" 1 "$HITS"

echo "[5] Kibana: verificar a mano desde Windows (captura de Dev Tools: GET lab-test/_search)"
check "Kibana responde en $LAB_IP:5601" 302 "$(code -I "http://$LAB_IP:5601/")"

echo "[6] Elasticsearch NO expuesto fuera de localhost"
check "ES por IP host-only ($LAB_IP:9200) inaccesible" 000 "$(code --max-time 5 "http://$LAB_IP:9200/")"
echo "    Puertos en escucha:"
ss -tlnH | awk '{print "     ", $4}' | grep -E ':(9200|5044|5601|80|22)$'

echo "[7] Mínimo privilegio: logstash_internal no puede leer ni borrar"
check "logstash_internal _search" 403 "$(code -u "logstash_internal:$LOGSTASH_INTERNAL_PASSWORD" "$ES/lab-test/_search")"
check "logstash_internal DELETE índice" 403 "$(code -u "logstash_internal:$LOGSTASH_INTERNAL_PASSWORD" -X DELETE "$ES/lab-test")"
check "lab_analyst puede leer lab-test" 200 "$(code -u "lab_analyst:$ANALYST_PASSWORD" "$ES/lab-test/_search")"
check "lab_analyst no puede escribir en lab-test" 403 "$(code -u "lab_analyst:$ANALYST_PASSWORD" -X POST "$ES/lab-test/_doc" -H 'Content-Type: application/json' -d '{"x":1}')"

echo "[8] Heap de Elasticsearch"
curl -s -u "elastic:$ELASTIC_PASSWORD" "$ES/_nodes/jvm" \
  | jq '.nodes[] | {nodo: .name, version, heap_max_bytes: .jvm.mem.heap_max_in_bytes, heap_max_gb: (.jvm.mem.heap_max_in_bytes/1073741824)}'

echo
echo "=== Resultado: $PASS OK, $FAIL fallas ==="
echo "Salida guardada en $OUT"
