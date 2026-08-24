#!/usr/bin/env bash
# Regressão do bloco remoto de .github/workflows/recover-selfhosted-runner.yml.
#
# O workflow envia um script por SSH para a VPS em DUAS ramificações (chave e
# senha). Nenhum teste do repositório exercitava esse script — o único teste de
# runner cobre scripts/setup-selfhosted-runner.sh. Sem isto, uma edição futura
# pode reintroduzir a descoberta por /home/*, voltar a executar svc.sh do
# diretório do runner, ou fazer as duas ramificações divergirem em silêncio.
#
# Histórico que justifica cada asserção (Issue #1255, PR #1257):
#   - o glob incluiu /home/*/actions-runner*/ e o svc.sh escolhido rodava com
#     sudo: escalonamento de privilégio local;
#   - depois passou a derivar o dono confiável de .service, arquivo que fica
#     dentro do candidato e pertence a quem o possui: confiança circular;
#   - por fim executar svc.sh do diretório do runner era inseguro por si só,
#     porque o dono do diretório pode substituir o arquivo depois.
# A forma vigente não toca o diretório: opera a unit systemd, que é de root.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKFLOW="$RAIZ/.github/workflows/recover-selfhosted-runner.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

falhas=0
ok()    { printf '  \033[1;32mOK\033[0m    %s\n' "$1"; }
falha() { printf '  \033[1;31mFALHA\033[0m %s\n' "$1"; falhas=$((falhas + 1)); }

[ -f "$WORKFLOW" ] || { echo "workflow não encontrado: $WORKFLOW" >&2; exit 1; }

# ── extrai os blocos remotos ────────────────────────────────────────────────
# Só biblioteca padrão: este teste roda em gate bloqueante (p0-guard e
# ci-local.sh p0) e não pode depender de PyYAML, que nenhum dos dois instala.
# O heredoc é delimitado por texto, então varrer as linhas basta — e o recuo é
# o mesmo da linha terminadora, porque o YAML remove o recuo comum do bloco.
python3 - "$WORKFLOW" "$TMP" <<'PY'
import sys, pathlib
workflow, saida = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
linhas = workflow.read_text(encoding="utf-8").splitlines()

blocos, atual, recuo = [], None, ""
for linha in linhas:
    if atual is None:
        if linha.rstrip().endswith("<<'REMOTE'"):
            atual, recuo = [], None
        continue
    if linha.strip() == "REMOTE":
        recuo_fim = linha[: len(linha) - len(linha.lstrip())]
        corpo = [l[len(recuo_fim):] if l.startswith(recuo_fim) else l for l in atual]
        blocos.append("\n".join(corpo) + "\n")
        atual = None
        continue
    atual.append(linha)

if atual is not None:
    sys.exit("heredoc REMOTE sem terminador")
for i, b in enumerate(blocos, 1):
    (saida / f"bloco{i}.sh").write_text(b, encoding="utf-8")
(saida / "contagem").write_text(str(len(blocos)), encoding="utf-8")
PY

total="$(cat "$TMP/contagem")"
if [ "$total" -eq 2 ]; then
  ok "duas ramificações remotas encontradas (chave e senha)"
else
  falha "esperadas 2 ramificações remotas, encontradas $total"
  echo "[recover-runner-test] abortando: estrutura do workflow mudou." >&2
  exit 1
fi

# ── as duas ramificações não podem divergir ─────────────────────────────────
if diff -q "$TMP/bloco1.sh" "$TMP/bloco2.sh" >/dev/null; then
  ok "ramificações de chave e senha são idênticas"
else
  falha "ramificações divergiram — corrija as duas juntas"
  diff -u "$TMP/bloco1.sh" "$TMP/bloco2.sh" | head -30 >&2 || true
fi

# ── sintaxe ─────────────────────────────────────────────────────────────────
for b in "$TMP"/bloco*.sh; do
  if bash -n "$b" 2>/dev/null; then ok "sintaxe válida em $(basename "$b")"
  else falha "sintaxe inválida em $(basename "$b")"; fi
done

# ── invariantes de segurança ────────────────────────────────────────────────
proibido() {
  if grep -q -- "$1" "$TMP/bloco1.sh"; then falha "$2"; else ok "$2"; fi
}
exigido() {
  if grep -q -- "$1" "$TMP/bloco1.sh"; then ok "$2"; else falha "$2"; fi
}

proibido '/home/'          'não procura runner sob /home (escalonamento via sudo)'
proibido './svc.sh'        'não executa svc.sh do diretório do runner'
proibido 'cd "$runner_dir"' 'não faz cd para diretório de runner'
proibido 'systemctl show -p User' 'não deriva confiança de .service (laço circular)'
exigido  'list-unit-files' 'descobre o runner pela unit systemd'
exigido  'sudo systemctl restart' 'cicla o serviço com restart (stop engolido mascarava runner travado)'
proibido 'systemctl stop' 'não usa stop+start: stop falho + start no-op reportava recuperação falsa'
exigido  'actions.runner.s2corporativo-ejc' 'restringe a descoberta ao runner deste repositório'

# Invariante que protege ESTE arquivo, não a VPS. Os dublês abaixo interceptam
# `sudo` e `systemctl` pelo PATH, e isso só funciona enquanto o bloco remoto os
# invoca pelo nome. Um endurecimento plausível — trocar `sudo systemctl` por
# `/usr/bin/sudo systemctl` — contornaria os dublês, e aí este teste, que é gate
# bloqueante e roda na máquina do desenvolvedor via `ci-local.sh p0`, executaria
# systemctl de verdade sobre a unit de produção nomeada na linha do cenário
# saudável. Numa máquina com systemd e sudo NOPASSWD, pararia o runner.
proibido '/usr/bin/sudo'   'não invoca sudo por caminho absoluto (contornaria o dublê do teste)'
proibido '/bin/systemctl'  'não invoca systemctl por caminho absoluto (idem)'

# O teste extrai só o heredoc; as opções de SSH ficam fora dele e nada as cobria.
# Um `StrictHostKeyChecking=no` numa das ramificações passaria despercebido.
if [ "$(grep -c 'StrictHostKeyChecking=yes' "$WORKFLOW")" -eq 2 ]; then
  ok 'as duas ramificações SSH exigem StrictHostKeyChecking=yes'
else
  falha 'StrictHostKeyChecking=yes ausente ou não presente nas duas ramificações'
fi
if grep -q 'StrictHostKeyChecking=no\|UserKnownHostsFile=/dev/null' "$WORKFLOW"; then
  falha 'verificação de host key desativada no workflow'
else
  ok 'verificação de host key não é desativada em lugar nenhum'
fi

# ── comportamento, com systemctl e sudo simulados ───────────────────────────
BIN="$TMP/bin"; mkdir -p "$BIN"
cat > "$BIN/sudo" <<'EOS'
#!/usr/bin/env bash
exec "$@"
EOS
cat > "$BIN/systemctl" <<'EOS'
#!/usr/bin/env bash
acao="$1"; shift || true
case "$acao" in
  # systemctl list-unit-files sai 1 quando nenhum arquivo de unit casa — é o
  # comportamento real, e é o que o fallback para list-units existe para tratar.
  # Filtra pelo padrão recebido, como o systemctl real. Sem isto o dublê
  # devolveria tudo e o cenário do runner alheio não provaria nada.
  list-unit-files|list-units)
    padrao=""
    for arg in "$@"; do case "$arg" in --*) ;; *) padrao="$arg" ;; esac; done
    if [ "$acao" = "list-unit-files" ]; then origem="${FAKE_UNIT_FILES:-}"; else origem="${FAKE_UNITS:-}"; fi
    casou=""
    for u in $origem; do
      case "$u" in ${padrao:-*}) casou="$casou $u" ;; esac
    done
    [ -z "$casou" ] || printf '%s\n' $casou
    if [ "$acao" = "list-unit-files" ] && [ -z "$casou" ]; then exit 1; fi ;;
  restart) echo "restart $1" >> "${FAKE_LOG:?}"
           [ "${FAKE_START_FAIL:-}" != "$1" ] || exit 1 ;;
  # stop e start seguem simulados para que, se alguém os reintroduzir, o cenário
  # de regressão abaixo consiga demonstrar por que eles mascaravam a falha.
  stop)  echo "stop $1" >> "${FAKE_LOG:?}"
         [ "${FAKE_STOP_FAIL:-}" != "$1" ] || exit 1 ;;
  start) echo "start $1" >> "${FAKE_LOG:?}" ;;
  is-active) if [ "${FAKE_SEMPRE_ATIVO:-}" = "1" ]; then exit 0; fi
             [ "${FAKE_ATIVO:-1}" = "1" ] && [ "${FAKE_START_FAIL:-}" != "$2" ] ;;
  status)    echo "status simulado" ;;
esac
EOS
chmod +x "$BIN/sudo" "$BIN/systemctl"

rodar() { FAKE_UNIT_FILES="$1" FAKE_UNITS="$1" FAKE_ATIVO="${2:-1}" \
            FAKE_START_FAIL="${3:-}" FAKE_LOG="$TMP/log" PATH="$BIN:$PATH" \
            bash "$TMP/bloco1.sh" >"$TMP/out" 2>&1; }

# Só a unit carregada existe; nenhum arquivo de unit casa. list-unit-files sai 1.
rodar_so_fallback() { FAKE_UNIT_FILES="" FAKE_UNITS="$1" FAKE_ATIVO=1 \
            FAKE_START_FAIL="" FAKE_LOG="$TMP/log" PATH="$BIN:$PATH" \
            bash "$TMP/bloco1.sh" >"$TMP/out" 2>&1; }

: > "$TMP/log"
if rodar 'actions.runner.s2corporativo-ejc.ejc-vps.service' 1; then
  if grep -q 'restart actions.runner.s2corporativo-ejc.ejc-vps.service' "$TMP/log"; then
    ok 'unit encontrada é reiniciada via systemctl'
  else
    falha 'unit encontrada não foi reiniciada'; cat "$TMP/log" >&2
  fi
else
  falha 'runner saudável deveria sair com 0'; cat "$TMP/out" >&2
fi

: > "$TMP/log"
if rodar '' 1; then
  falha 'sem unit registrada deveria falhar'
else
  rc=$?
  [ "$rc" -eq 4 ] && ok 'sem unit registrada aborta com exit 4' \
                  || falha "sem unit registrada saiu com $rc, esperado 4"
fi

: > "$TMP/log"
if rodar 'actions.runner.s2corporativo-ejc.a.service' 0; then
  falha 'unit que não sobe deveria falhar'
else
  rc=$?
  [ "$rc" -eq 6 ] && ok 'unit que não fica ativa aborta com exit 6' \
                  || falha "unit inativa saiu com $rc, esperado 6"
fi

: > "$TMP/log"
if rodar 'actions.runner.s2corporativo-ejc.a.service actions.runner.s2corporativo-ejc.c.service' 1; then
  n="$(grep -c '^restart ' "$TMP/log")"
  [ "$n" -eq 2 ] && ok 'múltiplas units: todas reiniciadas' \
                 || falha "múltiplas units: $n reiniciadas, esperado 2"
else
  falha 'múltiplas units saudáveis deveriam sair com 0'; cat "$TMP/out" >&2
fi

# Regressão específica: `list-unit-files` sai 1 quando nada casa. Sem `|| true`,
# `set -euo pipefail` aborta na atribuição e o fallback para `list-units` — que
# existe justamente para esse caso — nunca roda.
: > "$TMP/log"
if rodar_so_fallback 'actions.runner.s2corporativo-ejc.carregada.service'; then
  if grep -q '^restart actions.runner.s2corporativo-ejc.carregada.service' "$TMP/log"; then
    ok 'sem arquivo de unit, o fallback para list-units encontra e reinicia'
  else
    falha 'fallback não reiniciou a unit carregada'; cat "$TMP/log" >&2
  fi
else
  rc=$?
  falha "fallback de list-units não foi alcançado (saiu com $rc)"
  head -5 "$TMP/out" >&2
fi

# Regressão específica: com `set -e`, um `systemctl start` sem guarda aborta o
# script na primeira unit quebrada — as saudáveis nunca são reiniciadas e o
# acumulador de falha nunca é alcançado.
: > "$TMP/log"
if rodar 'actions.runner.s2corporativo-ejc.velha.service actions.runner.s2corporativo-ejc.boa.service' 1 'actions.runner.s2corporativo-ejc.velha.service'; then
  falha 'unit quebrada deveria fazer o passo falhar'
else
  rc=$?
  if [ "$rc" -ne 6 ]; then
    falha "unit quebrada saiu com $rc, esperado 6"
  elif grep -q '^restart actions.runner.s2corporativo-ejc.boa.service' "$TMP/log"; then
    ok 'restart que falha não aborta o laço: unit saudável ainda é reiniciada'
  else
    falha 'laço abortou na primeira unit quebrada — unit saudável não foi reiniciada'
    cat "$TMP/log" >&2
  fi
fi

# Regressão do P1 apontado pelo Codex em ea439071: runner de OUTRO repositório
# instalado na mesma VPS não pode ser tocado. Com `actions.runner.*.service` os
# laços parariam um job alheio em pleno voo.
: > "$TMP/log"
if FAKE_UNIT_FILES='actions.runner.outraorg-outrorepo.vps.service' \
   FAKE_UNITS='actions.runner.outraorg-outrorepo.vps.service' \
   FAKE_ATIVO=1 FAKE_START_FAIL="" FAKE_LOG="$TMP/log" PATH="$BIN:$PATH" \
   bash "$TMP/bloco1.sh" >"$TMP/out" 2>&1; then
  falha 'runner de outro repositório foi aceito — deveria abortar com exit 4'
else
  rc=$?
  if [ "$rc" -ne 4 ]; then
    falha "runner alheio saiu com $rc, esperado 4"
  elif [ -s "$TMP/log" ]; then
    falha 'runner de outro repositório foi TOCADO'; cat "$TMP/log" >&2
  else
    ok 'runner de outro repositório não é descoberto nem tocado'
  fi
fi

# Regressão do segundo P1: runner travado mas ainda `active`. Com o antigo
# `stop || true` seguido de `start`, o stop falho era engolido, o start virava
# no-op bem-sucedido e o is-active final declarava recuperação sem ciclar nada.
: > "$TMP/log"
if FAKE_UNIT_FILES='actions.runner.s2corporativo-ejc.travada.service' \
   FAKE_UNITS='actions.runner.s2corporativo-ejc.travada.service' \
   FAKE_SEMPRE_ATIVO=1 FAKE_START_FAIL='actions.runner.s2corporativo-ejc.travada.service' \
   FAKE_LOG="$TMP/log" PATH="$BIN:$PATH" bash "$TMP/bloco1.sh" >"$TMP/out" 2>&1; then
  falha 'runner travado reportou recuperação bem-sucedida sem ter sido ciclado'
  cat "$TMP/log" >&2
else
  ok 'runner que não cicla falha, mesmo continuando ativo'
fi

echo
if [ "$falhas" -eq 0 ]; then
  echo "[recover-runner-test] OK — descoberta por unit systemd, ramificações idênticas e invariantes de segurança preservados."
else
  echo "[recover-runner-test] $falhas verificação(ões) falharam." >&2
  exit 1
fi
