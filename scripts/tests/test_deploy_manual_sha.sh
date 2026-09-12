#!/usr/bin/env bash
# Regressão do pré-voo do deploy manual: SHA abreviado (>= 7 hex) confere
# com o HEAD completo; lixo, prefixo curto e SHA divergente reprovam.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/sha_prefix.sh"
HEAD="094e3d8a8c3c63289b1685803b998d166a083f47"
falhas=0
ok()   { printf 'ok   %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; falhas=1; }
ejc_sha_confere "$HEAD" "$HEAD"      && ok "sha completo"         || fail "sha completo"
ejc_sha_confere "$HEAD" "094e3d8a"   && ok "prefixo 8"            || fail "prefixo 8"
ejc_sha_confere "$HEAD" "094e3d8"    && ok "prefixo 7"            || fail "prefixo 7"
ejc_sha_confere "$HEAD" "094E3D8A"   && ok "prefixo maiúsculo"    || fail "prefixo maiúsculo"
! ejc_sha_confere "$HEAD" "094e3d"   && ok "prefixo 6 reprova"    || fail "prefixo 6 reprova"
! ejc_sha_confere "$HEAD" "0189b277" && ok "sha divergente reprova" || fail "sha divergente reprova"
! ejc_sha_confere "$HEAD" "main"     && ok "ref não-hex reprova"  || fail "ref não-hex reprova"
! ejc_sha_confere "$HEAD" ""         && ok "vazio reprova"        || fail "vazio reprova"
! ejc_sha_confere "$HEAD" "${HEAD}00" && ok "mais de 40 reprova"  || fail "mais de 40 reprova"
bash -n "$ROOT/scripts/deploy_manual.sh" && ok "deploy_manual.sh sintaxe" || fail "deploy_manual.sh sintaxe"
grep -q 'ejc_sha_confere "$head_local" "$TARGET_SHA"' "$ROOT/scripts/deploy_manual.sh" && ok "pré-voo usa a função" || fail "pré-voo usa a função"
grep -q 'origin_main_sha=' "$ROOT/scripts/deploy_manual.sh" && ok "manual exige origin/main" || fail "manual não exige origin/main"
grep -q '"$WOODPECKER_GATE" "$REPO_FULL_NAME" "$TARGET_SHA"' "$ROOT/scripts/deploy_manual.sh" && ok "manual exige gate Woodpecker" || fail "manual não exige gate Woodpecker"
exit $falhas
