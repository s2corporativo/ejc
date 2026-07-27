#!/usr/bin/env bash
# Manutenção de limpeza da VPS de produção (disco, Docker, pacotes, logs).
#
# Uso:
#   scripts/vps_maintenance.sh            # modo auditoria (padrão): só relata, não apaga nada
#   scripts/vps_maintenance.sh --apply    # executa a limpeza de fato
#
# Escopo deliberadamente conservador — nunca toca em:
#   - volumes Docker (podem conter dados do Postgres/Redis)
#   - qualquer coisa dentro de /opt/ejc (código, .env, uploads, backups da aplicação)
#   - backups locais da aplicação (retenção já é gerida por BACKUP_RETENCAO_DIAS
#     em backend/app/services/backup_service.py)
set -euo pipefail

APPLY=0
if [ "${1:-}" = "--apply" ]; then
  APPLY=1
fi

section() {
  echo
  echo "## $1"
}

section "Disco (df -h)"
df -h / /var 2>/dev/null || df -h

section "Maiores diretórios em /opt/ejc (top 15)"
du -sh /opt/ejc/*/ 2>/dev/null | sort -rh | head -15 || echo "(sem acesso a /opt/ejc ou vazio)"

section "Uso de disco pelo Docker (docker system df)"
docker system df -v 2>/dev/null || echo "(docker indisponível)"

section "Imagens Docker dangling (<none>)"
dangling_count="$(docker images -f "dangling=true" -q 2>/dev/null | wc -l)" \
  && echo "quantidade: $dangling_count" || echo "(docker indisponível)"

section "Containers parados (exited/dead)"
docker ps -a --filter "status=exited" --filter "status=dead" --format '{{.Names}} ({{.Status}})' || true

section "Cache de build do Docker"
docker system df --format '{{.Type}}\t{{.Size}}\t{{.Reclaimable}}' 2>/dev/null | grep -i "build cache" || true

section "Journal de logs do sistema"
journalctl --disk-usage 2>/dev/null || echo "(journalctl indisponível)"

section "Cache do apt"
du -sh /var/cache/apt/archives 2>/dev/null || echo "(sem acesso a /var/cache/apt)"

section "Pacotes órfãos (apt-get autoremove --dry-run)"
apt-get autoremove --dry-run 2>/dev/null | grep -E '^(Remv|The following)' || echo "(nenhum ou apt indisponível)"

if [ "$APPLY" -eq 0 ]; then
  section "Modo auditoria — nada foi alterado"
  echo "Rode com --apply para executar a limpeza real (prune de imagens/containers/build cache Docker,"
  echo "apt-get autoremove/clean, journalctl --vacuum-time=14d)."
  exit 0
fi

section "Aplicando limpeza"

echo "-- docker container prune (apenas containers parados)"
docker container prune -f

echo "-- docker image prune (apenas imagens dangling, sem -a)"
docker image prune -f

echo "-- docker builder prune (cache de build)"
docker builder prune -f

echo "-- apt-get autoremove/clean"
apt-get autoremove -y
apt-get clean

echo "-- journalctl --vacuum-time=14d"
journalctl --vacuum-time=14d

section "Resultado após limpeza"
df -h / /var 2>/dev/null || df -h
docker system df 2>/dev/null || true
