#!/usr/bin/env bash
# Confere se o SHA informado pelo operador identifica o HEAD do checkout.
# Aceita SHA completo (40 hex) OU prefixo abreviado (>= 7 hex), como o git.
# Motivo (1º deploy manual real, 2026-09-05): o pré-voo comparava a string
# inteira e reprovava `--sha 094e3d8a` contra o HEAD completo — o runbook
# ensinava o formato curto e o script exigia o longo.
#
# Uso: ejc_sha_confere <head_completo> <sha_informado>  → 0 se confere.
ejc_sha_confere() {
  local head="$1" alvo="$2"
  case "$alvo" in
    *[!0-9a-fA-F]*|"") return 1 ;;   # não é hex
  esac
  [ "${#alvo}" -ge 7 ] || return 1    # curto demais para ser inequívoco
  [ "${#alvo}" -le 40 ] || return 1
  alvo="$(printf '%s' "$alvo" | tr 'A-F' 'a-f')"
  case "$head" in
    "$alvo"*) return 0 ;;
  esac
  return 1
}
