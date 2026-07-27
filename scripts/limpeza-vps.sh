#!/usr/bin/env bash
# EJC — higiene do VPS: remove lixo acumulado sem tocar em dados.
#
# A VPS hospeda PRODUÇÃO de vários projetos (EJC, s2licit, verdelimp, graphiti)
# e o runner self-hosted do CI. Por isso este script é deliberadamente tímido:
#
#   - NUNCA remove volumes Docker. `docker system prune --volumes` apaga o
#     volume de qualquer container parado — é assim que se perde um banco
#     durante uma janela de manutenção.
#   - NUNCA usa `docker system prune -a`: isso remove imagens não referenciadas
#     por container EM EXECUÇÃO, quebrando o rollback de uma stack parada.
#   - Só apaga imagens órfãs (dangling), cache de build, caches de pacote e
#     logs além da retenção.
#   - Recusa mexer no runner enquanto houver job de CI em execução.
#
# Padrão é DRY-RUN: sem `--apply` nada é removido, só se relata o que seria.
#
# Uso:
#   sudo bash scripts/limpeza-vps.sh              # relatório (não apaga nada)
#   sudo bash scripts/limpeza-vps.sh --apply      # executa a limpeza
#   RETENCAO_LOG_DIAS=30 sudo bash scripts/limpeza-vps.sh --apply
set -euo pipefail

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

RETENCAO_JOURNAL="${RETENCAO_JOURNAL:-14d}"     # logs do systemd
RETENCAO_LOG_DIAS="${RETENCAO_LOG_DIAS:-30}"    # /var/log rotacionados
RETENCAO_DIAG_DIAS="${RETENCAO_DIAG_DIAS:-7}"   # _diag do runner
RUNNER_HOME="${RUNNER_HOME:-/opt/actions-runner}"
RUNNER_SVC="${RUNNER_SVC:-actions.runner.s2corporativo-ejc.ejc-vps}"

titulo() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
acao()   { if [ "$APPLY" = "1" ]; then echo "  → $*"; else echo "  [dry-run] $*"; fi; }
rodar()  { [ "$APPLY" = "1" ] && eval "$@" || true; }

# ── Diagnóstico: sempre antes de remover ──────────────────────────────────────
titulo "Espaço em disco"
df -h / | tail -1
echo
df -i / | tail -1 | awk '{print "inodes: " $5 " usados (" $3 " de " $2 ")"}'

titulo "Maiores consumidores"
du -sh /var/log /var/lib/docker "$RUNNER_HOME/_work" "$RUNNER_HOME/_diag" 2>/dev/null || true
echo "journald: $(journalctl --disk-usage 2>/dev/null | grep -oE '[0-9.]+[KMG]' | tail -1 || echo '?')"

if command -v docker >/dev/null 2>&1; then
  titulo "Docker (antes)"
  docker system df 2>/dev/null || true
fi

[ "$APPLY" = "1" ] || titulo "MODO RELATÓRIO — nada será removido (use --apply)"

# ── 1. APT: pacotes órfãos, kernels antigos e cache ───────────────────────────
titulo "APT"
if command -v apt-get >/dev/null 2>&1; then
  acao "apt-get autoremove --purge (pacotes órfãos e kernels antigos)"
  rodar "apt-get autoremove --purge -y >/dev/null"
  acao "apt-get clean (cache de .deb)"
  rodar "apt-get clean"
else
  echo "  apt-get ausente — ignorado"
fi

# ── 2. Logs do systemd ────────────────────────────────────────────────────────
titulo "journald (retenção: $RETENCAO_JOURNAL)"
acao "journalctl --vacuum-time=$RETENCAO_JOURNAL"
rodar "journalctl --vacuum-time=$RETENCAO_JOURNAL >/dev/null 2>&1"

# ── 3. Logs rotacionados em /var/log ──────────────────────────────────────────
titulo "/var/log (rotacionados > $RETENCAO_LOG_DIAS dias)"
n=$(find /var/log -type f \( -name '*.gz' -o -regex '.*\.[0-9]+$' \) \
      -mtime "+$RETENCAO_LOG_DIAS" 2>/dev/null | wc -l)
acao "remover $n arquivo(s) rotacionado(s)"
rodar "find /var/log -type f \\( -name '*.gz' -o -regex '.*\\.[0-9]+$' \\) -mtime +$RETENCAO_LOG_DIAS -delete 2>/dev/null"

# ── 4. Docker: só o que é seguro ──────────────────────────────────────────────
titulo "Docker (imagens órfãs e cache de build)"
if command -v docker >/dev/null 2>&1; then
  echo "  containers em execução (preservados):"
  docker ps --format '    {{.Names}} ({{.Status}})' 2>/dev/null || true
  acao "docker image prune -f   # SOMENTE dangling; nunca -a"
  rodar "docker image prune -f >/dev/null"
  acao "docker builder prune -f # cache de build"
  rodar "docker builder prune -f >/dev/null"
  echo "  volumes: PRESERVADOS por decisão de projeto (contêm os bancos)"
else
  echo "  docker ausente — ignorado"
fi

# ── 5. Runner do CI: só com a fila parada ─────────────────────────────────────
titulo "Runner self-hosted"
job_ativo=0
if pgrep -f 'Runner.Worker' >/dev/null 2>&1; then job_ativo=1; fi
if [ "$job_ativo" = "1" ]; then
  echo "  ⚠ há JOB DE CI EM EXECUÇÃO (Runner.Worker ativo) — nada será tocado aqui."
  echo "    Rode de novo quando o runner estiver ocioso."
else
  echo "  runner ocioso ($(systemctl is-active "$RUNNER_SVC" 2>/dev/null || echo 'estado desconhecido'))"
  n=$(find "$RUNNER_HOME/_diag" -type f -name '*.log' -mtime "+$RETENCAO_DIAG_DIAS" 2>/dev/null | wc -l)
  acao "remover $n log(s) de diagnóstico > $RETENCAO_DIAG_DIAS dias"
  rodar "find '$RUNNER_HOME/_diag' -type f -name '*.log' -mtime +$RETENCAO_DIAG_DIAS -delete 2>/dev/null"
  acao "limpar $RUNNER_HOME/_work/_temp (recriado no próximo job)"
  rodar "rm -rf '$RUNNER_HOME/_work/_temp'/* 2>/dev/null"
fi

# ── Resultado ─────────────────────────────────────────────────────────────────
titulo "Espaço em disco (depois)"
df -h / | tail -1

if [ "$APPLY" != "1" ]; then
  printf '\nNada foi removido. Para executar: sudo bash %s --apply\n' "$0"
fi

# ── Fora do escopo deste script (exigem decisão humana) ───────────────────────
cat <<'NOTA'

Não tratado aqui de propósito — confira manualmente e decida:
  • dumps antigos em volumes de backup (ejc_backups_data, s2licit_backups_data):
    são dados; a retenção é decisão de negócio, não de script.
  • /opt/actions-runner/_work/<repo> completo: apagar força reclone no próximo
    CI (seguro, porém lento). Só compensa sob pressão real de disco.
  • uploads de aplicação: NUNCA entram em rotina de limpeza automática.
NOTA
