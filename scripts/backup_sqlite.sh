#!/usr/bin/env bash
# backup_sqlite.sh
# Faz backup do arquivo SQLite fornecido (first arg) ou usa DB_FILE env.
# Uso: ./scripts/backup_sqlite.sh /data/sorteios.db

set -euo pipefail
DB_FILE="${1:-${DB_FILE:-./data/sorteios.db}}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

if [ ! -f "$DB_FILE" ]; then
  echo "Arquivo de DB não encontrado: $DB_FILE"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
TS=$(date +"%Y%m%d_%H%M%S")
OUT="$BACKUP_DIR/sorteios_${TS}.db"

# usa sqlite3 .backup para garantir consistência
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_FILE" ".backup '$OUT'"
  echo "Backup realizado: $OUT"
else
  # fallback: cópia direta (pode resultar em arquivo inconsistente sem WAL)
  cp "$DB_FILE" "$OUT"
  echo "sqlite3 não encontrado, backup por cópia: $OUT"
fi

# opcional: remover backups antigos (ex: manter 30 últimos)
KEEP=${KEEP:-30}
ls -1t "$BACKUP_DIR"/sorteios_*.db 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm --
