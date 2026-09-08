#!/usr/bin/env bash
# Guard reutilizável para scripts históricos que não pertencem mais ao caminho
# canônico de deploy. Deve ser chamado antes de qualquer mutação.

ejc_legacy_script_guard() {
  local script_name="${1:-script legado}"
  local replacement="${2:-RUNBOOK_DEPLOY_MANUAL.md}"
  case "${EJC_LEGACY_SCRIPT_OK:-0}" in
    1)
      printf '[legacy-guard] AVISO: opt-in explícito habilitou %s; use somente em contingência documentada.\n' "$script_name" >&2
      return 0
      ;;
    0|'') ;;
    *)
      printf '[legacy-guard] BLOQUEADO: EJC_LEGACY_SCRIPT_OK aceita somente 0 ou 1.\n' >&2
      exit 64
      ;;
  esac

  cat >&2 <<EOF2
[legacy-guard] BLOQUEADO: $script_name é legado e pode contornar backup, mutex, CI ou política atual de deploy.
Caminho suportado: $replacement
Execução excepcional exige revisão operacional e opt-in explícito:
  EJC_LEGACY_SCRIPT_OK=1 <comando>
EOF2
  exit 64
}
