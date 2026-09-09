#!/usr/bin/env bash
# Guard reutilizável para scripts históricos que não pertencem mais ao caminho
# canônico de deploy. Deve ser chamado antes de qualquer mutação.

ejc_legacy_script_guard() {
  local script_name="${1:-script legado}"
  local replacement="${2:-RUNBOOK_DEPLOY_MANUAL.md}"
  case "${EJC_LEGACY_SCRIPT_OK:-}" in
    I_UNDERSTAND_THIS_IS_LEGACY)
      if [ -z "${EJC_LEGACY_SCRIPT_REASON:-}" ]; then
        printf '[legacy-guard] BLOQUEADO: EJC_LEGACY_SCRIPT_REASON é obrigatório para contingência.\n' >&2
        exit 64
      fi
      printf '[legacy-guard] AVISO: contingência explícita habilitou %s; motivo registrado no ambiente.\n' "$script_name" >&2
      return 0
      ;;
    '') ;;
    *)
      printf '[legacy-guard] BLOQUEADO: EJC_LEGACY_SCRIPT_OK exige a frase I_UNDERSTAND_THIS_IS_LEGACY.\n' >&2
      exit 64
      ;;
  esac

  cat >&2 <<EOF2
[legacy-guard] BLOQUEADO: $script_name é legado e pode contornar backup, mutex, CI ou política atual de deploy.
Caminho suportado: $replacement
Execução excepcional exige revisão operacional, motivo registrado e opt-in explícito:
  EJC_LEGACY_SCRIPT_OK=I_UNDERSTAND_THIS_IS_LEGACY EJC_LEGACY_SCRIPT_REASON="<motivo>" <comando>
EOF2
  exit 64
}
