#!/usr/bin/env bash
# Archiva los logs brutos de auditd y Apache después del lote (riesgo R1 del plan): permite volver a
# ingestar si cambia el parseo, sin repetir las sesiones. En la VM, desde la raíz del repo:
#     sudo bash scripts/t3_archivar_logs.sh lote
# Deja data/raw/<nombre>_<fecha>/logs.tar.gz y su SHA-256. Los logs son solo del laboratorio
# (usuarios de prueba e IPs de la red Docker), sin datos personales.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecutar con sudo."; exit 1; }
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NOMBRE="${1:-lote}"
DEST="$REPO_DIR/data/raw/${NOMBRE}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DEST"

tar -czf "$DEST/logs.tar.gz" -C / \
  $(cd / && ls -d var/log/audit/audit.log* var/log/apache2/access.log* var/log/apache2/error.log* 2>/dev/null)
( cd "$DEST" && sha256sum logs.tar.gz > logs.tar.gz.sha256 )
tar -tzvf "$DEST/logs.tar.gz"
chown -R "${SUDO_UID:-0}:${SUDO_GID:-0}" "$REPO_DIR/data/raw"
echo "Archivado en $DEST"
cat "$DEST/logs.tar.gz.sha256"
