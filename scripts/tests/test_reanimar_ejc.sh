#!/usr/bin/env bash
# Regressão de scripts/reanimar_ejc.sh — o script que reergue a produção.
#
# Um script de recuperação errado é pior que não ter script: ele roda no pior
# momento possível, com o sistema já fora do ar e alguém sob pressão. Estes
# testes travam as garantias que não podem depender de revisão humana.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/reanimar_ejc.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }
ok()   { printf '  ok · %s\n' "$*"; }

[ -f "$SCRIPT" ] || fail "reanimar_ejc.sh ausente"
[ -x "$SCRIPT" ] || fail "reanimar_ejc.sh não é executável"
bash -n "$SCRIPT" || fail "erro de sintaxe"
ok "sintaxe e bit de execução"

# ── Nenhum comando destrutivo, em nenhuma fase ──────────────────────────────
# A lista espelha a §6 do CLAUDE.md. Recuperação nunca destrói dado: o sistema
# já está quebrado, e a única coisa pior é ficar quebrado E sem os dados.
for proibido in 'down -v' 'volume rm' 'system prune' 'rm -rf' 'dropdb' \
                'downgrade' 'reset --hard' 'clean -fd' 'deploy_vps_safe.sh'; do
  # Ignora as linhas de comentário, que CITAM os proibidos de propósito.
  if grep -v '^\s*#' "$SCRIPT" | grep -Fq -- "$proibido"; then
    fail "comando destrutivo '$proibido' presente em código executável"
  fi
done
ok "nenhum comando destrutivo em código executável"

# ── Toda sondagem HTTP tem teto de tempo ────────────────────────────────────
# É a lição do incidente: o watchdog antigo travou porque sondava sem
# --max-time. Um script de recuperação que pendura não recupera nada.
while IFS= read -r linha; do
  case "$linha" in *-m\ *|*--max-time*) ;; *) fail "curl sem teto: $linha" ;; esac
done < <(grep -v '^\s*#' "$SCRIPT" | grep -o 'curl [^|)]*')
ok "toda sondagem curl tem teto de tempo"

# ── Passo irreversível atrás de confirmação ─────────────────────────────────
grep -q 'Digite "sim" para seguir' "$SCRIPT" || fail "confirmação não exige 'sim' explícito"
grep -q 'cp -p "\$APP_DIR/.env"' "$SCRIPT" || fail "não faz backup do .env antes de alterá-lo"
ok "confirmação explícita e backup do .env"

# ── Gates de risco jurídico NÃO ligam sem --assumir-riscos ──────────────────
# O mais importante deste arquivo. Se um refactor mover estas três linhas para
# fora do bloco protegido, o script passa a emitir documento com cálculo não
# homologado, violar licença não comercial e soltar write-tools de IA sem HITL.
bloco_protegido="$(awk '/ASSUMIR_RISCOS" = "1"/,/^  else$/' "$SCRIPT")"
for gate in PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED RAG_RERANK_ENABLED AI_AGENT_ENABLED; do
  total="$(grep -c "definir_flag $gate true" "$SCRIPT" || true)"
  dentro="$(printf '%s' "$bloco_protegido" | grep -c "definir_flag $gate true" || true)"
  [ "$total" = "1" ] || fail "$gate ligado em $total lugares; esperado exatamente 1"
  [ "$dentro" = "1" ] || fail "$gate ligado FORA do bloco --assumir-riscos"
done
ok "os 3 gates de risco só ligam sob --assumir-riscos"

# ── `definir_flag` é idempotente e não corrompe o .env ──────────────────────
# Extrai a função real do script e exercita contra um .env de mentira.
cat > "$TMP/.env" <<'EOF'
EMAIL_ENABLED=false
SMTP_HOST=smtp.antigo.com
OUTRA_COISA=preservar
EOF
cat > "$TMP/harness.sh" <<EOF
set -euo pipefail
APP_DIR="$TMP"
info() { :; }
erro() { printf 'ERRO: %s\n' "\$*" >&2; exit 2; }
$(awk '/^definir_flag\(\)/,/^}/' "$SCRIPT")
definir_flag EMAIL_ENABLED true      # troca valor existente
definir_flag EMAIL_ENABLED true      # idempotente: repetir não duplica
definir_flag NOVA_FLAG sim           # acrescenta a que não existe
definir_flag SMTP_HOST smtp.novo.com # troca valor com pontos
EOF
bash "$TMP/harness.sh" || fail "definir_flag falhou no harness"

grep -qx 'EMAIL_ENABLED=true' "$TMP/.env"   || fail "não trocou o valor existente"
grep -qx 'OUTRA_COISA=preservar' "$TMP/.env" || fail "apagou linha não relacionada"
grep -qx 'NOVA_FLAG=sim' "$TMP/.env"        || fail "não acrescentou flag nova"
grep -qx 'SMTP_HOST=smtp.novo.com' "$TMP/.env" || fail "não trocou valor com pontos"
[ "$(grep -c '^EMAIL_ENABLED=' "$TMP/.env")" = "1" ] || fail "duplicou EMAIL_ENABLED"
ok "definir_flag idempotente e não destrutivo"

# ── Recusa rodar de dentro de /opt/ejc ──────────────────────────────────────
# O script se auto-substituiria durante o checkout da fase de deploy.
grep -q 'rode a partir de um checkout git' "$SCRIPT" || fail "sem guarda de APP_DIR"
ok "recusa executar de dentro do diretório de produção"

# ── Argumento desconhecido falha fechado ────────────────────────────────────
if "$SCRIPT" --modo-inexistente >/dev/null 2>&1; then
  fail "argumento desconhecido não foi rejeitado"
fi
ok "argumento desconhecido falha fechado"

printf '\nTODOS OS TESTES DE reanimar_ejc.sh PASSARAM\n'
