#!/usr/bin/env bash
# T3 — Preparación de los escenarios. LEERLO ANTES DE EJECUTARLO. En la VM, desde la raíz del repo:
#     sudo bash scripts/t3_setup.sh
#
# Hace:
#   1. Copia los generadores a /opt/lab/gen (legibles por labuser y por los contenedores)
#   2. Crea el directorio de trabajo de labuser con archivos propios de prueba
#   3. Publica en Apache el sitio de prueba (respalda el index.html original de Ubuntu)
#   4. Crea la red Docker "labnet" (172.30.0.0/24; el anfitrión es 172.30.0.1)
#   5. ufw: permite HTTP desde labnet (los clientes llegan a Apache por la interfaz de la red Docker)
#   6. Descarga la imagen python:3.12-alpine para los clientes HTTP
#   7. Prueba corta de los dos generadores
# Es idempotente.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecutar con sudo."; exit 1; }
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

echo "== 1. Generadores en /opt/lab/gen"
install -d -m 755 -o root -g root /opt/lab/gen
install -m 644 -o root -g root src/generacion/linux_actividad.py src/generacion/http_cliente.py src/generacion/lote.py /opt/lab/gen/
ls -l /opt/lab/gen

echo "== 2. Directorio de trabajo de labuser"
T=/home/labuser/trabajo
install -d -m 750 -o labuser -g labuser "$T"
[ -f "$T/notas.txt" ] || printf 'Notas de trabajo del usuario de prueba.\nInforme semanal pendiente.\nRevisar datos.csv\n' > "$T/notas.txt"
[ -f "$T/datos.csv" ] || { echo "id,valor,categoria"; for i in $(seq 1 200); do echo "$i,$((RANDOM % 1000)),c$((i % 7))"; done; } > "$T/datos.csv"
[ -f "$T/diario.txt" ] || echo "Diario del usuario de prueba" > "$T/diario.txt"
chown -R labuser:labuser "$T"
ls -l "$T"

echo "== 3. Sitio de prueba en Apache"
[ -f /var/www/html/index.html.ubuntu ] || { [ -f /var/www/html/index.html ] && cp /var/www/html/index.html /var/www/html/index.html.ubuntu; } || true
python3 /opt/lab/gen/http_cliente.py --generar-sitio /var/www/html
chown -R root:root /var/www/html && chmod -R a+rX /var/www/html

echo "== 4. Red Docker labnet"
docker network inspect labnet >/dev/null 2>&1 || docker network create --subnet 172.30.0.0/24 --gateway 172.30.0.1 labnet
docker network inspect labnet --format '{{range .IPAM.Config}}{{.Subnet}} gw {{.Gateway}}{{end}}'

echo "== 5. ufw: HTTP desde labnet"
ufw allow from 172.30.0.0/24 to any port 80 proto tcp
ufw status | grep -E '^(80|22|5601)/tcp'

echo "== 6. Imagen de los clientes HTTP"
docker pull -q python:3.12-alpine

echo "== 7. Prueba de los generadores"
docker run --rm --network labnet --ip 172.30.0.5 -v /opt/lab/gen:/gen:ro python:3.12-alpine \
  python /gen/http_cliente.py --modo benigno --duracion 3 --semilla 1 --tasa 1
sleep 1
echo "Última línea de access.log (debe empezar con 172.30.0.5):"
tail -n 1 /var/log/apache2/access.log
sudo -u labuser python3 /opt/lab/gen/linux_actividad.py --modo benigno --duracion 3 --semilla 1 --tasa 2

echo
echo "Listo. Siguiente paso: reiniciar la ingesta y correr el piloto (paso_a_paso/03_escenarios.md)."
