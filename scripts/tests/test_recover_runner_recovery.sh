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
python3 - "$WORKFLOW" "$TMP" <<'PY'
import sys, pathlib, yaml
workflow, saida = sys.argv[1], pathlib.Path(sys.argv[2])
doc = yaml.safe_load(open(workflow, encoding="utf-8"))
blocos = []
for job in doc["jobs"].values():
    for step in job.get("steps", []):
        run = step.get("run") or ""
        if "<<'REMOTE'" not in run:
            continue
        for parte in run.split("<<'REMOTE'")[1:]:
            blocos.append(parte.split("\nREMOTE")[0].lstrip("\n"))
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
exigido  'sudo systemctl start' 'opera o serviço via systemctl'

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
  list-unit-files|list-units) printf '%s\n' ${FAKE_UNITS:-} ;;
  stop)  echo "stop $1" >> "${FAKE_LOG:?}" ;;
  start) echo "start $1" >> "${FAKE_LOG:?}"
         [ "${FAKE_START_FAIL:-}" != "$1" ] || exit 1 ;;
  is-active) [ "${FAKE_ATIVO:-1}" = "1" ] && [ "${FAKE_START_FAIL:-}" != "$2" ] ;;
  status)    echo "status simulado" ;;
esac
EOS
chmod +x "$BIN/sudo" "$BIN/systemctl"

rodar() { FAKE_UNITS="$1" FAKE_ATIVO="${2:-1}" FAKE_START_FAIL="${3:-}" \
            FAKE_LOG="$TMP/log" PATH="$BIN:$PATH" \
            bash "$TMP/bloco1.sh" >"$TMP/out" 2>&1; }

: > "$TMP/log"
if rodar 'actions.runner.s2corporativo-ejc.ejc-vps.service' 1; then
  if grep -q 'start actions.runner.s2corporativo-ejc.ejc-vps.service' "$TMP/log"; then
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
if rodar 'actions.runner.a.b.service' 0; then
  falha 'unit que não sobe deveria falhar'
else
  rc=$?
  [ "$rc" -eq 6 ] && ok 'unit que não fica ativa aborta com exit 6' \
                  || falha "unit inativa saiu com $rc, esperado 6"
fi

: > "$TMP/log"
if rodar 'actions.runner.a.b.service actions.runner.c.d.service' 1; then
  n="$(grep -c '^start ' "$TMP/log")"
  [ "$n" -eq 2 ] && ok 'múltiplas units: todas reiniciadas' \
                 || falha "múltiplas units: $n reiniciadas, esperado 2"
else
  falha 'múltiplas units saudáveis deveriam sair com 0'; cat "$TMP/out" >&2
fi

# Regressão específica: com `set -e`, um `systemctl start` sem guarda aborta o
# script na primeira unit quebrada — as saudáveis nunca são reiniciadas e o
# acumulador de falha nunca é alcançado.
: > "$TMP/log"
if rodar 'actions.runner.velha.service actions.runner.boa.service' 1 'actions.runner.velha.service'; then
  falha 'unit quebrada deveria fazer o passo falhar'
else
  rc=$?
  if [ "$rc" -ne 6 ]; then
    falha "unit quebrada saiu com $rc, esperado 6"
  elif grep -q '^start actions.runner.boa.service' "$TMP/log"; then
    ok 'start que falha não aborta o laço: unit saudável ainda é reiniciada'
  else
    falha 'laço abortou na primeira unit quebrada — unit saudável não foi reiniciada'
    cat "$TMP/log" >&2
  fi
fi

echo
if [ "$falhas" -eq 0 ]; then
  echo "[recover-runner-test] OK — descoberta por unit systemd, ramificações idênticas e invariantes de segurança preservados."
else
  echo "[recover-runner-test] $falhas verificação(ões) falharam." >&2
  exit 1
fi
