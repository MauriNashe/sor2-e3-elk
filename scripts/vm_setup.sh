#!/usr/bin/env bash
# Preparación de la VM monitoreada (Ubuntu Server 24.04 LTS). Tarea 1.
# LEERLO ANTES DE EJECUTARLO. Uso, desde la raíz del repo:
#     sudo bash scripts/vm_setup.sh
#
# Hace:
#   1. Paquetes base: auditd, apache2, ufw, chrony, python3-venv, git, curl, jq
#   2. Docker Engine + plugin compose (repositorio oficial de Docker)
#   3. Filebeat en la MISMA versión que STACK_VERSION (repositorio de Elastic), instalado y detenido
#   4. vm.max_map_count=262144 (requisito de Elasticsearch), persistente
#   5. Usuario sin privilegios "labuser" para los escenarios
#   6. Zona horaria y sincronización NTP (chrony)
#   7. ufw: entrante denegado salvo 22, 80 y 5601 desde la red host-only
#
# No toca la configuración de red (IP fija): eso se hace a mano, ver README.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Ejecutar con sudo."; exit 1; fi
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"; [ -f "$ENV_FILE" ] || ENV_FILE="$REPO_DIR/.env.example"
STACK_VERSION="$(grep -E '^STACK_VERSION=' "$ENV_FILE" | cut -d= -f2)"
LAB_NET="$(grep -E '^LAB_NET=' "$ENV_FILE" | cut -d= -f2)"
STACK_MAJOR="${STACK_VERSION%%.*}"
ADMIN_USER="${SUDO_USER:-}"
TZ_LAB="America/Argentina/Buenos_Aires"

echo "== Versión del stack: $STACK_VERSION (rama ${STACK_MAJOR}.x) | red de laboratorio: $LAB_NET"

echo "== 1. Paquetes base"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y auditd audispd-plugins apache2 ufw chrony \
  python3-venv python3-pip git curl jq ca-certificates gnupg sysstat

echo "== 2. Docker Engine"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
if [ -n "$ADMIN_USER" ]; then usermod -aG docker "$ADMIN_USER"; fi

echo "== 3. Filebeat $STACK_VERSION"
if [ ! -f /usr/share/keyrings/elastic.gpg ]; then
  curl -fsSL https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor -o /usr/share/keyrings/elastic.gpg
fi
echo "deb [signed-by=/usr/share/keyrings/elastic.gpg] https://artifacts.elastic.co/packages/${STACK_MAJOR}.x/apt stable main" \
  > /etc/apt/sources.list.d/elastic-${STACK_MAJOR}.x.list
apt-get update
apt-mark unhold filebeat >/dev/null 2>&1 || true
apt-get install -y --allow-downgrades "filebeat=${STACK_VERSION}"
apt-mark hold filebeat          # evita que un apt upgrade desalinee la versión con el stack
systemctl disable --now filebeat || true   # se configura y arranca en la T2

echo "== 4. vm.max_map_count"
echo "vm.max_map_count=262144" > /etc/sysctl.d/99-elasticsearch.conf
sysctl --system >/dev/null
sysctl vm.max_map_count

echo "== 5. Usuario de prueba labuser (sin sudo, sin contraseña: se usa con 'sudo -u labuser')"
id labuser >/dev/null 2>&1 || useradd -m -s /bin/bash labuser

echo "== 6. Reloj"
timedatectl set-timezone "$TZ_LAB"
systemctl enable --now chrony
timedatectl set-ntp true || true

echo "== 7. Servicios monitoreados"
systemctl enable --now auditd apache2

echo "== 8. Firewall (ufw)"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
for p in 22 80 5601; do ufw allow from "$LAB_NET" to any port "$p" proto tcp; done
ufw --force enable
ufw status verbose

echo
echo "Listo. Cerrá la sesión y volvé a entrar para que '$ADMIN_USER' pueda usar docker sin sudo."
echo "Siguiente paso: cp .env.example .env, completar contraseñas y 'docker compose up -d'."
