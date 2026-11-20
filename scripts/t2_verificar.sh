#!/usr/bin/env bash
# T2 — Verificación mínima de la ingesta. Genera unos pocos eventos conocidos y comprueba que llegan
# parseados a Elasticsearch. En la VM, desde la raíz del repo (SIN sudo; lo pide cuando hace falta):
#     bash scripts/t2_verificar.sh
# Salida: results/t2/verificacion_<fecha>.txt
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
set -a; source .env; set +a
ES="http://127.0.0.1:9200"
AUTH="lab_analyst:${ANALYST_PASSWORD}"
mkdir -p results/t2
OUT="results/t2/verificacion_$(date +%Y%m%d_%H%M%S).txt"
exec > >(tee "$OUT") 2>&1
sudo -v

PASS=0; FAIL=0
check() {  # check "descripción" esperado obtenido
  if [ "$2" = "$3" ]; then echo "  [OK]    $1 (esperado $2, obtenido $3)"; PASS=$((PASS+1))
  else                     echo "  [FALLA] $1 (esperado $2, obtenido $3)"; FAIL=$((FAIL+1)); fi
}
# cuenta QUERY_JSON INDICE -> cantidad de documentos
cuenta() {
  curl -s -u "$AUTH" "$ES/$2/_count" -H 'Content-Type: application/json' -d "$1" | jq -r '.count // "error"'
}

MARCA="t2check$(date +%s)"
T0="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
echo "=== Verificación T2 — $(date -Is) — marca $MARCA — desde $T0 (UTC) ==="

echo
echo "[1] Servicios"
check "filebeat activo" active "$(systemctl is-active filebeat)"
check "reglas de auditd cargadas (lab_*)" 4 "$(sudo auditctl -l | grep -cE '(key=|-k )lab_')"

echo
echo "[2] Generar eventos conocidos"
sudo -u labuser cat /srv/lab/protegido/secreto.txt >/dev/null 2>&1 && echo "  ¡labuser pudo leer el archivo protegido!" \
  || echo "  labuser: lectura de secreto.txt denegada (esperado)"
sudo -u labuser /usr/bin/id >/dev/null
curl -s -o /dev/null -w "  GET /?$MARCA -> %{http_code}\n" "http://127.0.0.1/?$MARCA"
curl -s -o /dev/null -w "  GET /no-existe-$MARCA -> %{http_code}\n" "http://127.0.0.1/no-existe-$MARCA"
echo "  Esperando 20 s a que el pipeline los procese..."
sleep 20

echo
echo "[3] Evidencia en los logs originales"
RAW_PROT=$(sudo ausearch -k lab_protegido -ts recent --format raw 2>/dev/null | grep -c 'type=SYSCALL')
RAW_HTTP=$(sudo grep -c "$MARCA" /var/log/apache2/access.log)
echo "  audit.log: eventos SYSCALL con key=lab_protegido en los últimos 10 min: $RAW_PROT"
echo "  access.log: líneas con la marca: $RAW_HTTP"
check "peticiones de prueba en access.log" 2 "$RAW_HTTP"

echo
echo "[4] Llegada a Elasticsearch"
RANGO="{\"range\":{\"@timestamp\":{\"gte\":\"$T0\"}}}"
N_HTTP=$(cuenta "{\"query\":{\"bool\":{\"filter\":[$RANGO,{\"query_string\":{\"query\":\"*$MARCA*\",\"default_field\":\"url.original\"}}]}}}" "lab-apache-*")
check "peticiones de prueba en lab-apache-*" 2 "$N_HTTP"
# La clave de la regla (key=lab_protegido) la guarda el módulo bajo auditd.log.*; se busca en esos campos.
CLAVE='{"multi_match":{"query":"lab_protegido","fields":["auditd.log.*","tags"],"lenient":true}}'
N_PROT=$(cuenta "{\"query\":{\"bool\":{\"filter\":[$RANGO,$CLAVE]}}}" "lab-auditd-*")
echo "  registros con lab_protegido en lab-auditd-* desde T0: $N_PROT (cada evento de auditd son varios registros)"
[ "$N_PROT" != "error" ] && [ "$N_PROT" -gt 0 ] && check "acceso al archivo protegido llegó a lab-auditd-*" si si \
  || check "acceso al archivo protegido llegó a lab-auditd-*" si no
N_OTROS=$(cuenta '{"query":{"match_all":{}}}' "lab-otros-*")
check "eventos sin módulo (lab-otros-*)" 0 "${N_OTROS/error/0}"
N_ERR=$(cuenta "{\"query\":{\"bool\":{\"filter\":[$RANGO,{\"exists\":{\"field\":\"error.message\"}}]}}}" "lab-auditd-*,lab-apache-*")
check "documentos con error de parseo desde T0" 0 "$N_ERR"

echo
echo "[5] Índices del laboratorio"
curl -s -u "$AUTH" "$ES/_cat/indices/lab-*?v&h=index,health,docs.count,store.size&s=index"

echo
echo "[6] Ejemplo: petición 404 en lab-apache-* (campos y marcas de tiempo)"
curl -s -u "$AUTH" "$ES/lab-apache-*/_search" -H 'Content-Type: application/json' -d "{
  \"size\":1, \"sort\":[{\"@timestamp\":\"desc\"}],
  \"query\":{\"bool\":{\"filter\":[$RANGO,{\"query_string\":{\"query\":\"*no-existe-$MARCA*\",\"default_field\":\"url.original\"}}]}}}" \
  | jq '.hits.hits[0]._source | {
      "@timestamp", host: .host.name, source_ip: .source.ip, method: .http.request.method,
      url: .url.original, status: .http.response.status_code, event: .event, lab: .lab}'

echo
echo "[7] Ejemplo: acceso al archivo protegido en lab-auditd-* (documento completo)"
curl -s -u "$AUTH" "$ES/lab-auditd-*/_search" -H 'Content-Type: application/json' -d "{
  \"size\":1, \"sort\":[{\"@timestamp\":\"desc\"}],
  \"query\":{\"bool\":{\"filter\":[$RANGO,$CLAVE]}}}" \
  | jq '.hits.hits[0]._source'

echo
echo "=== Resultado: $PASS OK, $FAIL fallas ==="
echo "Salida guardada en $REPO_DIR/$OUT"
