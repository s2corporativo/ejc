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
$(awk '/^_e_segredo\(\)/,/^}/' "$SCRIPT")
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

# ── definir_flag NUNCA imprime valor de segredo ─────────────────────────────
# A revisão do PR pegou a versão anterior imprimindo `$atual → $valor`, o que
# despejava SMTP_PASSWORD, EVOLUTION_API_KEY, DATAJUD_API_KEY e
# VAPID_PRIVATE_KEY no terminal e em qualquer log de incidente capturado.
cat > "$TMP/.env2" <<'EOF'
SMTP_PASSWORD=senha-antiga
EOF
cat > "$TMP/harness2.sh" <<EOF
set -euo pipefail
APP_DIR="$TMP"
info() { printf '   %s\n' "\$*"; }
erro() { printf 'ERRO: %s\n' "\$*" >&2; exit 2; }
$(awk '/^_e_segredo\(\)/,/^}/' "$SCRIPT")
$(awk '/^definir_flag\(\)/,/^}/' "$SCRIPT")
definir_flag SMTP_PASSWORD 'S3nh@-Sup3r-Secreta'
definir_flag EVOLUTION_API_KEY 'chave-evolution-secreta'
definir_flag DATAJUD_API_KEY 'chave-datajud-secreta'
definir_flag VAPID_PRIVATE_KEY 'chave-vapid-secreta'
definir_flag EMAIL_ENABLED true
EOF
mv "$TMP/.env2" "$TMP/.env"
saida="$(bash "$TMP/harness2.sh" 2>&1)" || fail "harness de segredos falhou"
for segredo in 'S3nh@-Sup3r-Secreta' 'senha-antiga' 'chave-evolution-secreta' \
               'chave-datajud-secreta' 'chave-vapid-secreta'; do
  case "$saida" in
    *"$segredo"*) fail "definir_flag IMPRIMIU um segredo na saída: $segredo" ;;
  esac
done
# ...mas continua informando o não-segredo, senão o operador fica cego.
case "$saida" in *"true"*) ;; *) fail "definir_flag deixou de mostrar valor não-secreto" ;; esac
grep -qx 'SMTP_PASSWORD=S3nh@-Sup3r-Secreta' "$TMP/.env" || fail "segredo não foi gravado"
ok "definir_flag grava segredo e nunca o imprime"

# ── definir_flag trata o valor LITERALMENTE (sem interpolação de sed) ────────
# `&`, `\` e `|` são metacaracteres de substituição do sed. Senha de SMTP e
# chave de API os contêm com frequência: a versão anterior gravava credencial
# corrompida em produção, ou abortava no meio do religamento.
cat > "$TMP/.env" <<'EOF'
SMTP_PASSWORD=x
OUTRA=preservar
EOF
for valor in 'a&b' 'a\b' 'a|b' 'p@ss&w|rd\zz' '~!#$%^*()[]{}' 'a/b/c'; do
  cat > "$TMP/harness3.sh" <<EOF
set -euo pipefail
APP_DIR="$TMP"
info() { :; }
erro() { printf 'ERRO: %s\n' "\$*" >&2; exit 2; }
$(awk '/^_e_segredo\(\)/,/^}/' "$SCRIPT")
$(awk '/^definir_flag\(\)/,/^}/' "$SCRIPT")
definir_flag SMTP_PASSWORD '$valor'
EOF
  bash "$TMP/harness3.sh" || fail "definir_flag abortou com o valor: $valor"
  gravado="$(grep '^SMTP_PASSWORD=' "$TMP/.env" | head -1 | cut -d= -f2-)"
  [ "$gravado" = "$valor" ] || fail "valor corrompido: esperado [$valor], gravado [$gravado]"
  grep -qx 'OUTRA=preservar' "$TMP/.env" || fail "linha vizinha destruída com o valor: $valor"
done
ok "definir_flag preserva valor com &, \\, |, / e outros metacaracteres"

# ── Mudança de .env é aplicada RECRIANDO, não reiniciando ───────────────────
# O Docker fixa o ambiente na CRIAÇÃO do container; `docker restart` não relê o
# env_file. A versão anterior gravava tudo certo e não ligava nada.
grep -q 'force-recreate' "$SCRIPT" || fail "não recria os serviços após editar o .env"
for fase in fase_flags fase_ligar_tudo fase_embeddings; do
  corpo="$(awk "/^${fase}\(\) \{/,/^}/" "$SCRIPT")"
  printf '%s' "$corpo" | grep -q 'aplicar_env' \
    || fail "$fase edita o .env e não chama aplicar_env"
  # `if` explícito: `A && fail` sob `set -e` depende de uma exceção sutil da
  # regra de saída e some se alguém reordenar a linha — a mesma classe de bug
  # que este PR corrigiu no script principal.
  if printf '%s' "$corpo" | grep -v '^\s*#' | grep -q 'docker restart'; then
    fail "$fase ainda usa 'docker restart' após editar o .env (não relê env_file)"
  fi
done
ok "fases que editam .env recriam os serviços em vez de reiniciar"

# ── sondar_api devolve SÓ o código em stdout ────────────────────────────────
# A versão anterior imprimia o diagnóstico e o código no mesmo stdout, então
# quem capturava por substituição recebia texto multilinha e a classificação
# caía sempre no ramo "código inesperado" — inclusive com o backend em 200.
cat > "$TMP/harness4.sh" <<EOF
set -euo pipefail
BASE_URL="http://127.0.0.1:9"
$(awk '/^sondar_api\(\)/,/^}/' "$SCRIPT")
c="\$(sondar_api /api/health 2 2>/dev/null)"
printf '%s' "\$c"
EOF
capturado="$(bash "$TMP/harness4.sh")"
[ "$capturado" = "000" ] || fail "sondar_api devolveu [$capturado]; esperado exatamente '000'"
ok "sondar_api devolve só o código em stdout (diagnóstico vai para stderr)"

# ── Deploy exige que o alvo esteja integrado à main ─────────────────────────
grep -q 'merge-base --is-ancestor' "$SCRIPT" \
  || fail "--deploy não verifica se o SHA é ancestral de origin/main"
ok "deploy recusa SHA fora da main"

# ── Falha do pós-deploy é falha da fase ─────────────────────────────────────
corpo_deploy="$(awk '/^fase_deploy\(\) \{/,/^}/' "$SCRIPT")"
if printf '%s' "$corpo_deploy" | grep -q 'post_deploy_check.sh" || aviso'; then
  fail "falha do post_deploy_check está sendo convertida em sucesso"
fi
ok "reprovação do post_deploy_check derruba a fase"

# ── Scripts delegados também têm teto de tempo ──────────────────────────────
# O deploy chama estes; sem teto eles penduram no mesmo modo de falha que o
# script inteiro existe para tratar (TCP aceito, resposta nunca).
for delegado in deploy_manual.sh post_deploy_check.sh; do
  arquivo="$REPO_ROOT/scripts/$delegado"
  [ -f "$arquivo" ] || continue
  while IFS= read -r linha; do
    case "$linha" in *--max-time*|*\ -m\ *) ;; *) fail "curl sem teto em $delegado: $linha" ;; esac
  done < <(grep -v '^\s*#' "$arquivo" | grep -o 'curl [^|)]*')
done
ok "scripts delegados (deploy_manual, post_deploy_check) com teto em todo curl"

# ── Expurgo irreversível exige prova de restauração testada ─────────────────
corpo_ligar="$(awk '/^fase_ligar_tudo\(\) \{/,/^}/' "$SCRIPT")"
printf '%s' "$corpo_ligar" | grep -q 'restauracao-testada' \
  || fail "ENTRADA_EXPURGO_ENABLED (hard delete) liga sem portão de backup restaurável"
ok "expurgo LGPD exige confirmação de restauração testada"

# ── Fases que editam .env conferem permissão antes de agir ──────────────────
grep -q 'exigir_acesso_ao_env' "$SCRIPT" || fail "sem verificação de acesso ao .env"
for fase in fase_flags fase_ligar_tudo fase_embeddings; do
  printf '%s' "$(awk "/^${fase}\(\) \{/,/^}/" "$SCRIPT")" | grep -q 'exigir_acesso_ao_env' \
    || fail "$fase não confere permissão no .env antes de trabalhar"
done
ok "fases que editam .env falham cedo e claro sem permissão"

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
