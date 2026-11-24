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
check "auditd en formato RAW (sin separador 0x1D en las últimas 200 líneas)" 0 "$(sudo tail -n 200 /var/log/audit/audit.log | grep -c $'\x1d')"
check "auditd sin node=(null)" 0 "$(sudo tail -n 200 /var/log/audit/audit.log | grep -c 'node=(null)')"

echo
echo "[2] Generar eventos conocidos"
sudo -u labuser cat /srv/lab/protegido/secreto.txt >/dev/null 2>&1 && echo "  ¡labuser pudo leer el archivo protegido!" \
  || echo "  labuser: lectura de secreto.txt denegada (esperado)"
sudo -u labuser /usr/bin/id >/dev/null
curl -s -o /dev/null -w "  GET /?$MARCA -> %{http_code}\n" "http://127.0.0.1/?$MARCA"
curl -s -o /dev/null -w "  GET /no-existe-$MARCA -> %{http_code}\n" "http://127.0.0.1/no-existe-$MARCA"
# Latencia observada en la primera prueba: Filebeat lee hasta ~10 s después (backoff de lectura), envía en
# lotes con flush de hasta ~10 s, y los índices lab-* se refrescan cada 5 s (plantilla de Filebeat).
echo "  Esperando 45 s a que el pipeline los procese y queden visibles..."
sleep 45

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
# El módulo guarda la clave de la regla en auditd.log.key. En los registros SYSCALL el tipo de registro
# está en event.action ("syscall"), no en auditd.log.record_type. event.original no está indexado.
CLAVE='{"term":{"auditd.log.key":"lab_protegido"}}'
N_PROT=$(cuenta "{\"query\":{\"bool\":{\"filter\":[$RANGO,$CLAVE]}}}" "lab-auditd-*")
echo "  registros con lab_protegido en lab-auditd-* desde T0: $N_PROT (cada evento de auditd son varios registros)"
[ "$N_PROT" != "error" ] && [ "$N_PROT" -gt 0 ] && check "acceso al archivo protegido llegó a lab-auditd-*" si si \
  || check "acceso al archivo protegido llegó a lab-auditd-*" si no
N_OTROS=$(cuenta '{"query":{"match_all":{}}}' "lab-otros-*")
check "eventos sin módulo (lab-otros-*)" 0 "${N_OTROS/error/0}"
N_ERR=$(cuenta "{\"query\":{\"bool\":{\"filter\":[$RANGO,{\"exists\":{\"field\":\"error.message\"}}]}}}" "lab-auditd-*,lab-apache-*")
check "documentos con error de parseo desde T0" 0 "$N_ERR"
N_ERR_TOT=$(cuenta '{"query":{"exists":{"field":"error.message"}}}' "lab-auditd-*,lab-apache-*")
check "documentos con error de parseo en total" 0 "$N_ERR_TOT"

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
echo "[7] Ejemplo: acceso denegado al archivo protegido en lab-auditd-* (registro SYSCALL)"
SYSCALL_DOC=$(curl -s -u "$AUTH" "$ES/lab-auditd-*/_search" -H 'Content-Type: application/json' -d "{
  \"size\":1, \"sort\":[{\"@timestamp\":\"desc\"}],
  \"query\":{\"bool\":{\"filter\":[$RANGO,$CLAVE,{\"term\":{\"event.action\":\"syscall\"}}]}}}" | jq '.hits.hits[0]._source')
echo "$SYSCALL_DOC" | jq '{
  "@timestamp", host: .host.name, accion: .event.action, clave: .auditd.log.key, serie: .auditd.log.sequence,
  syscall: .auditd.log.syscall, exito: .auditd.log.success, codigo_salida: .process.exit_code,
  uid: .user.id, auid: .user.audit.id, proceso: .process.executable, pid: .process.pid,
  lab: .lab}'

echo
echo "[7b] Latencias del acceso denegado (s): generación -> lectura -> recepción -> indexación"
echo "$SYSCALL_DOC" | jq -r '
  def t: if . == null then null else (sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601) + ((capture("\\.(?<f>[0-9]+)Z$").f // "0") | ("0." + .) | tonumber) end;
  [ (."@timestamp" | t), (.lab.filebeat_read | t), (.lab.logstash_received | t), (.lab.es_ingested | t) ] as $x
  | if ($x | any(. == null)) then "  (falta alguna marca: lab.filebeat_read aparece después de reiniciar Logstash y la ingesta)"
    else "  lectura Filebeat: \(($x[1]-$x[0])*1000|round/1000) | hasta Logstash: \(($x[2]-$x[1])*1000|round/1000) | indexación: \(($x[3]-$x[2])*1000|round/1000) | total: \(($x[3]-$x[0])*1000|round/1000)" end'

echo
echo "[8] Reconstrucción del evento: registros que comparten el número de serie"
SERIE=$(echo "$SYSCALL_DOC" | jq -r '.auditd.log.sequence // empty')
if [ -n "$SERIE" ]; then
  REGS=$(curl -s -u "$AUTH" "$ES/lab-auditd-*/_search" -H 'Content-Type: application/json' -d "{
    \"size\":20, \"sort\":[{\"@timestamp\":\"asc\"}],
    \"query\":{\"bool\":{\"filter\":[$RANGO,{\"term\":{\"auditd.log.sequence\":$SERIE}}]}}}" \
    | jq -c '[.hits.hits[]._source.event.action]')
  echo "  serie $SERIE -> registros: $REGS"
  N_REGS=$(echo "$REGS" | jq 'length')
  [ "$N_REGS" -ge 3 ] && check "el evento tiene varios registros (SYSCALL, CWD, PATH, PROCTITLE)" si si \
    || check "el evento tiene varios registros (SYSCALL, CWD, PATH, PROCTITLE)" si "no ($N_REGS)"
else
  check "el evento tiene varios registros (SYSCALL, CWD, PATH, PROCTITLE)" si "sin SYSCALL"
fi

echo
echo "=== Resultado: $PASS OK, $FAIL fallas ==="
echo "Salida guardada en $REPO_DIR/$OUT"
